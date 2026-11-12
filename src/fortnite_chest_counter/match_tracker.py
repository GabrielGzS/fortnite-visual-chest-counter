"""
Follows the match beside the chest counter (v0.3.0, M4, M6). It watches and writes diagnostics, and in "on" mode also passes what it saw to
the match history. It changes nothing else.

The live loop calls these after each frame has been counted:

    chest(ev)         a finished event; a counted chest becomes evidence for the next sample
    offer(t, frame)   an analysed frame; about one per second of source time is actually read
    close(reason)     counting stopped: closes whatever is open

It reuses the frames the detector already decoded and only reads them. It writes "match_state" lines in the session log, which never carry
a "time" key: research/regress.py and research/match_replay.py read any line with one as a chest event.

With a history, a checkpoint saves the open match's running totals every `heartbeat_seconds` of source time, and at every match boundary.
That setting decides only how often totals reach the disk. Sampling stays at one per second and time is accumulated continuously, so a
longer interval can only mean more time counted as uncertain after a crash.

No failure here may reach the counter. Every call contains its own errors: the first one gives one warning and tracking stops for the rest
of the run, leaving any open match unrecorded. KeyboardInterrupt is left alone, because that is the user stopping the counter.

Evidence rules, matching the offline replay (research/match_replay.py) and M2's rule that pending evidence cannot cross a break:
  * A chest reaches M2 with the next sample. On a black or frozen sample M2 ignores it, and it is not carried over to a later one.
  * A chest that began before a break in the video is dropped. The detector finishes events late, so without this a chest from before a
    long outage could arrive just after it and open a match that nothing on screen supports.
  * Chests still waiting when counting stops are counted in the summary, never given to M2.
"""

import math
import time
from dataclasses import asdict

from fortnite_chest_counter import match_cues as M
from fortnite_chest_counter import match_state as S

LOG_EVENT = "match_state"
LOG_SCHEMA = 1
MODE = "shadow"
SAMPLE_SECONDS = 1.0
SAMPLE_TOLERANCE = 1e-6                    # frame times are sums of 1/fps: fifteen of them can add up to 0.9999999 s
SOURCE_LOST_REASONS = frozenset({"video source stopped"})


