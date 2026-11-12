"""
Personal Bests (v0.4.0, M3): your best match, rate, hour, session, day and week. Pure and derived every time from history, never stored, so
marking a match "Not a match", restoring it or undoing a correction changes them at the next refresh, and no number can drift.

Eligibility (D10), so that a best means something:
  * Match bests use Complete matches only (their start and the end of your part were both seen), never one marked "Not a match".
  * The best chests per minute needs 5 minutes of active play in that match, and uses the same counts as the per-minute rate (your +1s only
    when "Count my +1s" is ticked; your -1s always).
  * The best hour is 60 real minutes, all of them counted (progression.Snapshot.best_hour). A shorter session is never scaled up to an hour.
  * The best session rate needs a session of at least an hour.
  * Most broken chests in a match counts Complete and Partial matches, as you reported them.

Counts follow D3 like the rest of progress: detected chests plus your standing corrections, with the manual part reported beside each best.
A tie goes to the first time it was reached. A best of nothing (no chests) is no best at all: None, shown as a dash.
"""

from dataclasses import dataclass

from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import progression as P

MIN_RATE_ACTIVE_SECONDS = 300
MIN_SESSION_RATE_SECONDS = 3600
BESTS = (("match_chests", "Most chests in a match"), ("match_rate", "Best chests per minute"), ("hour", "Best hour"), ("day", "Best day"),
         ("week", "Best week"), ("session", "Most chests in a session"), ("session_rate", "Best session pace"), ("longest_session", "Longest session"),
         ("match_broken", "Most broken chests in a match"))


@dataclass(frozen=True)
class Best:
    key: str
    value: object                          # a count, a rate or seconds
    certain: object = None                 # CERTAIN beside it, where that applies
    start: object = None                   # when: a UTC datetime, or a date for a day or a week
    end: object = None
    seconds: object = None                 # how long it took
    manual_added: int = 0                  # your corrections inside it, already in the value
    manual_removed: int = 0
    cut_short: bool = False                # an interrupted run or lost history rows: it is "at least" this
    quality: object = None                 # for a match: complete / partial
    source: object = None                  # for a match: (run_id, match_number)


def _first(candidates, value, when):
    """The highest value, and among equals the earliest. -> the candidate or None."""
    best = None
    for item in candidates:
        if best is None or value(item) > value(best) or (value(item) == value(best) and when(item) < when(best)):
            best = item
    return best


def _match_when(match):
    return match.started_at.timestamp() if match.started_at is not None else float("inf")


def _match_best(key, match, value, certain):
    return Best(key, value, certain, match.started_at, None, match.duration_seconds, match.manual_added, match.manual_removed,
                bool(match.chests_may_be_missing or match.interrupted), match.quality, (match.run_id, match.match_number))


def personal_bests(snapshot, summary=None):
    """{key: Best or None} for every key in BESTS. `summary`: match_analytics.summarize of the same history, worked out here when not given."""
    if summary is None:
        summary = A.summarize(snapshot.history, include_manual=snapshot.include_manual)
    matches = [m for m in summary.all_matches if not m.excluded]
    complete = [m for m in matches if m.quality == A.COMPLETE]
    out = dict.fromkeys(key for key, _ in BESTS)

    best = _first([m for m in complete if m.approx > 0], lambda m: m.approx, _match_when)
    out["match_chests"] = best and _match_best("match_chests", best, best.approx, best.certain)
    rated = [m for m in complete if m.rate is not None and (m.active_seconds or 0) >= MIN_RATE_ACTIVE_SECONDS and m.rate.approx_per_minute > 0]
    best = _first(rated, lambda m: m.rate.approx_per_minute, _match_when)
    out["match_rate"] = best and _match_best("match_rate", best, best.rate.approx_per_minute, best.rate.certain_per_minute)
    broken = [m for m in matches if m.quality in (A.COMPLETE, A.PARTIAL) and m.broken_chests > 0]
    best = _first(broken, lambda m: m.broken_chests, _match_when)
    out["match_broken"] = best and _match_best("match_broken", best, best.broken_chests, None)

    hour = snapshot.best_hour()
    if hour is not None and hour.totals.recorded > 0:
        out["hour"] = Best("hour", hour.totals.recorded, hour.totals.certain, hour.start, hour.end, hour.covered_seconds, hour.totals.manual_added,
                           hour.totals.manual_removed)
    day = snapshot.best_day()
    if day is not None:
        out["day"] = Best("day", day.totals.recorded, day.totals.certain, day.day, None, day.counted_seconds, day.totals.manual_added, day.totals.manual_removed)
    week = snapshot.best_week()
    if week is not None:
        out["week"] = Best("week", week.recorded, sum(d.totals.certain for d in week.days), week.start, None, week.counted_seconds,
                           sum(d.totals.manual_added for d in week.days), sum(d.totals.manual_removed for d in week.days))

    rows = sorted(snapshot.session_rows(), key=lambda row: row.session.start)          # oldest first, so a tie goes to the first
    session = _first([r for r in rows if r.totals.recorded > 0], lambda r: r.totals.recorded, lambda r: r.session.start)
    out["session"] = session and _session_best("session", session, session.totals.recorded)
    paced = [r for r in rows if r.session.span_seconds >= MIN_SESSION_RATE_SECONDS and r.totals.recorded > 0]
    session = _first(paced, lambda r: r.per_hour, lambda r: r.session.start)
    out["session_rate"] = session and _session_best("session_rate", session, session.per_hour)
    session = _first([r for r in rows if r.session.span_seconds > 0], lambda r: r.session.span_seconds, lambda r: r.session.start)
    out["longest_session"] = session and _session_best("longest_session", session, session.session.span_seconds)
    return out


@dataclass(frozen=True)
class Analytics:
    """Everything the Analytics page shows, from one read of history."""
    summary: object                        # match_analytics.Summary of every match
    snapshot: object                       # progression.Snapshot
    periods: dict                          # period key -> progression.Progress
    bests: dict                            # BESTS key -> Best or None


def load(folder, now=None, zone=None, counting_now=False, include_manual=False):
    """One profile's Analytics. Slow on a very large history (about two seconds for a heavy year), so the app calls it off its window's thread."""
    snapshot = P.load(folder, now=now, zone=zone, counting_now=counting_now, include_manual=include_manual)
    summary = A.summarize(snapshot.history, include_manual=include_manual)
    return Analytics(summary, snapshot, {key: snapshot.progress(key) for key, _ in P.PERIODS}, personal_bests(snapshot, summary))


def _session_best(key, row, value):
    s = row.session
    return Best(key, value, row.totals.certain, s.start, s.end, s.span_seconds, row.totals.manual_added, row.totals.manual_removed, s.cut_short)
