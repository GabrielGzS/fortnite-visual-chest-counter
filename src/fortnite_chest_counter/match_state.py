"""
Where a Fortnite match is up to, worked out over time from match_cues' scores (v0.3.0). Pure logic: it takes numbers and returns events.

It uses no images, files, clocks or randomness, and it changes nothing by itself, so the same observations always give the same result.
Nothing here affects chest counting: chests only come in as evidence that a match is being played.

    state        meaning
    UNKNOWN      not enough evidence yet (a real state: nothing is guessed)
    LOBBY        the menus, including the matchmaking queue
    LOADING      the CONNECTING screen, going either way
    PRE_GAME     the waiting island and the bus countdown
    IN_MATCH     on the bus or on the map, alive
    ELIMINATED   out of active play: eliminated, spectating, or won

Each rule needs a signal in 2 of the last 3 samples, unless the table says otherwise:

    from                      to                    evidence
    any                       LOADING               CONNECTING. An open match closes.
    any                       LOBBY                 menu bar or CANCEL. An open match closes.
    any but PRE_GAME          PRE_GAME              WAITING FOR PLAYERS or LAUNCHING IN
    PRE_GAME                  IN_MATCH              countdown gone 3 s with no health bar (the bus), or gone 15 s
    UNKNOWN, LOBBY, LOADING   IN_MATCH, joined late green health bar in 5 of 8 samples, or a counted chest (dated from the chest's
                                                    own time); no menu or loading text
    any                       ELIMINATED            YOU PLACED, Victory Royale, SPECTATING or ELIMINATED BY
    ELIMINATED                stays non-active      a health bar cannot distinguish a reboot from watching another player
    IN_MATCH, ELIMINATED      UNKNOWN               no evidence of play or no picture for 60 s, or video time ran backwards

What it will not claim:
  * A match is "complete" when its start was seen, the player's part in it ended on screen, there is English evidence, and there is no
    break in the video before that ending. Complete describes what was observed, not how it went: YOU PLACED, Victory, or play giving way
    to a loading screen or the menus all end it, however soon and for whatever reason. Video simply stopping does not. A break after the
    ending hides nothing about the match, so it does not count.
  * WAITING FOR PLAYERS and LAUNCHING IN only appear before a game. A match opened on a health bar straight after a loading screen, with no
    chest in it, that such text then closes was the waiting island, whose HUD can appear before its text can be read. It stays unconfirmed.
    The same holds for a match whose start was only guessed because the countdown text stayed unread for 15 s while the health bar stayed:
    the bus was never seen leaving, and a countdown coming back proves it had not (rc6: 36 s of island over bright sky read as a match).
  * A match is "unconfirmed" until English text or an English chest belongs to it. A health bar, a Portuguese chest and Victory Royale can
    never confirm one: the health bar and the word ROYALE look the same in other languages. Unconfirmed matches must stay out of statistics.
  * An elimination does not finish a match on its own. The record stays open through spectating. M1 cannot identify the original player's
    return: HUD-only recovery stays non-active and makes a later ending partial if the earlier ending was not observed.
  * Time after a victory cannot prove another match began. A new loading/menu/countdown boundary is needed; edited games may be missed.
  * Pending English evidence cannot cross missing samples or a long black/frozen picture. Already observed evidence in an open record stays
    attached to that record, whose continuity is marked separately.
  * A rewind that keeps the clock running cannot be seen directly. A long black or frozen picture marks the match as broken, and gameplay
    reached without a loading screen counts as joined late, so a rewound match stays partial rather than complete.
  * The number after YOU PLACED is not read, so no placement is reported.
  * Time with nothing of the game in view is not counted as play: no health bar, no fixed HUD, no text and no chest for 10 s or more, for example a
    browser page. It is uncertain, not an ending, and it does not by itself make a match partial: the footage has no full-screen map or inventory
    screen to prove those would be told apart. The HUD only answers "is the game on screen?". It never opens or closes a match.

M1's signal names are repeated here on purpose, so this module needs no image code; tests check that both lists agree.
"""

