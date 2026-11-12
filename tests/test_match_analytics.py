"""
Match analytics (v0.3.0, M8B): the numbers match a hand-worked example, nothing unknown becomes zero, complete and observed figures never mix, and
the Analytics page shows it without freezing the window. Every expected value below was worked out by hand, not computed by the code under test.

Run:   python tests/test_match_analytics.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import ast
import contextlib
import io
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import profiles, settings
from fortnite_chest_counter import records as R

import test_match_recording as MR
import test_match_state as M2
import test_match_tracker as T
import test_update_gui as G


@contextlib.contextmanager
def folder():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "history" / "someone"


class Run:
    """Writes one run straight into a real history, as the live loop would."""

    def __init__(self, f, run_id="run"):
        self.f, self.warnings, self.count = Path(f), [], 0
        # dated two hours back, so the whole run lies in the past as a real one does (v0.4.0: time-based figures stop at now)
        self.writer = H.HistoryWriter(f, self.warnings.append, run_id=run_id, now=lambda: (datetime.now().astimezone() - timedelta(hours=2)).isoformat(timespec="milliseconds"))
        self.writer.start_run("stream", "0.3.0", 15, ["en"], 0, 0, 0, 60)

    def match(self, number, opened, played, closed, active, completion="complete", ended_by="placed", ended=None, spectating=0.0, uncertain=0.0, english=True, from_start=True, reasons=()):
        self.writer.match_opened({"t": opened, "match_number": number, "observed_from_start": from_start, "start_confidence": "high"})
        if ended is not None:
            self.writer.transition({"t": ended + 1, "previous": "IN_MATCH", "state": "ELIMINATED", "reason": "you_placed_seen", "match_number": number})
        self.writer.match_closed({"match_number": number, "completion": completion, "english_confirmed": english, "ended_by": ended_by, "observed_from_start": from_start, "opened_t": opened,
                                  "played_from_t": played, "ended_t": ended, "closed_t": closed, "observed_seconds": closed - opened - uncertain, "active_seconds": active, "spectating_seconds": spectating,
                                  "uncertain_seconds": uncertain, "complete_duration_seconds": (ended - played) if completion == "complete" else None, "start_confidence": "high", "end_confidence": "high",
                                  "discontinuity": False, "respawns": 0, "english_chests": 0, "portuguese_chests": 0, "reasons": list(reasons), "evidence": []})
        return self

    def chest(self, t, certain=True, approx=True, language="en", chest_type="rare"):
        self.count += 1
        self.writer.chest({"event_id": f"E{self.count:04d}", "time": t, "certain_counted": certain, "approx_counted": approx, "popup_template": f"{language}:CHEST", "adjusted_tier": "HIGH", "source": "popup", "chest_type": chest_type}, self.count, self.count)
        return self

    def end(self, elapsed=4000.0):
        self.writer.end_run(3500.0, "Q pressed", 60000, 0, elapsed, self.count, self.count, self.count)
        return self


def summary_of(f):
    return A.load(f)


def close(a, b):
    assert abs(a - b) < 1e-9, (a, b)


def worked_example(f):
    """Two complete matches, one partial, one unconfirmed. Worked by hand:

        A complete  open 0     play 30    end 630   close 640   active 600 s   chests 100 C, 200 A-only, 300 C        -> 2 CERTAIN, 3 APPROX
                    a chest at 635 is after the ending: not credited
        B complete  open 1000  play 1030  end 1330  close 1340  active 300 s   chest 1100 C                           -> 1 CERTAIN, 1 APPROX
        C partial   open 2000  play 2000             close 2240  active 240 s   chests 2100 C, 2200 A-only             -> 1 CERTAIN, 2 APPROX
        D unconfirmed open 3000 play 3000            close 3300  active 300 s   chest 3100 A-only, Portuguese          -> stays out
        a chest at 900 belongs to no match

    Observed (A, B, C) = 640 + 340 + 240 = 1220.  Confirmed play (A, B) = 900.  Unconfirmed time = 300.
    Every chest: CERTAIN 100, 300, 635, 900, 1100, 2100 = 6.  APPROX adds 200, 2200, 3100 = 9.  Credited (A, B, C): CERTAIN 4, APPROX 6.
    Per complete match: CERTAIN 3/2, APPROX 4/2.  Complete rate over 15 min: 3/15, 4/15.  Observed rate over 19 min: 4/19, 6/19.
    """
    run = Run(f)
    run.match(1, 0.0, 30.0, 640.0, 600.0, ended=630.0, spectating=10.0)
    run.match(2, 1000.0, 1030.0, 1340.0, 300.0, ended=1330.0, spectating=10.0, ended_by="victory")
    run.match(3, 2000.0, 2000.0, 2240.0, 240.0, completion="partial", ended_by="stopped", from_start=False)
    run.match(4, 3000.0, 3000.0, 3300.0, 300.0, completion="unconfirmed", ended_by="lost", english=False, from_start=False)
    for t, certain in ((100.0, True), (200.0, False), (300.0, True), (635.0, True), (900.0, True), (1100.0, True), (2100.0, True), (2200.0, False)):
        run.chest(t, certain=certain)
    run.chest(3100.0, certain=False, language="pt")
    return run.end()


# ------------------------------------------------------------------ M9H: the waiting island, and corrections made for a match

ISLAND = ["started: countdown ended", A.WAITING_ISLAND, "next match countdown seen"]


def test_the_waiting_island_is_no_match():
    """rc6 on Replays' stream: between two real matches, 38 s of island read as a match until the countdown proved otherwise. It stays in history
    (the tracker did think it a match for a moment) but is in no count, list or statistic."""
    with folder() as f:
        run = Run(f)
        run.match(1, 0.0, 30.0, 640.0, 600.0, ended=630.0)
        run.match(2, 700.0, 700.0, 738.0, 38.0, completion="unconfirmed", ended_by="left_or_unknown", english=False, reasons=ISLAND)
        run.match(3, 738.0, 760.0, 1200.0, 430.0, ended=1190.0)
        run.end()
        s = summary_of(f)
        assert (s.matches, s.complete, s.unconfirmed, s.waiting_islands) == (2, 2, 0, 1) and s.unconfirmed_seconds is None
        assert [m.match_number for m in s.recent] == [3, 1]


def test_an_unconfirmed_match_that_was_not_the_island_still_shows():
    with folder() as f:
        worked_example(f)
        s = summary_of(f)
        assert s.unconfirmed == 1 and s.waiting_islands == 0 and 4 in [m.match_number for m in s.recent]


def corrected_example(f):
    """The worked example's match 1 (3 APPROX, 2 CERTAIN, 600 s) with two +1s and one -1 made for it, one more +1 undone, and a +1 made on Overview."""
    worked_example(f)
    H.append_chest_correction(f, "p1", "run", 1, "not_visible", "t", 6, 10, 9, match_number=1)
    H.append_chest_correction(f, "p2", "run", 1, "missed", "t", 6, 11, 9, match_number=1)
    H.append_chest_correction(f, "m1", "run", -1, "false_positive", "t", 6, 10, 9, match_number=1)
    H.append_chest_correction(f, "p3", "run", 1, "manual", "t", 6, 11, 9, match_number=1)
    H.append_correction_undone(f, "u3", "run", "p3", 6, 10)
    H.append_chest_correction(f, "o1", None, 1, "manual", "t", 6, 11, 10)


