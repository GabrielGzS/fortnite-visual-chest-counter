"""
Real-life time from history (v0.4.0, M1): when the app was counting, how runs group into sessions, and how both fall on calendar days and
weeks. Pure: it takes a history as the history reader returns it and gives back intervals. It writes nothing and invents nothing.

Kinds of time, never mixed:
  * time counting    inside runs, by the wall clock (a run's own elapsed time when it ended cleanly)
  * session time     runs joined while the gap between them is under BREAK_SECONDS, from the first start to the last end. The gaps are real time
                     that passed, not an observation: nothing is known about what happened in them
  * unobserved gap   session time minus time counting
  * active play      match_state's alive-on-the-bus-or-map time; it comes from match rows (match_analytics), not from here

Rules that keep it honest:
  * A run that ended cleanly lasts its own `elapsed_seconds` from its start, which a change of the PC's clock cannot stretch.
  * A run that did not end cleanly lasts only until history last saw it (its last heartbeat): "at least", never longer. The run_end row that
    recovery writes later carries the time of that recovery, possibly days afterwards, so its `at` is never an end; its `last_seen_at` is.
  * The run counting right now lasts until now.
  * `simulate` (a developer command) replays a file faster than real time. Its wall clock is nobody's play, so its runs are left out.
  * All arithmetic is done in UTC. Days are local calendar days by the PC's time zone rules at each moment (or the zone given, for tests), so
    a 23- or 25-hour day around a daylight-saving change is measured as it was. Weeks start on Monday.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

BREAK_SECONDS = 30 * 60                    # D2: runs closer than this belong to one session
CLOCK_TOLERANCE_SECONDS = 120              # a clean run whose wall clock and own elapsed time differ by more had its clock changed
LEFT_OUT_SOURCES = frozenset({"simulate"})
UTC = timezone.utc


def parse_at(text):
    """A row's `at` as a UTC datetime, or None. A time without its UTC offset is not guessed at."""
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment.astimezone(UTC) if moment.utcoffset() is not None else None


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def seconds_between(a, b):
    return (b - a).total_seconds()


@dataclass(frozen=True)
class Run:
    run_id: str
    source_type: object
    start: datetime                        # UTC
    end: datetime                          # UTC; for a run that did not end cleanly, the last moment it was seen
    ended_cleanly: bool
    in_progress: bool = False
    clock_changed: bool = False

    @property
    def seconds(self):
        return seconds_between(self.start, self.end)

    @property
    def cut_short(self):
        """It ended without a clean stop, so it lasted at least this long and possibly a little longer."""
        return not self.ended_cleanly and not self.in_progress


@dataclass
class Session:
    runs: list = field(default_factory=list)

    @property
    def start(self):
        return self.runs[0].start

    @property
    def end(self):
        return max(run.end for run in self.runs)

    @property
    def span_seconds(self):
        return seconds_between(self.start, self.end)

    @property
    def counted_seconds(self):
        return sum(seconds_between(a, b) for a, b in merged((run.start, run.end) for run in self.runs))

    @property
    def gap_seconds(self):
        return max(self.span_seconds - self.counted_seconds, 0.0)

    @property
    def cut_short(self):
        return any(run.cut_short for run in self.runs)

    @property
    def in_progress(self):
        return any(run.in_progress for run in self.runs)

    def intervals(self):
        return merged((run.start, run.end) for run in self.runs)


def runs(history, heartbeats=None, now=None, running=None):
    """Every run with a known start, as wall-clock intervals, oldest first. `heartbeats`: the last heartbeat rows (history.last_heartbeats) of runs that never ended
    (history.runs carries a last heartbeat only when heartbeats were read). `running`: the id of the run counting now, which lasts until `now`."""
    heartbeats = heartbeats or {}
    now = (now or datetime.now(UTC)).astimezone(UTC)
    out = []
    for run_id, run in history.runs.items():
        start_row = run.get("start")
        if not start_row:
            continue
        start = parse_at(start_row.get("at"))
        source = start_row.get("source_type")
        if start is None or source in LEFT_OUT_SOURCES:
            continue
        end_row, clean, in_progress, changed = run.get("end"), False, False, False
        if end_row and not end_row.get("interrupted"):
            elapsed, at_end = _number(end_row.get("elapsed_seconds")), parse_at(end_row.get("at"))
            if elapsed is not None and elapsed >= 0:
                end, clean = start + timedelta(seconds=elapsed), True
                changed = at_end is not None and abs(seconds_between(start, at_end) - elapsed) > CLOCK_TOLERANCE_SECONDS
            elif at_end is not None:
                end, clean = at_end, True
            else:
                end = start
        elif end_row:                                      # written by recovery: its own `at` is when recovery ran, never the end
            end = parse_at(end_row.get("last_seen_at")) or start
        elif run_id == running:
            end, in_progress = now, True
        else:                                              # not ended and not recovered yet
            beat = heartbeats.get(run_id) or run.get("last_heartbeat")
            end = parse_at(beat.get("at")) if beat else None
            end = end or start
        out.append(Run(run_id, source, start, max(end, start), clean, in_progress, changed))
    out.sort(key=lambda r: r.start)
    return out


def merged(intervals):
    """Overlapping or touching intervals joined. -> [(start, end)] in order."""
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def sessions(all_runs, break_seconds=BREAK_SECONDS):
    """Runs grouped while each starts less than `break_seconds` after the group's end so far."""
    out = []
    for run in sorted(all_runs, key=lambda r: r.start):
        if out and seconds_between(out[-1].end, run.start) < break_seconds:
            out[-1].runs.append(run)
        else:
            out.append(Session([run]))
    return out


# ---------------------------------------------------------------------- calendar

def local(moment, zone=None):
    """The local time of a UTC moment: the PC's time zone rules at that moment, or `zone`."""
    return moment.astimezone(zone) if zone is not None else moment.astimezone()


def day_of(moment, zone=None):
    return local(moment, zone).date()


def day_start(day, zone=None):
    """Local midnight at the start of `day`, as a UTC moment. Midnight is never skipped or repeated by daylight saving where this app is used;
    if a zone did, the earlier reading is taken."""
    naive = datetime.combine(day, time())
    aware = naive.astimezone() if zone is None else naive.replace(tzinfo=zone)
    return aware.astimezone(UTC)


def week_start(day):
    """The Monday of `day`'s calendar week (D5)."""
    return day - timedelta(days=day.weekday())


def days_from(first, last):
    """Every calendar day from `first` to `last`, both included."""
    return [first + timedelta(days=n) for n in range((last - first).days + 1)] if last >= first else []


def split_by_day(start, end, zone=None):
    """[(day, seconds)] of the interval on each local day it touches."""
    out, cursor = [], start
    while cursor < end:
        day = day_of(cursor, zone)
        boundary = min(day_start(day + timedelta(days=1), zone), end)
        if boundary <= cursor:                             # cannot happen with a sane zone; never loop forever
            boundary = end
        out.append((day, seconds_between(cursor, boundary)))
        cursor = boundary
    return out


def counted_by_day(all_runs, zone=None):
    """{day: seconds counting}, from the runs merged so overlaps are not counted twice."""
    out = {}
    for start, end in merged((run.start, run.end) for run in all_runs):
        for day, seconds in split_by_day(start, end, zone):
            out[day] = out.get(day, 0.0) + seconds
    return out


def clip(intervals, start, end):
    """The parts of the intervals between `start` and `end`."""
    out = []
    for a, b in intervals:
        a, b = max(a, start), min(b, end)
        if a < b:
            out.append((a, b))
    return out


def total_seconds(intervals):
    return sum(seconds_between(a, b) for a, b in intervals)