from collections import deque
from dataclasses import asdict, dataclass, field

UNKNOWN, LOBBY, LOADING, PRE_GAME, IN_MATCH, ELIMINATED = "UNKNOWN", "LOBBY", "LOADING", "PRE_GAME", "IN_MATCH", "ELIMINATED"
COMPLETE, PARTIAL, UNCONFIRMED = "complete", "partial", "unconfirmed"
PLACED, VICTORY, LEFT_OR_UNKNOWN, STOPPED, LOST, DISCONTINUITY = "placed", "victory", "left_or_unknown", "stopped", "lost", "discontinuity"
HIGH, MEDIUM, LOW = "high", "medium", "low"
WAITING_ISLAND = "waiting island"

SCORE_THRESHOLD = 0.70
HEALTH_BAR_MIN_PIXELS = 30
ENGLISH_SIGNALS = frozenset({"you_placed", "eliminated_by", "connecting", "lobby_menu", "matchmaking", "waiting_for_players", "bus_launching", "spectating"})
ALL_SIGNALS = ENGLISH_SIGNALS | {"victory_royale"}

CONFIRM_HITS, CONFIRM_WINDOW = 2, 3
HUD_HITS, HUD_WINDOW = 5, 8
AMBIGUOUS_HUD_HITS, AMBIGUOUS_HUD_WINDOW = 8, 10
COUNTDOWN_GONE_ON_BUS, COUNTDOWN_GONE_ANYWAY = 3.0, 15.0
NO_EVIDENCE_LIMIT = 60.0
MAX_SAMPLE_GAP = 5.0                       # samples further apart than this mean part of the video was not seen
NO_PICTURE_BREAK = 3.0                     # a black or frozen picture this long may hide a jump in the video
GAME_OUT_OF_VIEW = 10.0                    # nothing of the game on screen this long is not play. Over about 1,340 s of real play the longest was 3 s; browser pages ran 18 s and 20 s
OUT_OF_VIEW_REASON = "game not in view"


def chest_language(popup_template):
    """"en", "pt" or "unknown" for an estimator event's popup_template, such as "en:CHEST"."""
    prefix = str(popup_template or "").split(":")[0]
    return prefix if prefix in ("en", "pt") else "unknown"


@dataclass(frozen=True)
class Observation:
    t: float                               # seconds of source time, increasing
    scores: dict                           # match_cues.CueReader.read(): {signal: 0 to 1}
    health_bar_pixels: int = 0
    black: bool = False
    frozen: bool = False
    chests: tuple = ()                     # the language of each chest counted since the last observation
    hud_in_view: object = None             # the fixed HUD seen (True) or not (False); None when it was not measured, as in a recorded timeline
    first_chest_t: object = None           # the earliest of those chests' own times; None when not known, as in a recorded timeline
    health_green_pixels: object = None     # the health bar's green part alone; None when not measured, as in a recorded timeline


@dataclass(frozen=True)
class Transition:
    t: float
    previous: str
    state: str
    reason: str
    match_number: object = None


@dataclass(frozen=True)
class MatchOpened:
    t: float
    match_number: int
    observed_from_start: bool
    start_confidence: str