def test_a_matchs_count_includes_the_corrections_made_for_it():
    with folder() as f:
        corrected_example(f)
        for include in (False, True):
            row = next(m for m in A.load(f, include).recent if m.match_number == 1)
            assert (row.certain, row.approx, row.manual_added, row.manual_removed) == (2, 4, 2, 1)        # 3 detected, +2, -1: whatever the setting
        assert all(m.manual_added == m.manual_removed == 0 for m in A.load(f).recent if m.match_number != 1)   # the Overview +1 belongs to no match


def test_a_correction_made_for_what_turned_out_to_be_the_island_belongs_to_no_match():
    """Pressed while the island was taken for a match: it stays in the total (the counter already has it) but no match is credited with it,
    neither the island, which is no match, nor a neighbour, which it was not made for."""
    with folder() as f:
        run = Run(f)
        run.match(1, 0.0, 30.0, 640.0, 600.0, ended=630.0)
        run.match(2, 700.0, 700.0, 738.0, 38.0, completion="unconfirmed", ended_by="left_or_unknown", english=False, reasons=ISLAND)
        run.match(3, 738.0, 760.0, 1200.0, 430.0, ended=1190.0)
        run.end()
        H.append_chest_correction(f, "p", "run", 1, "manual", "t", 0, 1, 0, match_number=2)
        for include in (False, True):
            s = A.load(f, include)
            assert all(m.manual_added == 0 and m.approx == 0 for m in s.recent) and s.credited_approx == 0 and s.manual_added == 1


def test_broken_chests_are_counted_apart_as_yours():
    with folder() as f:
        worked_example(f)                                                          # matches 1 and 2 complete, 3 partial
        H.append_chest_correction(f, "b1", "run", 1, "broken_chest", "t", 6, 10, 9, match_number=1)
        H.append_chest_correction(f, "b2", "run", 1, "broken_chest", "t", 6, 11, 9, match_number=3)
        H.append_chest_correction(f, "m", "run", 1, "missed", "t", 6, 12, 9, match_number=1)
        H.append_chest_correction(f, "b3", "run", 1, "broken_chest", "t", 6, 13, 9, match_number=2)
        H.append_correction_undone(f, "u", "run", "b3", 6, 12)
        s = A.load(f)
        assert s.broken_chests == 2 and s.broken_per_complete_match == 0.5               # 1 over two complete matches; the undone one is gone
        row = next(m for m in s.recent if m.match_number == 1)
        assert (row.manual_added, row.broken_chests, row.approx) == (2, 1, 5)


