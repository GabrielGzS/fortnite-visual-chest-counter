"""
Descriptive statistics from match history (v0.3.0, M8). Pure: it takes what match_history.read returned and gives back numbers. It writes nothing,
and history never replaces the counter's totals, which stay the official numbers.

What it will not do:
  * Invent a value. Anything unknown is None, which the app shows as a dash; zero always means a real zero.
  * Average what cannot be compared. Complete, partial and unconfirmed matches are counted apart, and unconfirmed ones stay out of every statistic.
  * Mix the two chest rates. The complete rate uses complete matches only and is the headline. The observed rate also includes partial matches and
    measures only what was seen. Each needs enough play to mean anything, and one never stands in for the other.
  * Use a match whose history lost chests in either rate: its count would be too low.
  * Add CERTAIN to APPROX. APPROX is the total and already includes CERTAIN.
  * Claim an outcome. An ending is reported only as it was observed; placement numbers are not read.
  * Call the waiting island a match. A record the countdown proved was the island stays in history but is in no count, list or statistic.

Rates are total chests divided by total active minutes, not an average of per-match rates, so a short match cannot outweigh a long one.
Which chests belong to which match comes from match_history.attribute: only chests during active play are credited.

Manual corrections made for a match (the Game view's +1 and -1) belong to it. Its APPROX count always includes them, like the counter's total.
In its statistics a -1 always counts, since it takes off a chest the detector should not have counted, and a +1 only with include_manual: it is
a chest the detector did not see (a broken chest, say), so by default the rates stay what the detector measured.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fortnite_chest_counter import match_history as H

COMPLETE, PARTIAL, UNCONFIRMED = "complete", "partial", "unconfirmed"
QUALITIES = (COMPLETE, PARTIAL, UNCONFIRMED)
MIN_OBSERVED_RATE_SECONDS = 300            # under five minutes of play, a chest more or less would swing the rate wildly
MIN_COMPLETE_RATE_SECONDS = 300            # the same, across all complete matches together: short matches still count towards it
MIN_MATCH_RATE_SECONDS = 60                # one match, live or in the list: under a minute of play the figure says nothing yet
RECENT_MATCHES = 25
READ_KINDS = H.MATCH_KINDS | H.CORRECTION_KINDS | {"transition", "counter_change", "chest", "chest_type"}      # everything but the heartbeats, which are most of the file
ENDINGS = {"placed": "Placed", "victory": "Victory Royale", "left_or_unknown": "Left or not seen", "stopped": "Counting stopped", "lost": "Video lost",
           "discontinuity": "Video jumped", H.INTERRUPTED: "App closed unexpectedly"}
# A match that ended with no YOU PLACED or Victory on screen, by what was seen next. It says where play went, never why: quitting, a disconnect and an
# ending the app missed all look the same.
LEFT_ENDINGS = {"menu_seen": "Returned to lobby", "connecting_seen": "Left the match", "next match countdown seen": "Next match began"}
WAITING_ISLAND = "waiting island"          # match_state's reason for a record the countdown proved was never a match


@dataclass
class Rate:
    certain_per_minute: float
    approx_per_minute: float
    matches: int
    minutes: float


@dataclass
class PerMatch:
    certain: float
    approx: float
    matches: int


@dataclass
class RecentMatch:
    started_at: object                     # a datetime, or None when the run's start is not known
    duration_seconds: object
    duration_is_full: bool                 # True: the whole match, start to ending. False: only what was seen of it
    certain: int
    approx: int
    chests_may_be_missing: bool
    quality: str
    interrupted: bool
    ending: str
    run_id: object = None
    match_number: object = None
    excluded: bool = False                 # marked "Not a match": shown so it can be restored, left out of every statistic
    rate: object = None                    # a Rate for this match alone, or None when one is not defensible
    manual_added: int = 0                  # your +1s and -1s made for this match, still standing; approx above already includes them
    manual_removed: int = 0
    broken_chests: int = 0                 # of those +1s, the ones you said were broken chests
    active_seconds: object = None          # alive on the bus or the map (v0.4.0, for Personal Bests)


@dataclass
class Summary:
    complete: int = 0
    partial: int = 0
    unconfirmed: int = 0
    excluded: int = 0                      # marked "Not a match"
    unfinished: int = 0                    # opened and never closed, so not counted yet
    observed_seconds: object = None        # complete and partial matches: on screen, from first evidence to the close
    confirmed_seconds: object = None       # complete matches: alive on the map
    unconfirmed_seconds: object = None     # left out of observed_seconds
    session_seconds: object = None         # time spent counting, in or out of matches
    sessions: int = 0
    sessions_cut_short: int = 0            # their time is only known up to the last checkpoint
    certain_chests: int = 0                # every chest in history, credited or not
    approx_chests: int = 0
    credited_certain: int = 0              # during active play in complete and partial matches
    credited_approx: int = 0
    per_complete_match: object = None
    complete_rate: object = None
    observed_rate: object = None
    matches_left_out_of_rates: int = 0     # history lost chests during them, or no active time is known
    missing_certain: int = 0               # gap rows: chests the totals have and history does not
    missing_approx: int = 0
    manual_added: int = 0                  # the user's +1s and -1s still standing, on the counter
    manual_removed: int = 0
    include_manual: bool = False           # whether +1s made for a match count in its statistics; -1s made for a match always do
    waiting_islands: int = 0               # records the countdown proved were the waiting island: kept in history, no match
    broken_chests: int = 0                 # +1s you said were broken chests, made for complete and partial matches: reported by you, not detected
    broken_per_complete_match: object = None   # their average over complete matches, or None without one
    damaged_rows: int = 0
    newer_rows: int = 0
    recent: list = field(default_factory=list)
    all_matches: list = field(default_factory=list)    # every match `recent` is taken from, newest first (v0.4.0, for Personal Bests)

    @property
    def matches(self):
        return self.complete + self.partial + self.unconfirmed

    @property
    def empty(self):
        return not (self.matches or self.sessions or self.certain_chests or self.approx_chests)


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _usable(match):
    return (match.get("completion") in QUALITIES and all(_number(match.get(key)) is not None for key in ("opened_t", "played_from_t", "closed_t"))
            and (match.get("ended_t") is None or _number(match.get("ended_t")) is not None))


def _total(rows, key):
    """A sum, or None when there is nothing known to add: no value is not the same as zero."""
    values = [_number(row.get(key)) for row in rows]
    known = [value for value in values if value is not None and value >= 0]
    return sum(known) if known else None


def _started_at(run, match):
    try:
        return datetime.fromisoformat(run["start"]["at"]) + timedelta(seconds=match["opened_t"])
    except (TypeError, KeyError, ValueError, OverflowError):
        return None


def _rate(matches, credited, enough_seconds=0):
    """Total chests over total active minutes, or None when no match qualifies or there is too little play."""
    seconds = sum(match["active_seconds"] for match in matches)
    if not matches or seconds <= 0 or seconds < enough_seconds:
        return None
    minutes = seconds / 60
    keys = [(match["run_id"], match["match_number"]) for match in matches]
    return Rate(sum(credited[key][0] for key in keys) / minutes, sum(credited[key][1] for key in keys) / minutes, len(matches), minutes)


def match_rate(certain, approx, active_seconds):
    """One match's chests per minute of active play, the denominator the summary rates use. None until there is enough play to mean anything."""
    active = _number(active_seconds)
    if active is None or active < MIN_MATCH_RATE_SECONDS:
        return None
    minutes = active / 60
    return Rate(certain / minutes, approx / minutes, 1, minutes)