@dataclass(frozen=True)
class MatchRecord:
    """One match, final. Everything a later stage needs to store it, and nothing it would have to guess."""
    match_number: int
    completion: str                        # complete, partial or unconfirmed
    english_confirmed: bool
    ended_by: str                          # placed, victory, left_or_unknown, stopped, lost or discontinuity
    observed_from_start: bool
    opened_t: float                        # first evidence of this match
    played_from_t: float                   # the bus left, or the first sign of play when joining late
    ended_t: object                        # YOU PLACED or Victory first seen, or None when the end was not seen
    closed_t: float                        # when the tracker closes the record, not an inferred match ending
    observed_seconds: float                # usable picture between opening and closing
    active_seconds: float                  # alive on the bus or the map
    spectating_seconds: float              # conservatively non-active after the player was out; includes wins/unclear HUD recovery
    uncertain_seconds: float               # black, frozen or missing picture
    complete_duration_seconds: object      # bus to end, only for a complete match; otherwise None
    start_confidence: str
    end_confidence: str
    discontinuity: bool
    respawns: int                          # remains zero until positive own-player recovery evidence exists
    english_chests: int
    portuguese_chests: int
    reasons: tuple                         # why it opened, changed and closed
    evidence: tuple                        # (t, signal, score) the first time each signal was confirmed

    def to_dict(self):
        return asdict(self)


@dataclass
class _Match:
    number: int
    opened_t: float
    played_from_t: float
    observed_from_start: bool
    start_confidence: str
    english: set = field(default_factory=set)
    ended_by: object = None
    ended_t: object = None
    end_confidence: str = LOW
    ambiguous_recovery: bool = False
    discontinuity: bool = False
    observed: float = 0.0
    active: float = 0.0
    spectating: float = 0.0
    uncertain: float = 0.0
    respawns: int = 0
    english_chests: int = 0
    portuguese_chests: int = 0
    reasons: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    seen: set = field(default_factory=set)
    after_loading: bool = False            # joined on a health bar straight after a loading screen
    start_guessed: bool = False            # opened because the countdown text was gone 15 s, with no sign of the bus
    chest_counted: bool = False


@dataclass
class _Countdown:
    first_t: float
    last_t: float
    confidence: str
    signals: set
    uncertain: float = 0.0
    broken: bool = False
    uncertain_at_last: float = 0.0         # uncertainty before the last countdown cannot be subtracted from subsequent play