def test_statistics_take_minus_ones_always_and_plus_ones_only_when_asked():
    with folder() as f:
        corrected_example(f)
        off, on = A.load(f), A.load(f, include_manual=True)
        assert (off.credited_approx, on.credited_approx) == (5, 7)                 # credited 6: -1 always, +2 only when asked
        assert (off.complete_rate.approx_per_minute, on.complete_rate.approx_per_minute) == (3 / 15, 5 / 15)
        assert (off.per_complete_match.approx, on.per_complete_match.approx) == (1.5, 2.5)
        assert (off.certain_chests, off.approx_chests) == (6, 9) and off.manual_added == 3 and off.manual_removed == 1   # what was detected, and every standing correction
        assert not off.include_manual and on.include_manual


# ------------------------------------------------------------------ the numbers

def test_counts_are_kept_apart():
    with folder() as f:
        worked_example(f)
        s = summary_of(f)
        assert (s.complete, s.partial, s.unconfirmed, s.matches) == (2, 1, 1, 4)


def test_times_are_kept_apart():
    with folder() as f:
        worked_example(f)
        s = summary_of(f)
        assert (s.observed_seconds, s.confirmed_seconds, s.unconfirmed_seconds, s.session_seconds, s.sessions) == (1220.0, 900.0, 300.0, 4000.0, 1)


def test_chests_are_not_double_counted():
    with folder() as f:
        worked_example(f)
        s = summary_of(f)
        assert (s.certain_chests, s.approx_chests, s.credited_certain, s.credited_approx) == (6, 9, 4, 6)


def test_a_certain_chest_counts_once_in_approx_even_if_its_flag_is_missing():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 100.0, 100.0, ended=90.0).chest(50.0, certain=True, approx=False).end()
        s = summary_of(f)
        assert (s.certain_chests, s.approx_chests) == (1, 1)


def test_per_complete_match():
    with folder() as f:
        worked_example(f)
        per = summary_of(f).per_complete_match
        assert (per.certain, per.approx, per.matches) == (1.5, 2.0, 2)


def test_the_complete_rate_uses_only_complete_matches():
    with folder() as f:
        worked_example(f)
        rate = summary_of(f).complete_rate
        close(rate.certain_per_minute, 3 / 15)
        close(rate.approx_per_minute, 4 / 15)
        assert rate.matches == 2 and rate.minutes == 15


def test_the_observed_rate_includes_partial_matches_and_stays_separate():
    with folder() as f:
        worked_example(f)
        s = summary_of(f)
        close(s.observed_rate.certain_per_minute, 4 / 19)
        close(s.observed_rate.approx_per_minute, 6 / 19)
        assert s.observed_rate.matches == 3 and s.observed_rate.minutes == 19 and s.complete_rate.certain_per_minute != s.observed_rate.certain_per_minute


def test_the_complete_rate_waits_for_five_minutes_across_matches():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 41.0, 40.0, ended=40.0).match(2, 100.0, 100.0, 161.0, 60.0, ended=160.0).match(3, 200.0, 200.0, 399.0, 199.0, ended=398.0).end()
        assert summary_of(f).complete_rate is None                        # 299 s


def test_short_complete_matches_count_and_are_weighted_by_their_time():
    with folder() as f:
        run = Run(f).match(1, 0.0, 0.0, 41.0, 40.0, ended=40.0).match(2, 100.0, 100.0, 161.0, 60.0, ended=160.0).match(3, 200.0, 200.0, 411.0, 210.0, ended=410.0)
        for t in (5.0, 6.0, 7.0, 105.0, 106.0, 107.0, 108.0, *(210.0 + i for i in range(12))):
            run.chest(t)
        run.end()
        rate = summary_of(f).complete_rate
        close(rate.approx_per_minute, 19 / (310 / 60))                    # the mean of each match's own rate would be about 4.1
        assert rate.matches == 3


def test_partial_matches_do_not_fill_the_complete_rate():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 700.0, 600.0, completion="partial", ended_by="stopped", from_start=False).chest(100.0).end()
        s = summary_of(f)
        assert s.complete_rate is None and s.observed_rate is not None


def test_a_rate_is_total_over_total_not_an_average_of_rates():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 60.0, 60.0, ended=50.0).chest(10.0).match(2, 100.0, 100.0, 1000.0, 900.0, ended=990.0).end()
        rate = summary_of(f).complete_rate
        close(rate.certain_per_minute, 1 / 16)                            # the mean of 1/min and 0/min would be 0.5


# ------------------------------------------------------------------ unknown is not zero

def test_an_empty_history_has_no_values():
    with folder() as f:
        s = summary_of(f)
        assert s.empty and s.matches == 0
        assert (s.observed_seconds, s.confirmed_seconds, s.session_seconds, s.per_complete_match, s.complete_rate, s.observed_rate) == (None,) * 6