def ending_text(match):
    """How a match ended, as far as was seen."""
    ended_by, reasons = match.get("ended_by"), match.get("reasons") or ()
    if WAITING_ISLAND in reasons:
        return "Waiting island"
    if ended_by == "left_or_unknown" and reasons and reasons[-1] in LEFT_ENDINGS:
        return LEFT_ENDINGS[reasons[-1]]
    return ENDINGS.get(ended_by, "Not seen")


def is_waiting_island(match):
    return WAITING_ISLAND in (match.get("reasons") or ())


def summarize(history, recent=RECENT_MATCHES, include_manual=False):
    every = [match for match in history.matches if _usable(match)]
    usable = [match for match in every if not is_waiting_island(match)]
    chests = [chest for chest in history.chests if _number(chest.get("t")) is not None]
    transitions = [row for row in history.transitions if _number(row.get("t")) is not None and "state" in row and "match_number" in row]
    summary = Summary(unfinished=len(history.open_matches), newer_rows=history.newer_rows, include_manual=bool(include_manual), waiting_islands=len(every) - len(usable),
                      damaged_rows=history.bad_lines + len(history.matches) - len(every) + len(history.chests) - len(chests) + len(history.transitions) - len(transitions))

    credited = {(match["run_id"], match["match_number"]): [0, 0] for match in every}
    for chest in H.attribute(H.History(matches=every, chests=chests, transitions=transitions)):        # the island still owns its moments
        certain, approx = bool(chest.get("certain_counted")), bool(chest.get("approx_counted") or chest.get("certain_counted"))
        summary.certain_chests += certain
        summary.approx_chests += approx
        if chest["credited"]:
            totals = credited[chest["run_id"], chest["match_number"]]
            totals[0] += certain
            totals[1] += approx

    # Corrections made for a match. Statistics take a -1 always and a +1 only when asked; the count shown takes both, like the counter.
    for_match = {key: value for key, value in H.corrections_by_match(history.chest_corrections).items() if key in credited}
    shown, stats = {}, {}
    for key, (certain, approx) in credited.items():
        added, removed, _ = for_match.get(key, (0, 0, 0))
        shown[key] = [certain, max(approx + added - removed, certain)]
        stats[key] = [certain, max(approx - removed + (added if include_manual else 0), certain)]

    kept = [match for match in usable if not match["not_a_match"]]
    summary.excluded = len(usable) - len(kept)
    complete = [match for match in kept if match["completion"] == COMPLETE]
    partial = [match for match in kept if match["completion"] == PARTIAL]
    unconfirmed = [match for match in kept if match["completion"] == UNCONFIRMED]
    summary.complete, summary.partial, summary.unconfirmed = len(complete), len(partial), len(unconfirmed)
    summary.observed_seconds = _total(complete + partial, "observed_seconds")
    summary.confirmed_seconds = _total(complete, "active_seconds")
    summary.unconfirmed_seconds = _total(unconfirmed, "observed_seconds")

    summary.broken_chests = sum(for_match.get((m["run_id"], m["match_number"]), (0, 0, 0))[2] for m in complete + partial)
    if complete:
        summary.broken_per_complete_match = sum(for_match.get((m["run_id"], m["match_number"]), (0, 0, 0))[2] for m in complete) / len(complete)
    for match in complete + partial:
        totals = stats[match["run_id"], match["match_number"]]
        summary.credited_certain += totals[0]
        summary.credited_approx += totals[1]

    def rate_ready(match):
        active = _number(match.get("active_seconds"))
        return active is not None and active > 0 and not match["history_incomplete"]

    complete_ready, seen_ready = [m for m in complete if rate_ready(m)], [m for m in complete + partial if rate_ready(m)]
    summary.matches_left_out_of_rates = len(complete + partial) - len(seen_ready)
    summary.complete_rate = _rate(complete_ready, stats, MIN_COMPLETE_RATE_SECONDS)
    summary.observed_rate = _rate(seen_ready, stats, MIN_OBSERVED_RATE_SECONDS)
    if complete_ready:
        keys = [(match["run_id"], match["match_number"]) for match in complete_ready]
        summary.per_complete_match = PerMatch(sum(stats[key][0] for key in keys) / len(keys), sum(stats[key][1] for key in keys) / len(keys), len(keys))

    known_sessions = []
    for run in history.runs.values():
        if run["start"] is None:
            continue
        summary.sessions += 1
        end = run["end"] or {}
        seconds = _number(end.get("elapsed_seconds"))
        if seconds is None:
            summary.sessions_cut_short += 1
            seconds = _number(end.get("t"))
        if seconds is not None and seconds >= 0:
            known_sessions.append(seconds)
    summary.session_seconds = sum(known_sessions) if known_sessions else None

    for gap in history.gaps:
        summary.missing_certain += max(_number(gap.get("missing_certain")) or 0, 0)
        summary.missing_approx += max(_number(gap.get("missing_approximate")) or 0, 0)

    manual = H.correction_totals(history.chest_corrections)
    summary.manual_added, summary.manual_removed = manual["added"], manual["removed"]

    for match in reversed(usable):
        run = history.runs.get(match["run_id"]) or {"start": None}
        full = match["completion"] == COMPLETE and _number(match.get("complete_duration_seconds")) is not None
        key = (match["run_id"], match["match_number"])
        totals, figures, (added, removed, broken) = shown[key], stats[key], for_match.get(key, (0, 0, 0))
        fair = rate_ready(match) and match["completion"] != UNCONFIRMED and not match["not_a_match"]              # the same matches the summary rates accept
        summary.all_matches.append(RecentMatch(_started_at(run, match), _number(match.get("complete_duration_seconds" if full else "observed_seconds")), full, totals[0], totals[1],
                                               bool(match["history_incomplete"]), match["completion"], bool(match.get("interrupted")), ending_text(match),
                                               match["run_id"], match["match_number"], bool(match["not_a_match"]),
                                               match_rate(figures[0], figures[1], match.get("active_seconds")) if fair else None, added, removed, broken,
                                               _number(match.get("active_seconds"))))
    summary.recent = summary.all_matches[:recent]
    return summary


def load(folder, include_manual=False):
    """The summary of one profile's history. Slow on a very large history, so the app calls it off its window's thread."""
    return summarize(H.read(folder, only=READ_KINDS), include_manual=include_manual)


def duration_text(seconds):
    """"7h 42m", "12m 30s", "45s", or a dash for an unknown time."""
    if _number(seconds) is None or seconds < 0:
        return None
    seconds = int(seconds)
    hours, minutes, rest = seconds // 3600, seconds // 60 % 60, seconds % 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {rest:02d}s" if minutes else f"{rest}s"