class MatchStateMachine:
    def __init__(self):
        self.state = UNKNOWN
        self._match = None
        self._opened = 0
        self._last_t = None
        self._recent = {signal: deque(maxlen=CONFIRM_WINDOW) for signal in ALL_SIGNALS}
        self._hud = deque(maxlen=HUD_WINDOW)
        self._after = deque(maxlen=AMBIGUOUS_HUD_WINDOW)
        self._countdown = None
        self._no_picture_since = None
        self._last_evidence_t = None
        self._last_closed_t = float("-inf")
        self._last_screen_text_t = float("-inf")
        self._loading_english_continuous = False
        self._unseen_since = None
        self._active_at_unseen = 0.0
        self._out_of_view = False

    @property
    def open_match_number(self):
        return self._match.number if self._match else None

    def snapshot(self):
        """The open match's running totals, for a checkpoint, or None when no match is open. Reads only: it changes no decision."""
        match = self._match
        if match is None:
            return None
        return {"match_number": match.number, "opened_t": match.opened_t, "played_from_t": match.played_from_t, "observed_seconds": round(match.observed, 3),
                "active_seconds": round(match.active, 3), "spectating_seconds": round(match.spectating, 3), "uncertain_seconds": round(match.uncertain, 3),
                "english_confirmed": bool(match.english), "observed_from_start": match.observed_from_start, "discontinuity": match.discontinuity, "ended_by": match.ended_by}

    # ------------------------------------------------------------------ the two calls
    def update(self, observation):
        """Take the next observation. -> the events it caused, in order: Transition, MatchOpened and MatchRecord."""
        events, t = [], observation.t
        elapsed = 0.0
        if self._last_t is not None:
            elapsed = t - self._last_t
            if elapsed == 0:
                return events
            if elapsed < 0:
                self._time_ran_backwards(t, events)
                elapsed = 0.0
            elif elapsed > MAX_SAMPLE_GAP:
                self._samples_missing(t, elapsed, events)
                elapsed = 0.0
        self._last_t = t
        if self._last_evidence_t is None:
            self._last_evidence_t = t
        if observation.black or observation.frozen:
            self._no_picture(t, elapsed, events)
            return events
        self._no_picture_since = None
        self._count_time(elapsed)
        hit = self._remember(observation)
        self._watch_view(observation, hit)
        self._decide(observation, hit, events)
        self._note_chests(observation)
        return events

    def finish(self, t, reason=STOPPED):
        """Counting stopped or the source changed: close whatever is open. A later run starts a new machine, and a new match record."""
        events = []
        if self._match is not None:
            if self._last_t is not None and t > self._last_t:
                elapsed = t - self._last_t
                if elapsed > MAX_SAMPLE_GAP or self._no_picture_since is not None:
                    self._match.uncertain += elapsed
                    if elapsed > MAX_SAMPLE_GAP:
                        self._match.discontinuity |= self._match.ended_by is None
                        self._match.reasons.append(f"{elapsed:.0f} s of video not seen before stopping")
                else:
                    self._count_time(elapsed)
            self._close(t, self._match.ended_by or reason, [reason], events)
        self._countdown = None
        if self.state != UNKNOWN:
            self._go(t, UNKNOWN, reason, events)
        return events

    # ------------------------------------------------------------------ time
    def _time_ran_backwards(self, t, events):
        if self._match is not None:
            self._match.discontinuity |= self._match.ended_by is None
            self._close(self._last_t, self._match.ended_by or DISCONTINUITY, ["video time ran backwards"], events)
        self._countdown = None
        self._clear_memory()
        self._last_closed_t = self._last_screen_text_t = float("-inf")       # the old clock no longer applies
        if self.state != UNKNOWN:
            self._go(t, UNKNOWN, "video_time_jump", events)

    def _samples_missing(self, t, elapsed, events):
        match = self._match
        if match is not None:
            match.discontinuity |= match.ended_by is None
            match.uncertain += elapsed
            match.reasons.append(f"{elapsed:.0f} s of video not seen")
        if self._countdown is not None:
            self._countdown.broken = True
            self._countdown.uncertain += elapsed
        self._clear_memory()
        if elapsed >= NO_EVIDENCE_LIMIT and match is not None:
            self._close(t, match.ended_by or LOST, ["too long without video"], events)
            self._go(t, UNKNOWN, "no_evidence", events)

    def _no_picture(self, t, elapsed, events):
        """Black or frozen: the frame says nothing, so no decision is made and the time counts as uncertain. It is no sign of the game either, so
        a stretch with the game out of view carries on through it: a still browser page reads as a frozen picture now and then."""
        if self._match is not None:
            self._match.uncertain += elapsed
        if self._countdown is not None:
            self._countdown.uncertain += elapsed
        if self._no_picture_since is None:
            self._no_picture_since = t
        lost_for = t - self._no_picture_since
        if lost_for >= NO_PICTURE_BREAK:
            if self._match is not None and self._match.ended_by is None and not self._match.discontinuity:
                self._match.discontinuity = True
                self._match.reasons.append("picture lost long enough to hide a jump")
            if self._countdown is not None:
                self._countdown.broken = True
            self._clear_memory()
            self._last_evidence_t = t
        if lost_for >= NO_EVIDENCE_LIMIT and self._match is not None:      # whatever comes back may be a different match
            self._close(t, self._match.ended_by or LOST, ["too long without a picture"], events)
            self._go(t, UNKNOWN, "no_evidence", events)

    def _count_time(self, elapsed):
        match = self._match
        if match is None:
            return
        if self._out_of_view:
            match.uncertain += elapsed
            return
        match.observed += elapsed
        if self.state == IN_MATCH:
            match.active += elapsed
        elif self.state == ELIMINATED:
            match.spectating += elapsed

    def _clear_memory(self):
        for recent in self._recent.values():
            recent.clear()
        self._hud.clear()
        self._after.clear()
        self._unseen_since, self._out_of_view = None, False
        self._loading_english_continuous = False
        if self._countdown is not None:
            self._countdown.signals.clear()               # pending language evidence, not a match already observed

    # ------------------------------------------------------------------ evidence
    def _remember(self, observation):
        t, scores = observation.t, observation.scores
        hit = {signal: scores.get(signal, 0.0) >= SCORE_THRESHOLD for signal in ALL_SIGNALS}
        for signal in ALL_SIGNALS:
            self._recent[signal].append((t, hit[signal], scores.get(signal, 0.0)))
        screen_text = hit["connecting"] or hit["lobby_menu"] or hit["matchmaking"]          # loading artwork can imitate a health bar
        if screen_text:
            self._last_screen_text_t = t
        hud = observation.health_bar_pixels >= HEALTH_BAR_MIN_PIXELS and not screen_text
        # Only the player's own green health bar may open a match. The menus' blue PARTY CHANNEL tiles sit where a small HUD draws the bar and
        # read as a shield bar; a shield bar alone keeps a match going but never starts one.
        green = observation.health_green_pixels
        self._hud.append((t, hud, hud and (green is None or green >= HEALTH_BAR_MIN_PIXELS)))
        self._after.append((hud, hit["you_placed"] or hit["eliminated_by"] or hit["spectating"]))
        if hud or observation.hud_in_view or observation.chests or any(hit.values()):
            self._last_evidence_t = t
        return hit

    def _watch_view(self, observation, hit):
        """During play, is anything of the game on screen? Time without it stops counting as play, reaching back to when it went."""
        match = self._match
        unseen = (self.state == IN_MATCH and match is not None and observation.hud_in_view is False and observation.health_bar_pixels < HEALTH_BAR_MIN_PIXELS
                  and not observation.chests and not any(hit.values()))
        if not unseen:
            self._unseen_since, self._out_of_view = None, False
            return
        if self._unseen_since is None:
            self._unseen_since, self._active_at_unseen = observation.t, match.active
        lost_for = observation.t - self._unseen_since
        if lost_for >= GAME_OUT_OF_VIEW and not self._out_of_view:
            self._out_of_view = True
            moved = match.active - self._active_at_unseen      # only what was counted as play: a black or frozen moment already went to uncertain
            match.active -= moved
            match.observed -= moved
            match.uncertain += moved
            match.reasons.append(OUT_OF_VIEW_REASON)

    def _confirmed(self, signal):
        return sum(1 for _, hit, _ in self._recent[signal] if hit) >= CONFIRM_HITS

    def _first_hit(self, signal):
        return next((t for t, hit, _ in self._recent[signal] if hit), self._last_t)

    def _note_match_evidence(self):
        match = self._match
        if match is None:
            return
        for signal in ALL_SIGNALS:
            if signal not in match.seen and self._confirmed(signal):
                match.seen.add(signal)
                t, _, score = next(item for item in self._recent[signal] if item[1])
                match.evidence.append((t, signal, round(score, 3)))
                if signal in ENGLISH_SIGNALS:
                    match.english.add(signal)

    def _note_chests(self, observation):
        match = self._match
        if match is None:
            return
        for language in observation.chests:
            match.chest_counted = True
            if language == "en":
                match.english_chests += 1
                match.english.add("en_chest")
            elif language == "pt":
                match.portuguese_chests += 1

    # ------------------------------------------------------------------ the rules, strongest evidence first
    def _decide(self, observation, hit, events):
        t = observation.t
        self._note_match_evidence()
        if self._confirmed("you_placed"):
            return self._player_out(t, PLACED, "you_placed", events)
        if self._confirmed("victory_royale"):
            return self._player_out(t, VICTORY, "victory_royale", events)
        for signal in ("spectating", "eliminated_by"):
            if self._confirmed(signal):
                return self._player_out(t, None, signal, events)
        if self._confirmed("connecting"):
            return self._screen(t, LOADING, "connecting_seen", events)
        if self._confirmed("lobby_menu") or self._confirmed("matchmaking"):
            return self._screen(t, LOBBY, "menu_seen", events)
        if self._confirmed("waiting_for_players") or self._confirmed("bus_launching"):
            return self._countdown_seen(t, events)
        if self.state == PRE_GAME:
            self._after_countdown(t, events)
        elif self.state in (UNKNOWN, LOBBY, LOADING):
            self._maybe_joined_late(t, observation, hit, events)
        elif self.state == IN_MATCH:
            self._check_still_playing(t, events)
        else:
            self._after_elimination(t, events)

    def _player_out(self, t, ended_by, signal, events):
        match = self._match
        if match is not None and ended_by is not None and match.ended_by is None:
            match.ended_by, match.ended_t = ended_by, self._first_hit(signal)
            match.end_confidence = HIGH if ended_by == PLACED else MEDIUM
            match.reasons.append(f"ended: {signal}")
        if self.state != ELIMINATED:
            self._countdown = None
            self._go(t, ELIMINATED, f"{signal}_seen", events)

    def _screen(self, t, state, reason, events):
        self._loading_english_continuous = state == LOADING   # fresh confirmation also restores evidence after a break in LOADING
        if self.state == state:
            return
        if self._match is not None:
            self._close(t, self._match.ended_by or LEFT_OR_UNKNOWN, [reason], events, play_ended=True)
        self._countdown = None
        self._go(t, state, reason, events)

    def _countdown_seen(self, t, events):
        signal = "waiting_for_players" if self._confirmed("waiting_for_players") else "bus_launching"
        if self.state != PRE_GAME:
            if self._match is not None:
                match = self._match
                if (match.after_loading or match.start_guessed) and not match.chest_counted and match.ended_by is None:
                    match.english.clear()              # the countdown proves play had not begun, so what confirmed it proves nothing
                    match.reasons.append(WAITING_ISLAND)
                self._close(t, match.ended_by or LEFT_OR_UNKNOWN, ["next match countdown seen"], events)
            self._countdown = _Countdown(self._first_hit(signal), t, HIGH if signal == "waiting_for_players" else MEDIUM, set())
            self._go(t, PRE_GAME, "countdown_seen", events)
        self._countdown.last_t = t
        self._countdown.uncertain_at_last = self._countdown.uncertain
        self._countdown.signals.add(signal)

    def _after_countdown(self, t, events):
        countdown = self._countdown
        gone = t - countdown.last_t
        no_hud_lately = not any(hud for _, hud, _ in list(self._hud)[-3:])
        if not ((gone >= COUNTDOWN_GONE_ON_BUS and no_hud_lately) or gone >= COUNTDOWN_GONE_ANYWAY):
            return
        unseen_after_countdown = countdown.uncertain - countdown.uncertain_at_last
        # A break after the last countdown can hide the departure. Use the first
        # usable observation after it, never date active play inside that break.
        played_from = t if countdown.broken and unseen_after_countdown else countdown.last_t
        match = self._open(t, countdown.first_t, played_from, not countdown.broken, countdown.confidence, events)
        match.english |= countdown.signals
        match.observed = max(t - match.opened_t - countdown.uncertain, 0.0)
        match.uncertain = countdown.uncertain
        match.active = max(t - match.played_from_t - (unseen_after_countdown if played_from == countdown.last_t else 0.0), 0.0)
        match.discontinuity = countdown.broken
        match.start_guessed = not (gone >= COUNTDOWN_GONE_ON_BUS and no_hud_lately)      # only the 15 s fallback: nothing showed the bus
        match.reasons.append("started: countdown ended")
        self._countdown = None
        self._go(t, IN_MATCH, "bus_departed" if gone < COUNTDOWN_GONE_ANYWAY else "countdown_timed_out", events)

    def _maybe_joined_late(self, t, observation, hit, events):
        text_lately = any(any(seen for _, seen, _ in self._recent[signal]) for signal in ("connecting", "lobby_menu", "matchmaking"))
        sustained = sum(1 for _, _, own in self._hud if own) >= HUD_HITS
        chest = bool(observation.chests)
        if text_lately or not (sustained or chest):
            return
        first = next((seen_t for seen_t, _, own in self._hud if own), t) if sustained else t
        if chest and observation.first_chest_t is not None:
            # The chest that shows the match is being played happened before it reached here (the detector finishes it a moment later):
            # reach back to it, or the live and saved per-match numbers would leave out the very chest that opened the match.
            # Never back into a screen that showed menus or loading; _open also stops at the previous match.
            first = max(min(first, observation.first_chest_t), self._last_screen_text_t)
        from_loading = self.state == LOADING
        match = self._open(t, first, first, False, LOW, events)
        match.after_loading = from_loading
        match.observed = match.active = t - match.opened_t
        if from_loading and self._loading_english_continuous:
            match.english.add("connecting")
        match.reasons.append("started: joined late, " + ("health bar" if sustained else "counted chest"))
        self._go(t, IN_MATCH, "health_bar_sustained" if sustained else "chest_counted", events)

    def _check_still_playing(self, t, events):
        if t - self._last_evidence_t >= NO_EVIDENCE_LIMIT:
            self._close(t, LOST, ["no evidence of play"], events)
            self._go(t, UNKNOWN, "no_evidence", events)

    def _after_elimination(self, t, events):
        match = self._match
        if t - self._last_evidence_t >= NO_EVIDENCE_LIMIT:
            if match is not None:
                self._close(t, match.ended_by or LOST, ["no evidence after the match"], events)
            self._go(t, UNKNOWN, "no_evidence", events)
            return
        # A spectated player's HUD and a real reboot look the same to M1.
        # This applies even when recording began on an end screen (no open match).
        if match is None or match.ended_by is not None or match.ambiguous_recovery:
            return
        full = len(self._after) == AMBIGUOUS_HUD_WINDOW
        if full and sum(1 for hud, _ in self._after if hud) >= AMBIGUOUS_HUD_HITS and not any(after for _, after in self._after):
            match.ambiguous_recovery = True
            match.reasons.append("health bar after elimination: own-player recovery unconfirmed")

    # ------------------------------------------------------------------ results
    def _open(self, t, opened_t, played_from_t, from_start, confidence, events):
        self._opened += 1
        # Never reach back before the previous match closed: two matches sharing a moment could both be credited with the same chest.
        opened_t, played_from_t = max(opened_t, self._last_closed_t), max(played_from_t, self._last_closed_t)
        self._match = _Match(self._opened, opened_t, played_from_t, from_start, confidence)
        events.append(MatchOpened(t, self._opened, from_start, confidence))
        return self._match

    def _go(self, t, state, reason, events):
        events.append(Transition(t, self.state, state, reason, self.open_match_number))
        self.state = state
        if state != LOADING:
            self._loading_english_continuous = False

    def _close(self, t, ended_by, reasons, events, play_ended=False):
        match = self._match
        finished = ended_by in (PLACED, VICTORY)
        if not match.english:
            completion = UNCONFIRMED
        elif match.observed_from_start and (finished or play_ended) and not match.discontinuity and not match.ambiguous_recovery:
            completion = COMPLETE
        else:
            completion = PARTIAL
        duration = round((match.ended_t if finished else t) - match.played_from_t, 3) if completion == COMPLETE else None
        events.append(MatchRecord(match.number, completion, bool(match.english), ended_by, match.observed_from_start, match.opened_t, match.played_from_t,
                                  match.ended_t if finished else None, t, round(match.observed, 3), round(match.active, 3), round(match.spectating, 3),
                                  round(match.uncertain, 3), duration, match.start_confidence, match.end_confidence if finished else LOW, match.discontinuity,
                                  match.respawns, match.english_chests, match.portuguese_chests, tuple(match.reasons + reasons), tuple(match.evidence)))
        self._match = None
        self._last_closed_t = t