def test_partial_only_history_shows_time_but_no_complete_figures():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 600.0, 600.0, completion="partial", ended_by="stopped", from_start=False).chest(100.0).end()
        s = summary_of(f)
        assert (s.complete, s.partial) == (0, 1) and s.observed_seconds == 600.0
        assert s.confirmed_seconds is None and s.per_complete_match is None and s.complete_rate is None
        close(s.observed_rate.certain_per_minute, 1 / 10)


def test_too_little_observed_play_gives_no_observed_rate():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 299.0, 299.0, completion="partial", ended_by="stopped", from_start=False).chest(100.0).end()
        assert summary_of(f).observed_rate is None


def test_exactly_enough_observed_play_gives_a_rate():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 300.0, 300.0, completion="partial", ended_by="stopped", from_start=False).chest(100.0).end()
        close(summary_of(f).observed_rate.certain_per_minute, 1 / 5)


def test_unconfirmed_matches_stay_out_of_every_statistic():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 900.0, 900.0, completion="unconfirmed", ended_by="stopped", english=False, from_start=False).chest(100.0, language="pt").end()
        s = summary_of(f)
        assert s.unconfirmed == 1 and s.observed_seconds is None and s.observed_rate is None and s.complete_rate is None and s.credited_approx == 0
        assert s.unconfirmed_seconds == 900.0


def test_zero_active_time_cannot_produce_a_rate():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 100.0, 0.0, ended=90.0).chest(50.0).end()
        s = summary_of(f)
        assert s.complete_rate is None and s.per_complete_match is None and s.matches_left_out_of_rates == 1


def test_unknown_active_time_is_left_out_not_counted_as_zero():
    with folder() as f:
        run = Run(f)
        run.match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).chest(100.0)
        row = rows_matching(run)
        H._append_line(f / H.MATCHES, H._encode({**row, "id": "other:1", "match_number": 2, "opened_t": 1000.0, "played_from_t": 1000.0, "closed_t": 1600.0, "ended_t": None, "active_seconds": None}))
        run.end()
        s = summary_of(f)
        assert s.complete == 2 and s.complete_rate.matches == 1 and s.matches_left_out_of_rates == 1


def rows_matching(run):
    return next(json.loads(line) for line in (run.f / H.MATCHES).read_bytes().splitlines() if b'"kind":"match_closed"' in line)


def test_a_real_zero_stays_zero():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).end()
        s = summary_of(f)
        assert s.complete_rate.certain_per_minute == 0 and s.per_complete_match.approx == 0 and s.certain_chests == 0


def test_no_outcome_is_inferred():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 600.0, 600.0, completion="partial", ended_by="stopped", from_start=False).end()
        assert summary_of(f).recent[0].ending == "Counting stopped"
    with folder() as f:
        run = Run(f).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0, ended_by="victory").end()
        assert summary_of(f).recent[0].ending == "Victory Royale"


def test_an_unknown_ending_says_not_seen():
    with folder() as f:
        Run(f).match(1, 0.0, 0.0, 600.0, 600.0, completion="partial", ended_by="something_new", from_start=False).end()
        assert summary_of(f).recent[0].ending == "Not seen"


# ------------------------------------------------------------------ recent matches

def test_recent_matches_are_newest_first_with_their_evidence():
    with folder() as f:
        worked_example(f)
        recent = summary_of(f).recent
        assert [r.quality for r in recent] == ["unconfirmed", "partial", "complete", "complete"]
        assert (recent[3].certain, recent[3].approx, recent[3].duration_seconds, recent[3].duration_is_full, recent[3].ending) == (2, 3, 600.0, True, "Placed")
        assert (recent[1].certain, recent[1].approx, recent[1].duration_seconds, recent[1].duration_is_full) == (1, 2, 240.0, False)


def test_a_match_start_comes_from_the_run_clock():
    with folder() as f:
        writer = H.HistoryWriter(f, [].append, run_id="run", now=lambda: "2026-11-11T10:00:00.000+01:00")
        writer.start_run("stream", "0.3.0", 15, ["en"], 0, 0, 0, 60)
        run = Run.__new__(Run)
        run.f, run.writer, run.count = Path(f), writer, 0
        run.match(1, 90.0, 90.0, 600.0, 510.0, ended=590.0).end()
        assert summary_of(f).recent[0].started_at.strftime("%H:%M:%S") == "10:01:30"


def test_a_run_with_no_start_row_has_no_start_time():
    with folder() as f:
        run = Run.__new__(Run)
        run.f, run.writer, run.count = Path(f), H.HistoryWriter(f, [].append, run_id="headless"), 0
        run.match(1, 90.0, 90.0, 600.0, 510.0, ended=590.0)
        assert summary_of(f).recent[0].started_at is None


