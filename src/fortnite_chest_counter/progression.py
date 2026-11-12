"""
Real-life progress from history (v0.4.0, M2): chests per hour of real life, per day and per week, and the current and best hour. Pure: it takes a
history as the history reader returns it and gives back numbers. It writes nothing, and the counter's totals stay the official numbers.

What is counted (D3, D4):
  * Recorded chests: every chest the detector counted, plus your +1s and minus your -1s that still stand (an undone correction never happened),
    each dated by its own `at`. Reset, Edit counts and a starting count are not chests and never appear here.
  * A chest seen while spectating (after you were out of a recognised Complete or Partial match that is not marked "Not a match") is someone
    else's: it is left out and counted apart. Anywhere attribution is uncertain, the chest counts. Its row and your totals are never touched.
  * Runs of the developer `simulate` command, with their chests and corrections, are nobody's play (timeline.LEFT_OUT_SOURCES).

How time is measured (timeline.py):
  * Chests per hour divide the recorded chests inside sessions by session time (D1): breaks, queues and the lobby are real life. A session's
    gaps are time that passed, never time observed; they are reported apart. It is never chests per minute of play times sixty.
  * Days and weeks: local calendar days from midnight, weeks from Monday (D5, D6). A day with counting and no chests is a known zero; a day
    with no counting is not counted, never a zero. Averages are given per monitored, active and calendar day (or week), over completed days only.
  * The best hour is the most recorded chests in a 60-minute window lying entirely inside time counting. A shorter session is never scaled up.

Unknown is None, which the app shows as a dash. Zero always means a real zero.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import timeline as TL

HOUR_SECONDS = 3600
MIN_HOURLY_SECONDS = 30 * 60               # chests per hour needs half an hour of session time
COVERAGE_TOLERANCE_SECONDS = 120           # runs this close together count as one stretch of counting for the rolling hour (an app restart)
DETECTOR_DELAY_SECONDS = 10                # a chest is finished a few seconds after its pop-up: still inside the match that just closed
RELIABLE_FOR_SPECTATING = (A.COMPLETE, A.PARTIAL)
PERIODS = (("today", "Today"), ("week", "This week"), ("last7", "Last 7 days"), ("last30", "Last 30 days"), ("all", "All time"))
UTC = timezone.utc
TICK = timedelta(microseconds=1)


@dataclass(frozen=True)
class Event:
    """One change to the recorded total."""
    at: datetime                           # UTC
    delta: int                             # +1, or -1 for a standing -1
    manual: bool
    certain: bool = False
    reason: object = None


@dataclass
class Totals:
    recorded: int = 0                      # detected + your standing corrections: the APPROX side
    detected: int = 0
    certain: int = 0
    manual_added: int = 0
    manual_removed: int = 0

    def add(self, event):
        self.recorded += event.delta
        if event.manual:
            self.manual_added += event.delta > 0
            self.manual_removed += event.delta < 0
        else:
            self.detected += 1
            self.certain += event.certain


@dataclass
class Day:
    day: object                            # a date
    counted_seconds: float = 0.0
    totals: Totals = field(default_factory=Totals)

    @property
    def monitored(self):
        return self.counted_seconds > 0

    @property
    def active(self):
        return self.totals.recorded > 0

    @property
    def status(self):
        """"chests", "zero" (counted, none found: a known zero) or "not_counted" (unobserved, never a zero)."""
        return "chests" if self.active else "zero" if self.monitored else "not_counted"


@dataclass
class Week:
    start: object                          # the Monday
    days: list = field(default_factory=list)

    @property
    def recorded(self):
        return sum(day.totals.recorded for day in self.days)

    @property
    def counted_seconds(self):
        return sum(day.counted_seconds for day in self.days)

    @property
    def monitored(self):
        return any(day.monitored for day in self.days)

    @property
    def active(self):
        return self.recorded > 0


@dataclass(frozen=True)
class Averages:
    """Over completed days (or weeks). Each is None when there is nothing to divide by."""
    per_monitored: object
    per_active: object
    per_calendar: object
    monitored: int
    active: int
    calendar: int
    not_counted: int                       # calendar days (weeks) with no counting and no chests


@dataclass(frozen=True)
class Window:
    """A stretch of real time and the recorded chests in it."""
    start: datetime
    end: datetime
    totals: Totals
    covered_seconds: float                 # time counting inside it


@dataclass
class SessionRow:
    session: object                        # a timeline.Session
    totals: Totals

    @property
    def per_hour(self):
        span = self.session.span_seconds
        return self.totals.recorded / (span / HOUR_SECONDS) if span >= MIN_HOURLY_SECONDS else None


@dataclass
class Progress:
    """One period."""
    key: str
    label: str
    start: datetime
    end: datetime
    totals: Totals                         # every recorded chest in the period, in sessions or not (a +1 made after stopping, say)
    in_sessions: int                       # recorded chests inside the period's sessions: what chests per hour divides
    session_seconds: float
    counting_seconds: float
    active_seconds: object                 # None: no recognised match in the period
    active_is_lower_bound: bool            # some play was not recognised (chests outside matches, unconfirmed matches)
    spectating_left_out: int
    sessions: int
    cut_short: bool                        # a run in it ended without a clean stop: times are "at least"
    match_summary: object                  # match_analytics.Summary of the matches that started in the period

    @property
    def gap_seconds(self):
        return max(self.session_seconds - self.counting_seconds, 0.0)

    @property
    def between_matches_seconds(self):
        return None if self.active_seconds is None else max(self.counting_seconds - self.active_seconds, 0.0)

    @property
    def per_hour(self):
        if self.session_seconds < MIN_HOURLY_SECONDS:
            return None
        return self.in_sessions / (self.session_seconds / HOUR_SECONDS)


class Snapshot:
    """Everything the time-based views need, worked out once from one read of history."""

    def __init__(self, history, heartbeats=None, now=None, zone=None, counting_now=False, include_manual=False, break_seconds=TL.BREAK_SECONDS):
        self.zone, self.include_manual, self.history = zone, include_manual, history
        self.now = (now or datetime.now(UTC)).astimezone(UTC)
        self.runs = TL.runs(history, heartbeats, now=self.now, running=self._running(history) if counting_now else None)
        self.sessions = TL.sessions(self.runs, break_seconds)
        self._counted = TL.merged((run.start, run.end) for run in self.runs)
        left_out_runs = {run_id for run_id, run in history.runs.items() if (run.get("start") or {}).get("source_type") in TL.LEFT_OUT_SOURCES}
        self.events, self.spectated, self.unknown_time = self._events(history, left_out_runs)
        self._times = [event.at for event in self.events]
        self._sums = [0]                                   # recorded total before each event, for counting any window at once
        for event in self.events:
            self._sums.append(self._sums[-1] + event.delta)
        self._matches = self._placed_matches(history, left_out_runs)
        self.today = TL.day_of(self.now, zone)
        self.first_day = self._first_day()
        self.days = self._days()

    @staticmethod
    def _running(history):
        """One counter at a time: the newest run that has not ended is the one counting now."""
        unended = [(TL.parse_at(run["start"].get("at")), run_id) for run_id, run in history.runs.items() if run.get("start") and run.get("end") is None]
        unended = [item for item in unended if item[0] is not None]
        return max(unended)[1] if unended else None

    # ------------------------------------------------------------------ building
    def _events(self, history, left_out_runs):
        reliable = [m for m in history.matches if A._usable(m) and not A.is_waiting_island(m) and not m["not_a_match"]
                    and m.get("english_confirmed") is True and m["completion"] in RELIABLE_FOR_SPECTATING]
        chests = [c for c in history.chests if A._number(c.get("t")) is not None]
        transitions = [row for row in history.transitions if A._number(row.get("t")) is not None and "state" in row and "match_number" in row]
        events, spectated, unknown = [], [], 0
        for chest in H.attribute(H.History(matches=reliable, chests=chests, transitions=transitions)):
            if chest.get("run_id") in left_out_runs:
                continue
            at = TL.parse_at(chest.get("at"))
            if at is None:
                unknown += 1
            elif chest["spectating"]:
                spectated.append(at)
            else:
                events.append(Event(at, 1, False, bool(chest.get("certain_counted"))))
        for correction in history.chest_corrections:
            if correction["undone"] or correction.get("run_id") in left_out_runs:
                continue
            at = TL.parse_at(correction.get("at"))
            if at is None:
                unknown += 1
            else:
                events.append(Event(at, correction["delta"], True, False, correction.get("reason")))
        events.sort(key=lambda event: event.at)
        spectated.sort()
        return events, spectated, unknown

    def _placed_matches(self, history, left_out_runs):
        """[(wall-clock start of play, wall-clock open, wall-clock close, match)] for every usable match that is not the island."""
        out = []
        for match in history.matches:
            if not A._usable(match) or A.is_waiting_island(match) or match.get("run_id") in left_out_runs:
                continue
            start = TL.parse_at(((history.runs.get(match["run_id"]) or {}).get("start") or {}).get("at"))
            if start is not None:
                out.append((start + timedelta(seconds=match["played_from_t"]), start + timedelta(seconds=match["opened_t"]),
                            start + timedelta(seconds=match["closed_t"]), match))
        out.sort(key=lambda item: item[0])
        return out

    def _first_day(self):
        moments = [run.start for run in self.runs] + self._times[:1]
        return TL.day_of(min(moments), self.zone) if moments else None

    def _days(self):
        if self.first_day is None:
            return []
        days = {day: Day(day) for day in TL.days_from(self.first_day, max(self.today, self.first_day))}
        for day, seconds in TL.counted_by_day(self.runs, self.zone).items():
            if day in days:
                days[day].counted_seconds += seconds
        for event in self.events:
            day = days.get(TL.day_of(event.at, self.zone))
            if day is not None:
                day.totals.add(event)
        return [days[day] for day in sorted(days)]

    # ------------------------------------------------------------------ counting events
    def _recorded(self, start, end):
        """The recorded total of the events with start <= at < end."""
        return self._sums[bisect_left(self._times, end)] - self._sums[bisect_left(self._times, start)]

    def _totals(self, start, end):
        totals = Totals()
        for event in self.events[bisect_left(self._times, start):bisect_left(self._times, end)]:
            totals.add(event)
        return totals

    # ------------------------------------------------------------------ periods
    def period_bounds(self, key):
        today = self.today
        first = {"today": today, "week": TL.week_start(today), "last7": today - timedelta(days=6), "last30": today - timedelta(days=29),
                 "all": self.first_day or today}[key]
        return TL.day_start(first, self.zone), self.now + TICK

    def progress(self, key):
        start, end = self.period_bounds(key)
        sessions = [s for s in self.sessions if s.end >= start and s.start < end]
        spans = TL.clip([(s.start, s.end + TICK) for s in sessions], start, end)
        in_sessions = sum(self._recorded(a, b) for a, b in spans)
        session_seconds = sum(TL.total_seconds(TL.clip([(s.start, s.end)], start, end)) for s in sessions)
        counting = TL.total_seconds(TL.clip(self._counted, start, end))
        placed = [item for item in self._matches if start <= item[0] < end]
        recognised = [item for item in placed if not item[3]["not_a_match"] and item[3]["completion"] in (A.COMPLETE, A.PARTIAL)]
        active = sum(A._number(item[3].get("active_seconds")) or 0.0 for item in recognised) if recognised else None
        lower_bound = any(item[3]["completion"] == A.UNCONFIRMED for item in placed) or self._chests_outside(recognised, start, end)
        wanted = {id(item[3]) for item in placed}
        summary = A.summarize(H.History(matches=[m for m in self.history.matches if id(m) in wanted], chests=self.history.chests,
                                        transitions=self.history.transitions, chest_corrections=self.history.chest_corrections),
                              include_manual=self.include_manual)
        spectated = bisect_left(self.spectated, end) - bisect_left(self.spectated, start)
        return Progress(key, dict(PERIODS)[key], start, end, self._totals(start, end), in_sessions, session_seconds, counting, active, lower_bound,
                        spectated, len(sessions), any(s.cut_short for s in sessions), summary)

    def _chests_outside(self, recognised, start, end):
        """True if a detected chest in the period fell outside every recognised match: play the match tracker did not see."""
        spans = TL.merged((opened, closed + timedelta(seconds=DETECTOR_DELAY_SECONDS)) for _, opened, closed, _ in recognised)
        index = 0
        for event in self.events[bisect_left(self._times, start):bisect_left(self._times, end)]:
            if event.manual:
                continue
            while index < len(spans) and spans[index][1] < event.at:
                index += 1
            if index == len(spans) or event.at < spans[index][0]:
                return True
        return False

    # ------------------------------------------------------------------ days and weeks
    def day(self, offset=0):
        """Today (0), yesterday (-1), ...: a Day, or None before the first recorded day."""
        wanted = self.today + timedelta(days=offset)
        return next((day for day in self.days if day.day == wanted), None)

    def last_days(self, count):
        """The last `count` calendar days including today, oldest first; days before history began are left out."""
        first = self.today - timedelta(days=count - 1)
        return [day for day in self.days if day.day >= first]

    def weeks(self):
        out = {}
        for day in self.days:
            out.setdefault(TL.week_start(day.day), Week(TL.week_start(day.day))).days.append(day)
        return [out[start] for start in sorted(out)]

    def this_week(self):
        weeks = self.weeks()
        return weeks[-1] if weeks and weeks[-1].start == TL.week_start(self.today) else None

    def day_averages(self, days=None):
        """Over completed days only: today is still going."""
        done = [day for day in (self.days if days is None else days) if day.day < self.today]
        return _averages([(d.totals.recorded, d.monitored, d.active) for d in done])

    def week_averages(self):
        """Over completed calendar weeks. The calendar figure is the calendar-day average times seven over the same days, so a history that
        began mid-week is not read as a short week."""
        this_monday = TL.week_start(self.today)
        done = [week for week in self.weeks() if week.start < this_monday]
        weeks = _averages([(w.recorded, w.monitored, w.active) for w in done])
        days = self.day_averages([day for day in self.days if day.day < this_monday])
        return Averages(weeks.per_monitored, weeks.per_active, days.per_calendar * 7 if days.per_calendar is not None else None,
                        weeks.monitored, weeks.active, weeks.calendar, weeks.not_counted)

    def best_day(self):
        days = [day for day in self.days if day.active]
        return max(days, key=lambda day: (day.totals.recorded, -day.day.toordinal())) if days else None

    def best_week(self):
        weeks = [week for week in self.weeks() if week.active]
        return max(weeks, key=lambda week: (week.recorded, -week.start.toordinal())) if weeks else None

    # ------------------------------------------------------------------ sessions and hours
    def session_rows(self):
        """Newest first."""
        return [SessionRow(session, self._totals(session.start, session.end + TICK)) for session in reversed(self.sessions)]

    def coverage(self):
        """Stretches of counting, with runs a moment apart (an app restart) joined."""
        out = []
        for start, end in self._counted:
            if out and TL.seconds_between(out[-1][1], start) <= COVERAGE_TOLERANCE_SECONDS:
                out[-1] = (out[-1][0], max(out[-1][1], end))
            else:
                out.append((start, end))
        return out

    def best_hour(self):
        """The most recorded chests in any 60 minutes inside counting. -> Window, or None without a counted hour. The earliest wins a tie."""
        best, hour = None, timedelta(seconds=HOUR_SECONDS)
        for start, end in self.coverage():
            if TL.seconds_between(start, end) < HOUR_SECONDS:
                continue
            latest = end - hour
            inside = self._times[bisect_left(self._times, start):bisect_right(self._times, end)]
            for begin in sorted({min(max(t, start), latest) for t in inside} | {start, latest}):
                recorded = self._recorded(begin, begin + hour)
                if best is None or recorded > best[0]:
                    best = (recorded, begin)
        if best is None:
            return None
        return Window(best[1], best[1] + hour, self._totals(best[1], best[1] + hour), HOUR_SECONDS)

    def current_hour(self):
        """The last 60 minutes, and how much of them was counted."""
        start = self.now - timedelta(seconds=HOUR_SECONDS)
        covered = TL.total_seconds(TL.clip(self._counted, start, self.now))
        return Window(start, self.now, self._totals(start, self.now + TICK), covered)


def _averages(rows):
    """rows: (recorded, monitored, active) per completed day or week."""
    monitored = [recorded for recorded, is_monitored, _ in rows if is_monitored]
    active = [recorded for recorded, _, is_active in rows if is_active]
    return Averages(sum(monitored) / len(monitored) if monitored else None, sum(active) / len(active) if active else None,
                    sum(recorded for recorded, _, _ in rows) / len(rows) if rows else None, len(monitored), len(active), len(rows),
                    sum(1 for _, is_monitored, is_active in rows if not is_monitored and not is_active))


def load(folder, now=None, zone=None, counting_now=False, include_manual=False):
    """One profile's snapshot, from one read of its history. Slow on a very large history, so the app calls it off its window's thread."""
    history = H.read(folder, only=A.READ_KINDS)
    unended = [run_id for run_id, run in history.runs.items() if run.get("end") is None]
    return Snapshot(history, H.last_heartbeats(folder, unended), now=now, zone=zone, counting_now=counting_now, include_manual=include_manual)
