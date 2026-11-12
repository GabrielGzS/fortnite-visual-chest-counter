"""
Synthetic histories for v0.4.0's time-based statistics. Rows are written through the real match_history writer with a fake clock, so the files
are exactly what the app writes, and every expected number in the tests can be worked out by hand.

CentralEurope is a real daylight-saving zone (UTC+1, UTC+2 from the last Sunday of March to the last Sunday of October, changing at 01:00 UTC),
written out here because Windows Python ships no time zone database.
"""

import itertools
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from unittest.mock import patch

from fortnite_chest_counter import match_history as H

UTC = timezone.utc
HOUR = timedelta(hours=1)


def _last_sunday(year, month):
    day = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return day - timedelta(days=(day.weekday() + 1) % 7)


class CentralEurope(tzinfo):
    def _changes(self, year):
        """The two changes of a year, as naive UTC times."""
        return (datetime.combine(_last_sunday(year, 3), datetime.min.time()) + HOUR,
                datetime.combine(_last_sunday(year, 10), datetime.min.time()) + HOUR)

    def utcoffset(self, dt):
        if dt is None:
            return HOUR
        naive = dt.replace(tzinfo=None)
        spring, autumn = self._changes(naive.year)
        if spring + HOUR <= naive < autumn + HOUR:                # 02:00 local in March; the hour 02:00-03:00 does not exist
            return 2 * HOUR
        if autumn + HOUR <= naive < autumn + 2 * HOUR:            # 02:00-03:00 in October happens twice
            return HOUR if dt.fold else 2 * HOUR
        return HOUR

    def dst(self, dt):
        return self.utcoffset(dt) - HOUR

    def tzname(self, dt):
        return "CEST" if self.dst(dt) else "CET"

    def fromutc(self, dt):
        utc = dt.replace(tzinfo=None)
        spring, autumn = self._changes(utc.year)
        if spring <= utc < autumn:
            return (utc + 2 * HOUR).replace(tzinfo=self, fold=0)
        return (utc + HOUR).replace(tzinfo=self, fold=1 if autumn <= utc < autumn + HOUR else 0)


CET = CentralEurope()


def moment(text, zone=CET):
    """'2026-11-12 03:38:12' local -> a UTC datetime."""
    return datetime.fromisoformat(text).replace(tzinfo=zone).astimezone(UTC)


class Recorder:
    """One profile's history. `zone` is the time zone the rows' `at` is written in, as the PC's would be."""

    def __init__(self, folder, zone=CET):
        self.folder, self.zone, self.clock, self.warnings = Path(folder), zone, None, []
        self._ids = itertools.count(1)

    def iso(self):
        return self.clock.astimezone(self.zone).isoformat(timespec="milliseconds")

    @contextmanager
    def at(self, when):
        self.clock = when
        with patch.object(H, "_now", self.iso):
            yield

    def run(self, start, source="desktop", run_id=None, heartbeat=60):
        return RunWriter(self, start, source, run_id or f"run{next(self._ids)}", heartbeat)

    def correction(self, when, delta, reason=H.MANUAL, run_id=None, match_number=None):
        """A +1 or -1 made on Overview or in the Game view. -> its id."""
        correction_id = f"c-{uuid.uuid4().hex[:8]}"
        with self.at(when):
            H.append_chest_correction(self.folder, correction_id, run_id, delta, reason, "token", 0, 0, 0, match_number)
        return correction_id

    def undo(self, when, correction_id, run_id=None):
        with self.at(when):
            H.append_correction_undone(self.folder, f"u-{uuid.uuid4().hex[:8]}", run_id, correction_id, 0, 0)

    def read(self, full=False):
        from fortnite_chest_counter import match_analytics as A
        return H.read(self.folder) if full else H.read(self.folder, only=A.READ_KINDS)


class RunWriter:
    """One run, with source time `t` in seconds since its start (as a local live source has it)."""

    def __init__(self, recorder, start, source, run_id, heartbeat):
        self.rec, self.t0, self.run_id, self.events, self.every = recorder, start, run_id, 0, heartbeat
        recorder.clock = start
        self.writer = H.HistoryWriter(recorder.folder, recorder.warnings.append, run_id=run_id, now=recorder.iso)
        with recorder.at(start):
            self.writer.start_run(source, "0.4.0", 15, ["en"], 0, 0, 0, heartbeat)

    def _at(self, t):
        self.rec.clock = self.t0 + timedelta(seconds=t)

    def chest(self, t, certain=False):
        self._at(t)
        self.events += 1
        self.writer.chest({"event_id": f"E{self.events:04d}", "time": float(t), "certain_counted": certain, "approx_counted": True,
                           "popup_template": "en:CHEST", "adjusted_tier": "HIGH" if certain else "MEDIUM", "source": "test"}, int(certain), self.events)
        return self

    def chests(self, *times):
        for t in times:
            self.chest(t)
        return self

    def beats(self, until, start=0):
        for t in range(start, int(until) + 1, self.every):
            self._at(t)
            self.writer.heartbeat(float(t), 0, 0)
        return self

    def match(self, number, opened, played, closed, active, completion="complete", ended_by="placed", ended=None, out=None, english=True,
              from_start=True, reasons=()):
        self._at(opened)
        self.writer.match_opened({"t": float(opened), "match_number": number, "observed_from_start": from_start, "start_confidence": "high"})
        if out is not None:
            self._at(out)
            self.writer.transition({"t": float(out), "previous": "IN_MATCH", "state": "ELIMINATED", "reason": "test", "match_number": number})
        self._at(closed)
        self.writer.match_closed({"match_number": number, "completion": completion, "english_confirmed": english, "ended_by": ended_by,
                                  "observed_from_start": from_start, "opened_t": float(opened), "played_from_t": float(played), "ended_t": ended,
                                  "closed_t": float(closed), "observed_seconds": float(closed - opened), "active_seconds": float(active),
                                  "spectating_seconds": 0.0, "uncertain_seconds": 0.0,
                                  "complete_duration_seconds": float((ended or closed) - played) if completion == "complete" else None,
                                  "start_confidence": "high", "end_confidence": "high", "discontinuity": False, "english_chests": 0,
                                  "portuguese_chests": 0, "reasons": list(reasons), "evidence": []})
        return self

    def end(self, t, clock_drift=0.0):
        """A clean stop after `t` seconds. `clock_drift` moves the wall clock of the end row only, as a clock change would."""
        self.rec.clock = self.t0 + timedelta(seconds=t + clock_drift)
        self.writer.end_run(float(t), "stopped", 0, 0, float(t), self.events, self.events, self.events)
        return self

    def crash(self):
        """The app dies: nothing more is written for this run."""
        self.writer._ended = True
        return self