def test_recent_is_limited():
    with folder() as f:
        run = Run(f)
        for i in range(30):
            run.match(i + 1, i * 100.0, i * 100.0, i * 100.0 + 90, 90.0, ended=i * 100.0 + 80)
        run.end()
        assert len(summary_of(f).recent) == A.RECENT_MATCHES


def test_a_match_with_lost_chests_is_flagged_and_left_out_of_rates():
    with folder() as f:
        run = Run(f).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).chest(100.0)
        H._append_line(f / H.MATCHES, H._encode({"kind": "gap", "schema": 1, "id": "x:1", "run_id": "run", "at": "x", "reason": H.WRITE_FAILED, "match_number": 1, "lost_rows": 1, "missing_certain": 1, "missing_approximate": 2}))
        run.end()
        s = summary_of(f)
        assert s.recent[0].chests_may_be_missing is True and s.complete_rate is None and s.matches_left_out_of_rates == 1 and (s.missing_certain, s.missing_approx) == (1, 2)


# ------------------------------------------------------------------ real situations in the data

def test_an_interrupted_match_counts_as_partial_with_only_its_reported_time():
    with folder() as f:
        run = Run(f, run_id="dead")
        run.writer.match_opened({"t": 10.0, "match_number": 1, "observed_from_start": True, "start_confidence": "high"})
        run.chest(100.0)
        run.writer.heartbeat(400.0, 6000, 0, match={"match_number": 1, "opened_t": 8.0, "played_from_t": 30.0, "observed_seconds": 392.0, "active_seconds": 370.0, "spectating_seconds": 0.0, "uncertain_seconds": 0.0, "english_confirmed": True})
        run.chest(450.0)                                                  # after the last checkpoint: outside what was reported
        H.HistoryWriter(f, [].append).start_run("stream", "0.3.0", 15, ["en"], 2, 2, 2, 60)
        s = summary_of(f)
        assert (s.complete, s.partial) == (0, 1) and s.observed_seconds == 392.0 and s.credited_certain == 1 and s.recent[0].interrupted is True and s.recent[0].ending == "App closed unexpectedly"
        assert s.sessions == 2 and s.sessions_cut_short == 2


def test_a_reset_mid_run_keeps_both_chests():
    with folder() as f:
        run = Run(f).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0)
        run.writer.chest({"event_id": "E0001", "time": 100.0, "certain_counted": True, "approx_counted": True}, 1, 1)
        run.writer.counter_changed("reset", 0, 0)
        run.writer.chest({"event_id": "E0001", "time": 200.0, "certain_counted": True, "approx_counted": True}, 1, 1)
        run.end()
        s = summary_of(f)
        assert s.credited_certain == 2 and s.recent[0].certain == 2


def test_repeated_rows_count_once():
    with folder() as f:
        worked_example(f)
        for name in (H.MATCHES, H.CHESTS):
            path = f / name
            path.write_bytes(path.read_bytes() * 2)
        s = summary_of(f)
        assert (s.complete, s.certain_chests, s.observed_seconds) == (2, 6, 1220.0)


def test_a_chest_type_correction_changes_no_count():
    with folder() as f:
        run = Run(f).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).chest(100.0, chest_type="unknown")
        before = summary_of(f)
        run.writer.chest_type("E0001", 100.0, "rare")
        after = summary_of(f)
        assert (before.certain_chests, before.credited_approx) == (after.certain_chests, after.credited_approx) == (1, 1)


def test_not_a_match_removes_it_from_every_statistic_and_undo_restores_it():
    with folder() as f:
        worked_example(f)
        H.correct_match(f, "run", 1)
        s = summary_of(f)
        assert (s.complete, s.excluded, s.observed_seconds, s.confirmed_seconds) == (1, 1, 580.0, 300.0) and s.complete_rate.matches == 1
        assert [r.excluded for r in s.recent] == [False, False, False, True]      # still listed, so it can be restored
        assert s.certain_chests == 6                                      # the chests themselves were still opened
        H.correct_match(f, "run", 1, not_a_match=False)
        assert summary_of(f).complete == 2


def test_truncated_and_corrupt_files_cannot_break_it():
    with folder() as f:
        worked_example(f)
        whole = (f / H.MATCHES).read_bytes()
        step = max(len(whole) // 200, 1)
        for cut in range(0, len(whole), step):
            (f / H.MATCHES).write_bytes(whole[:cut])
            A.load(f)
        (f / H.MATCHES).write_bytes(whole + b"\xff\xfe garbage\n{broken\n")
        s = summary_of(f)
        assert s.complete == 2 and s.damaged_rows == 2


def test_rows_with_impossible_values_are_counted_as_damaged():
    with folder() as f:
        run = Run(f).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0)
        row = rows_matching(run)
        for extra, fields in enumerate(({"completion": "maybe"}, {"opened_t": "soon"}, {"closed_t": None}, {"ended_t": "x"}), 2):
            H._append_line(f / H.MATCHES, H._encode({**row, "id": f"bad:{extra}", "match_number": extra, **fields}))
        H._append_line(f / H.CHESTS, H._encode({"kind": "chest", "schema": 1, "id": "bad:9", "run_id": "run", "counter_epoch": 5, "event_id": "E0099", "t": "later", "certain_total": 1, "approximate_total": 1}))
        H._append_line(f / H.MATCHES, H._encode({"kind": "transition", "schema": 1, "id": "bad:10", "run_id": "run", "t": None}))
        run.end()
        s = summary_of(f)
        assert s.complete == 1 and s.damaged_rows == 6, s.damaged_rows