class MatchTracker:
    def __init__(self, write, warn, cues=M, machine=None, history=None, heartbeat_seconds=60, frames=None, status=None):
        """`write` takes one dict for the session log, `warn` one message for the user. Raises if the templates cannot be loaded.
        `history` is a HistoryWriter in "on" mode; `frames` returns (frames processed, frames dropped) for its checkpoints.
        `status` receives what the app's status line shows, once per sample. It is read-only reporting."""
        self._write, self._warn, self._cues, self._status = write, warn, cues, status
        self._history, self._beat_every, self._frames, self._last_beat_t = history, heartbeat_seconds, frames, None
        self._mode = MODE if history is None else "on"
        self._reader = cues.CueReader()
        self._machine = machine if machine is not None else S.MatchStateMachine()
        self._picture = None               # a small copy of the last sample's picture, never the frame itself
        self._pending = []                 # (language, own time) of the chests counted since the last sample
        self._counted = []                 # (time, certain, approx) of every chest counted in this run, for the live per-match numbers
        self._out_at = None                # when the open match's player was first out
        self._closed = None                # the match that closed last, for its final numbers
        self._last_sample_t = self._last_seen_t = self._break_t = None
        self._samples, self._sample_s, self._total_s, self._max_s, self._source_s = 0, 0.0, 0.0, 0.0, 0.0
        self._chests = {"delivered": 0, "no_picture": 0, "dropped_at_break": 0}
        self.failed = self.closed = False
        self._log("started", mode=self._mode, schema=LOG_SCHEMA, sample_seconds=SAMPLE_SECONDS)

    # ------------------------------------------------------------------ the three calls
    def offer(self, t, frame):
        if self.failed or self.closed:
            return
        begin = time.perf_counter()
        try:
            sampled = self._offer(t, frame)
        except Exception as error:
            self._fail("offer", error)
            return
        spent = time.perf_counter() - begin
        self._total_s += spent
        if sampled:
            self._samples += 1
            self._sample_s += spent
            self._max_s = max(self._max_s, spent)

    def chest(self, ev):
        if self.failed or self.closed:
            return
        try:
            if not (ev.get("certain_counted") or ev.get("approx_counted")):
                return
            self._counted.append((ev["time"], bool(ev.get("certain_counted")), True))        # every counted chest, also one that is no evidence below
            if self._break_t is not None and ev["time"] < self._break_t:
                self._chests["dropped_at_break"] += 1
                return
            self._pending.append((S.chest_language(ev.get("popup_template")), float(ev["time"])))
        except Exception as error:
            self._fail("chest", error)

    def close(self, reason):
        if self.failed or self.closed:
            return
        self.closed = True
        try:
            if self._last_seen_t is not None:
                ended_by = S.LOST if reason in SOURCE_LOST_REASONS else S.STOPPED
                self._report(self._machine.finish(self._last_seen_t, ended_by))
                self._checkpoint(self._last_seen_t, True)
            self._log("summary", stop_reason=reason, chests_undelivered=len(self._pending), **{f"chests_{k}": v for k, v in self._chests.items()},
                      **self.stats())
        except Exception as error:
            self._fail("close", error)

    def stats(self):
        """Time spent here, apart from chest detection. Measured on the wall clock in the counting thread, so at worst an overestimate of
        its CPU. The share of one core is per second of source time, which also holds when a recording runs faster than real time."""
        return {"match_mode": self._mode, "match_failed": self.failed, "match_samples": self._samples,
                "match_ms_avg": round(1000 * self._sample_s / self._samples, 3) if self._samples else None,
                "match_ms_max": round(1000 * self._max_s, 3) if self._samples else None,
                "match_total_s": round(self._total_s, 4), "match_source_seconds": round(self._source_s, 1),
                "match_percent_of_one_core": round(100 * self._total_s / self._source_s, 3) if self._source_s else None}

    # ------------------------------------------------------------------ inside
    def _offer(self, t, frame):
        t = float(t)
        if not math.isfinite(t):
            raise ValueError(f"frame time is not a number: {t}")
        if self._last_seen_t is not None and t > self._last_seen_t:
            self._source_s += t - self._last_seen_t
        self._last_seen_t = t
        last = self._last_sample_t
        if last is not None and 0 <= t - last < SAMPLE_SECONDS - SAMPLE_TOLERANCE:
            return False
        if last is not None and (t < last or t - last > S.MAX_SAMPLE_GAP):
            self._chests["dropped_at_break"] += len(self._pending)
            self._pending.clear()
            self._break_t = t
        self._last_sample_t = t
        picture = self._cues.picture_evidence(frame, self._picture)
        self._picture = picture.sample
        scores, health = self._reader.read(frame), self._cues.health_bar_pixels(frame)
        green = self._cues.health_bar_green_pixels(frame) if health >= S.HEALTH_BAR_MIN_PIXELS and hasattr(self._cues, "health_bar_green_pixels") else None
        pending, self._pending = self._pending, []
        chests, first_chest_t = tuple(language for language, _ in pending), min((t for _, t in pending), default=None)
        # The HUD only matters when nothing else shows the game: beside a health bar, a chest or any text it changes nothing, so it is not read.
        alone = health < S.HEALTH_BAR_MIN_PIXELS and not chests and max(scores.values(), default=0.0) < S.SCORE_THRESHOLD
        hud = self._reader.hud_in_view(frame) if alone else None
        self._chests["no_picture" if picture.black or picture.frozen else "delivered"] += len(chests)
        self._checkpoint(t, self._report(self._machine.update(S.Observation(t, scores, health, picture.black, picture.frozen, chests, hud, first_chest_t, green))))
        self._tell(t, picture)
        return True

    def _tell(self, t, picture):
        """If the app cannot be told, only its status line stops: recording carries on."""
        if self._status is None:
            return
        try:
            match = self._machine.snapshot()
            self._status(state=self._machine.state, t=round(t, 1), picture="black" if picture.black else "frozen" if picture.frozen else "live", match=match,
                         chests=self._credited(match["opened_t"], match["played_from_t"], None, self._out_at) if match else None, last_match=self._last_match())
        except Exception:
            self._status = None

    def _credited(self, opened_t, played_from_t, closed_t, out_at):
        """Chests belonging to one match, by each chest's own time: the rule of match_history.attribute, which a test holds this to. Reads only
        detected chests, so a Reset, Edit counts or manual correction cannot change it."""
        certain = approx = 0
        for t, is_certain, is_approx in self._counted:
            if opened_t <= t and played_from_t <= t and (closed_t is None or t < closed_t) and (out_at is None or t < out_at):
                certain += is_certain
                approx += is_approx
        return {"certain": certain, "approx": approx}

    def _last_match(self):
        """The final numbers of the match that closed last. Recounted each time, because the detector finishes a chest a few seconds late."""
        closed = self._closed
        if closed is None:
            return None
        moments = [moment for moment in (closed["out_at"], closed["ended_t"]) if moment is not None]
        return {**self._credited(closed["opened_t"], closed["played_from_t"], closed["closed_t"], min(moments) if moments else None),
                **{key: closed[key] for key in ("match_number", "completion", "ended_by", "reasons", "active_seconds", "english_confirmed")}}

    def _report(self, events):
        """-> True if a match opened or closed."""
        boundary = False
        for event in events:
            if isinstance(event, S.MatchRecord):
                record = event.to_dict()
                record["evidence"] = sorted(record["evidence"], key=lambda item: (item[0], item[1]))      # M2 gathers these from a set
                self._log("record", **record)
                if self._history is not None:
                    self._history.match_closed(record)
                self._closed, self._out_at = {**record, "out_at": self._out_at}, None
                boundary = True
            elif isinstance(event, S.Transition):
                self._log("transition", **asdict(event))
                if self._history is not None:
                    self._history.transition(asdict(event))
                if event.state == S.ELIMINATED and event.match_number is not None and self._out_at is None:
                    self._out_at = event.t
            else:
                self._log("opened", **asdict(event))
                if self._history is not None:
                    self._history.match_opened(asdict(event))
                self._out_at = None
                boundary = True
        return boundary

    def _checkpoint(self, t, boundary):
        if self._history is None:
            return
        last = self._last_beat_t
        if boundary or last is None or t < last or t - last >= self._beat_every - SAMPLE_TOLERANCE:
            self._last_beat_t = t
            processed, dropped = self._frames() if self._frames is not None else (None, None)
            self._history.heartbeat(t, processed, dropped, self._machine.snapshot())

    def _log(self, kind, **fields):
        self._write({"event": LOG_EVENT, "kind": kind, **fields})

    def _fail(self, where, error):
        self.failed = True
        self._pending.clear()
        detail = f"{type(error).__name__}: {error}"
        for report in (lambda: self._warn(f"match tracking stopped for this run ({detail}); counting is not affected"),
                       lambda: self._log("tracker_disabled", where=where, error=detail, last_t=self._last_seen_t),
                       lambda: self._status is not None and self._status(failed=True)):
            try:
                report()
            except Exception:
                pass