def test_an_unfinished_match_is_not_counted():
    with folder() as f:
        run = Run(f)
        run.writer.match_opened({"t": 10.0, "match_number": 1, "observed_from_start": True, "start_confidence": "high"})
        s = summary_of(f)
        assert s.unfinished == 1 and s.matches == 0 and s.sessions == 1 and s.sessions_cut_short == 1 and s.session_seconds is None


def test_every_heartbeat_interval_gives_the_same_statistics():
    results = []
    for interval in settings.MATCH_HEARTBEATS:
        with folder() as f:
            rec = MR.Recording(f, heartbeat=interval, run_id="same")
            M2.played_match(rec).show(700, health=MR.HP)
            onset = rec.t - 50
            rec.add_chest(onset).show(10, "you_placed", health=40).show(5, "connecting").end()
            s = summary_of(f)
            results.append((s.complete, s.partial, s.observed_seconds, s.confirmed_seconds, s.credited_certain, s.credited_approx, s.complete_rate))
    assert all(result == results[0] for result in results) and results[0][0] == 1, results


def test_the_real_live_loop_feeds_it():
    with tempfile.TemporaryDirectory() as tmp:
        result, _ = T.run_command(tmp, "live", "on")
        s = A.load(Path(tmp) / "history" / "s")
    assert s.sessions == 1 and s.certain_chests == result["state"]["certain"] and s.approx_chests == result["state"]["approximate"] and s.matches == 1


def test_two_profiles_stay_apart():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "state" / "chest_state.json"
        Run(profiles.history_folder(base, "default"), "a").match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).chest(100.0).end()
        Run(profiles.history_folder(base, "alice"), "b").match(1, 0.0, 0.0, 300.0, 300.0, completion="partial", ended_by="stopped", from_start=False).end()
        one, two = A.load(profiles.history_folder(base, "default")), A.load(profiles.history_folder(base, "alice"))
        assert (one.complete, one.partial, one.certain_chests) == (1, 0, 1) and (two.complete, two.partial, two.certain_chests) == (0, 1, 0)


# ------------------------------------------------------------------ formatting

def test_durations_read_naturally():
    assert [A.duration_text(v) for v in (45, 750, 27720, 0)] == ["45s", "12m 30s", "7h 42m", "0s"]
    assert [A.duration_text(v) for v in (None, -1, float("nan"), "x", True)] == [None] * 5


# ------------------------------------------------------------------ isolation and scale

def test_the_statistics_module_uses_no_gui_and_touches_no_totals():
    tree = ast.parse((ROOT / "src/fortnite_chest_counter/match_analytics.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {f"{node.module}.{alias.name}" for alias in node.names}
    assert imported == {"math", "dataclasses.dataclass", "dataclasses.field", "datetime.datetime", "datetime.timedelta", "fortnite_chest_counter.match_history"}, imported


def test_loading_changes_no_file():
    with folder() as f:
        worked_example(f)
        before = {p.name: p.read_bytes() for p in f.iterdir()}
        A.load(f)
        assert before == {p.name: p.read_bytes() for p in f.iterdir()}


def large_history(f, matches=5000):
    f.mkdir(parents=True, exist_ok=True)
    rows, chests, n, event = bytearray(), bytearray(), 0, 0
    at = "2026-11-11T10:00:00.000+01:00"

    def head(kind):
        nonlocal n
        n += 1
        return {"kind": kind, "schema": 1, "id": f"run:{n}", "run_id": "run", "at": at}

    rows += H._encode({**head("run_start"), "source_type": "stream", "app_version": "x", "configured_analysis_fps": 15, "languages": ["en"], "certain_total": 0, "approximate_total": 0, "events_logged": 0, "heartbeat_seconds": 60})
    for i in range(1, matches + 1):
        t0 = i * 1500.0
        for k in range(6):
            rows += H._encode({**head("transition"), "t": t0 + 1191 if k == 5 else t0 + k, "previous": "IN_MATCH", "state": "ELIMINATED" if k == 5 else "IN_MATCH", "reason": "x", "match_number": i})
        for k in range(8):
            event += 1
            chests += H._encode({**head("chest"), "counter_epoch": 0, "event_id": f"E{event:04d}", "t": t0 + 60 + 60 * k, "certain_counted": True, "approx_counted": True, "chest_type": "rare", "language": "en", "certain_total": event, "approximate_total": event})
        rows += H._encode({**head("match_closed"), "match_number": i, "completion": "complete", "english_confirmed": True, "ended_by": "placed", "observed_from_start": True, "opened_t": t0, "played_from_t": t0 + 30, "ended_t": t0 + 1190, "closed_t": t0 + 1200,
                           "observed_seconds": 1200.0, "active_seconds": 1160.0, "spectating_seconds": 10.0, "uncertain_seconds": 0.0, "complete_duration_seconds": 1160.0, "start_confidence": "high", "end_confidence": "high", "discontinuity": False, "english_chests": 8, "portuguese_chests": 0, "reasons": [], "evidence": []})
    (f / H.MATCHES).write_bytes(bytes(rows))
    (f / H.CHESTS).write_bytes(bytes(chests))
    return event


def test_a_large_history_is_fast_and_correct():
    with folder() as f:
        total = large_history(f)
        begin = time.perf_counter()
        s = A.load(f)
        spent = time.perf_counter() - begin
        assert s.complete == 5000 and s.certain_chests == total == s.credited_certain and spent < 5, spent


# ------------------------------------------------------------------ the page

def settle(w):
    page = w.win.analytics
    if page._thread is not None:
        page._thread.join(30)
    page._collect()


def text_of(tile):
    return tile.value.text()


DASH = "—"


def history_folder(w, profile="default"):
    return w.dir / "state" / "history" / profile


def test_analytics_is_its_own_page_after_the_dashboard():
    with G.window() as w:
        assert [w.win.nav.item(i).text() for i in range(w.win.nav.count())] == ["Dashboard", "Analytics", "Overlay", "Settings", "Help & diagnostics"]
        assert w.win.pages.widget(1) is w.win.analytics


def test_the_empty_page_shows_dashes_and_explains():
    with G.window(config='[match]\nmode = "off"\n') as w:
        page = w.win.analytics
        page.refresh()
        settle(w)
        assert not page.empty.isHidden() and not page.empty_settings.isHidden() and "Turn on match tracking" in page.empty_hint.text()
        for tile in (page.observed, page.confirmed, page.session, page.certain, page.approx, page.per_match, page.complete_rate, page.observed_rate):
            assert text_of(tile) == DASH, tile.sub.text()
        assert page.table.rowCount() == 0 and page.table.isHidden() and page.recent_title.isHidden() and page.complete_rate.sub.text().startswith("Not enough complete matches")


def test_the_page_shows_the_worked_example():
    with G.window() as w:
        worked_example(history_folder(w))
        page = w.win.analytics
        page.refresh()
        settle(w)
        assert page.empty.isHidden() and text_of(page.matches) == "4" and page.matches.sub.text() == "2 complete · 1 partial · 1 unconfirmed"
        # v0.4.0: ACTIVE PLAY covers Complete and Partial matches (600 + 300 + 240 s), and the chest at 635, after match A ended, is someone
        # else's (D4): recorded chests are 9 - 1 = 8, CERTAIN 6 - 1 = 5. The complete-only 15 minutes stay in the per-minute figure.
        assert text_of(page.observed) == "20m 20s" and text_of(page.confirmed) == "at least 19m 00s" and text_of(page.session) == "1h 06m"   # match D and the chest at 900 were play not recognised
        assert "15m 00s of active play" in page.complete_rate.sub.text() and "1 spectated left out" in page.approx.sub.text()
        assert text_of(page.certain) == "5" and text_of(page.approx) == "8" and text_of(page.per_match) == "2.0" and "1.5 CERTAIN" in page.per_match.sub.text()
        assert text_of(page.complete_rate) == "0.27" and text_of(page.observed_rate) == "0.32"
        assert "0.20 CERTAIN" in page.complete_rate.sub.text() and "2 complete matches" in page.complete_rate.sub.text() and "0.21 CERTAIN" in page.observed_rate.sub.text() and "partial" in page.observed_rate.sub.text()
        assert page.table.rowCount() == 4
        assert [page.table.item(3, c).text() for c in (1, 2, 3, 4, 5, 6)] == ["10m", "2", "3", "0.30", "Complete", "Placed"]   # v0.4.0: minutes in the list
        assert [page.table.item(1, c).text() for c in (1, 4, 5, 6)] == ["4m seen", "0.50 seen", "Partial", "Counting stopped"]


def test_partial_only_shows_dashes_for_complete_figures():
    with G.window() as w:
        Run(history_folder(w)).match(1, 0.0, 0.0, 600.0, 600.0, completion="partial", ended_by="stopped", from_start=False).end()
        page = w.win.analytics
        page.refresh()
        settle(w)
        assert text_of(page.observed) == "10m 00s" and text_of(page.confirmed) == "10m 00s" and text_of(page.per_match) == DASH and text_of(page.complete_rate) == DASH
        assert page.per_match.sub.text() == "No complete matches yet" and text_of(page.observed_rate) != DASH


def test_the_page_tells_the_reader_what_to_be_careful_about():
    with G.window() as w:
        f = history_folder(w)
        run = Run(f).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).chest(100.0)
        H._append_line(f / H.MATCHES, H._encode({"kind": "gap", "schema": 1, "id": "x:1", "run_id": "run", "at": "x", "reason": H.WRITE_FAILED, "match_number": 1, "lost_rows": 1, "missing_certain": 1, "missing_approximate": 2}))
        H._append_line(f / H.MATCHES, b"{broken\n")
        run.end()
        page = w.win.analytics
        page.refresh()
        settle(w)
        notes = page.notes.text()
        assert "left out of chests per minute" in notes and "missing 2 chests" in notes and "1 damaged row skipped" in notes, notes
        assert page.table.item(0, 2).text() == "1+"


def test_opening_the_page_reads_the_history():
    with G.window() as w:
        Run(history_folder(w)).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).end()
        w.win.show_page(w.win.analytics)
        settle(w)
        assert text_of(w.win.analytics.matches) == "1"


def test_switching_profile_shows_that_profiles_history():
    with G.window() as w:
        base = w.dir / "state" / "chest_state.json"
        base.parent.mkdir(parents=True, exist_ok=True)
        entry = profiles.create(base, "Alice", activate=False)
        Run(history_folder(w)).match(1, 0.0, 0.0, 600.0, 600.0, ended=590.0).end()
        w.win.fill_profiles()
        page = w.win.analytics
        page.refresh()
        settle(w)
        assert text_of(page.matches) == "1" and page.profile_line.text() == "Profile: Default"
        d = w.win.dashboard
        d.profile.setCurrentIndex(d.profile.findData(entry["id"]))
        w.win.switch_profile(d.profile.currentIndex())
        page.refresh()
        settle(w)
        assert text_of(page.matches) == "0" and page.profile_line.text() == "Profile: Alice" and page.table.rowCount() == 0


def test_a_slow_history_does_not_freeze_the_window():
    real = R.load

    def slow(folder, *args, **kwargs):
        time.sleep(0.6)
        return real(folder, *args, **kwargs)

    with G.window() as w, patch.object(R, "load", slow):
        page = w.win.analytics
        begin = time.perf_counter()
        page.refresh()
        spent = time.perf_counter() - begin
        assert spent < 0.2 and page.status.text().startswith("Reading"), spent
        settle(w)
        assert page.status.text() == ""


def test_an_old_request_cannot_overwrite_a_newer_one():
    with G.window() as w:
        page = w.win.analytics
        page._generation = 5
        old = A.Summary(complete=9)
        new = A.Summary(complete=1)
        page._done.put((5, new))
        page._done.put((4, old))                                          # the older, slower read finishes last
        page._collect()
        assert text_of(page.matches) == "1"


def test_a_read_failure_is_explained():
    with G.window() as w, patch.object(R, "load", side_effect=PermissionError("locked")):
        page = w.win.analytics
        page.refresh()
        settle(w)
        assert "could not be read" in page.status.text() and "not affected" in page.status.text()


def test_the_page_changes_nothing():
    with G.window() as w:
        f = history_folder(w)
        worked_example(f)
        before = sorted((p.name, p.stat().st_size) for p in w.dir.rglob("*") if p.is_file())
        counts = w.win.counts
        with patch.object(w.win.worker, "send", create=True) as send:
            w.win.show_page(w.win.analytics)
            settle(w)
        assert send.call_count == 0 and w.win.counts == counts and before == sorted((p.name, p.stat().st_size) for p in w.dir.rglob("*") if p.is_file())


def test_the_table_cannot_be_edited():
    with G.window() as w:
        from PySide6.QtWidgets import QAbstractItemView
        assert w.win.analytics.table.editTriggers() == QAbstractItemView.NoEditTriggers


def test_the_page_refreshes_when_counting_stops_only_if_open():
    with G.window() as w:
        page = w.win.analytics
        with patch.object(page, "refresh") as refresh:
            w.win.handle({"type": "exit", "code": 0})
            assert refresh.call_count == 0
            w.win.pages.setCurrentWidget(page)
            w.win.handle({"type": "exit", "code": 0})
            assert refresh.call_count == 1


def test_recorded_real_loop_appears_on_the_page():
    with G.window(config='[match]\nmode = "on"\n') as w:
        with T.scripted_pipeline(T.scripted_frames()), contextlib.redirect_stdout(io.StringIO()):
            assert C.main(["live", "--source", "file", "--reset"]) == 0
        page = w.win.analytics
        page.refresh()
        settle(w)
        assert text_of(page.matches) == "1" and text_of(page.approx) == "3" and text_of(page.certain) == "2", (text_of(page.matches), page.status.text())


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}", flush=True)
        except Exception:
            failed += 1
            import traceback
            print(f"  FAIL  {name}", flush=True)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} match analytics checks passed")
    sys.exit(1 if failed else 0)
