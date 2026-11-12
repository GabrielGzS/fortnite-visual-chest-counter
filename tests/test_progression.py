"""
Real-life progress (v0.4.0, M2): chests per hour of session time, per day and per week, the current and best hour, and the three day
averages, from a history written by the real writer. Every expected value was worked out by hand from the fortnight below; nothing is
computed by the code under test.

The fortnight (Central European time; "now" is Thursday 12 November 2026, 18:00):

    Fri 6 Nov    20:00-20:30  one run, chests at 1, 2, 3, 4 minutes                              4 chests
    Sat 7, Sun 8              nothing: not counted
    Mon 9 Nov    20:00-21:00  run 1: a Complete match (play from 20:06, 1500 s active, out at 20:30:50, ended 20:31:40),
                              chests at 20:10 (CERTAIN), 20:20, 20:30, and 20:31:20 while spectating (left out)
                 21:20-22:00  run 2 (20 minutes later: same session), chests at 21:25 and 21:35, outside any match
                              your +1 (broken chest) at 21:50, your -1 at 21:55, a +1 at 21:56 undone at 21:57
                                                                                              3 + 2 + 1 - 1 = 5
    Tue 10 Nov   19:00-19:30  a run with no chest: a known zero                                  0
    Wed 11 Nov   23:30-00:30  a run across midnight, chests at 23:40 (Wed) and 00:10 (Thu)        1 on Wed, 1 on Thu
    Thu 12 Nov                today                                                           1

Run:   python tests/test_progression.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import tempfile
from datetime import date, timedelta
from pathlib import Path

from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import progression as P
from fortnite_chest_counter import timeline as TL

import history_fixtures as F

NOW = F.moment("2026-11-12 18:00:00")


@contextlib.contextmanager
def recorder():
    with tempfile.TemporaryDirectory() as tmp:
        yield F.Recorder(Path(tmp) / "history" / "p")


def fortnight(rec):
    rec.run(F.moment("2026-11-06 20:00:00")).chests(60, 120, 180, 240).end(1800)
    one = rec.run(F.moment("2026-11-09 20:00:00"))
    one.chest(600, certain=True).chests(1200, 1800, 1880)
    one.match(1, opened=300, played=360, closed=2000, active=1500, ended=1900, out=1850)
    one.end(3600)
    two = rec.run(F.moment("2026-11-09 21:20:00")).chests(300, 900).end(2400)
    rec.correction(F.moment("2026-11-09 21:50:00"), 1, H.BROKEN_CHEST, run_id=two.run_id)
    rec.correction(F.moment("2026-11-09 21:55:00"), -1, H.MANUAL, run_id=two.run_id)
    undone = rec.correction(F.moment("2026-11-09 21:56:00"), 1, H.MANUAL, run_id=two.run_id)
    rec.undo(F.moment("2026-11-09 21:57:00"), undone, run_id=two.run_id)
    rec.run(F.moment("2026-11-10 19:00:00")).end(1800)
    rec.run(F.moment("2026-11-11 23:30:00")).chests(600, 2400).end(3600)


def snapshot(rec, now=NOW, **kwargs):
    return P.load(rec.folder, now=now, zone=F.CET, **kwargs)


@contextlib.contextmanager
def the_fortnight():
    with recorder() as rec:
        fortnight(rec)
        yield snapshot(rec)


# ------------------------------------------------------------------ what is counted

def test_recorded_chests_are_detected_plus_standing_corrections_without_the_spectated_one():
    with the_fortnight() as s:
        total = s.progress("all").totals
    assert (total.recorded, total.detected, total.certain, total.manual_added, total.manual_removed) == (11, 11, 1, 1, 1)
    assert s.progress("all").spectating_left_out == 1 and len(s.spectated) == 1


def test_an_undone_correction_never_happened():
    with the_fortnight() as s:
        assert not [event for event in s.events if event.manual and event.at == F.moment("2026-11-09 21:56:00")]


def test_a_spectating_chest_counts_when_attribution_is_uncertain():
    for kwargs in ({"english": False, "completion": "unconfirmed"}, {}):
        with recorder() as rec:
            run = rec.run(F.moment("2026-11-09 20:00:00"))
            run.chests(600, 1880).match(1, opened=300, played=360, closed=2000, active=1500, ended=1900, out=1850, **kwargs).end(3600)
            if not kwargs:                                         # marked Not a match: its boundaries are not trusted
                H.correct_match(rec.folder, run.run_id, 1)
            s = snapshot(rec)
        assert s.progress("all").totals.recorded == 2 and not s.spectated, kwargs


def test_simulate_runs_and_their_corrections_are_left_out():
    with recorder() as rec:
        fake = rec.run(F.moment("2026-11-12 10:00:00"), source="simulate").chests(10, 20).end(3600)
        rec.correction(F.moment("2026-11-12 10:30:00"), 1, run_id=fake.run_id)
        rec.run(F.moment("2026-11-12 12:00:00")).chests(10).end(60)
        s = snapshot(rec)
    assert s.progress("all").totals.recorded == 1 and s.progress("all").counting_seconds == 60


def test_a_correction_made_while_not_counting_counts_on_its_day_but_not_in_any_session():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(60).end(3600)
        rec.correction(F.moment("2026-11-12 15:00:00"), 1)                    # Overview +1, app not counting
        s = snapshot(rec)
    today = s.progress("today")
    assert today.totals.recorded == 2 and today.in_sessions == 1 and today.per_hour == 1.0 and s.day(0).totals.recorded == 2


# ------------------------------------------------------------------ periods and chests per hour

def test_all_time_is_session_time_with_its_gap_reported_apart():
    with the_fortnight() as s:
        p = s.progress("all")
    assert p.sessions == 4 and p.session_seconds == 1800 + 7200 + 1800 + 3600 and p.counting_seconds == 1800 + 6000 + 1800 + 3600
    assert p.gap_seconds == 1200 and p.in_sessions == 11 and p.per_hour == 11 / 4 and not p.cut_short


def test_this_week_starts_on_monday():
    with the_fortnight() as s:
        p = s.progress("week")
    assert p.start == F.moment("2026-11-09 00:00:00") and p.sessions == 3 and p.session_seconds == 12600 and p.in_sessions == 7
    assert p.per_hour == 2.0 and (p.totals.recorded, p.totals.detected, p.totals.certain) == (7, 7, 1)


def test_today_takes_only_its_part_of_a_session_across_midnight():
    with the_fortnight() as s:
        p = s.progress("today")
    assert p.start == F.moment("2026-11-12 00:00:00") and p.session_seconds == 1800 and p.counting_seconds == 1800
    assert p.in_sessions == 1 and p.per_hour == 2.0 and p.totals.recorded == 1


def test_last_7_and_30_days():
    with the_fortnight() as s:
        assert s.progress("last7").start == F.moment("2026-11-06 00:00:00") and s.progress("last7").totals.recorded == 11
        assert s.progress("last30").start == F.moment("2026-10-14 00:00:00") and s.progress("last30").totals.recorded == 11


def test_per_hour_is_not_per_minute_times_sixty():
    with the_fortnight() as s:
        p = s.progress("week")
        minute = p.match_summary.complete_rate
    assert minute is not None and p.per_hour == 2.0 and abs(minute.approx_per_minute * 60 - p.per_hour) > 1


def test_half_an_hour_of_session_time_is_needed_for_a_rate():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(60, 120, 180).end(1799)
        assert snapshot(rec).progress("today").per_hour is None
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(60, 120, 180).end(1800)
        assert snapshot(rec).progress("today").per_hour == 6.0


def test_active_play_and_time_between_matches():
    with the_fortnight() as s:
        p = s.progress("week")
    assert p.active_seconds == 1500 and p.between_matches_seconds == 6000 + 1800 + 3600 - 1500
    assert p.active_is_lower_bound                                            # run 2's chests were outside every match
    with recorder() as rec:
        run = rec.run(F.moment("2026-11-12 10:00:00"))
        run.chests(600, 700).match(1, opened=300, played=360, closed=2000, active=1500, ended=1900).end(3600)
        rec.correction(F.moment("2026-11-12 10:50:00"), 1, H.BROKEN_CHEST, run_id=run.run_id)     # yours, outside the match: says nothing about recognition
        p = snapshot(rec).progress("today")
    assert p.active_seconds == 1500 and not p.active_is_lower_bound and p.between_matches_seconds == 2100


def test_no_recognised_match_means_unknown_active_play_not_zero():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(60).end(3600)
        p = snapshot(rec).progress("today")
    assert p.active_seconds is None and p.between_matches_seconds is None


def test_an_interrupted_run_marks_the_period_cut_short():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).beats(1200).crash()
        p = snapshot(rec).progress("today")
    assert p.cut_short and p.counting_seconds == 1200


def test_the_run_counting_now_lasts_until_now():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 17:00:00")).chests(60).beats(120)
        assert snapshot(rec, counting_now=True).progress("today").counting_seconds == 3600
        assert snapshot(rec).progress("today").counting_seconds == 120


# ------------------------------------------------------------------ days and weeks

def test_days_tell_chests_known_zeros_and_not_counted_apart():
    with the_fortnight() as s:
        status = {day.day.day: day.status for day in s.days}
        recorded = {day.day.day: day.totals.recorded for day in s.days}
    assert status == {6: "chests", 7: "not_counted", 8: "not_counted", 9: "chests", 10: "zero", 11: "chests", 12: "chests"}
    assert recorded == {6: 4, 7: 0, 8: 0, 9: 5, 10: 0, 11: 1, 12: 1}


def test_today_and_yesterday():
    with the_fortnight() as s:
        assert s.day(0).totals.recorded == 1 and s.day(-1).totals.recorded == 1 and s.day(-1).day == date(2026, 11, 11)
        assert s.day(-30) is None


def test_the_three_day_averages_use_completed_days_only():
    with the_fortnight() as s:
        a = s.day_averages()
    assert (a.calendar, a.monitored, a.active, a.not_counted) == (6, 4, 3, 2)
    assert a.per_calendar == 10 / 6 and a.per_monitored == 10 / 4 and a.per_active == 10 / 3


def test_weeks_and_their_averages():
    with the_fortnight() as s:
        weeks = s.weeks()
        a = s.week_averages()
        this = s.this_week()
    assert [(w.start, w.recorded) for w in weeks] == [(date(2026, 11, 2), 4), (date(2026, 11, 9), 7)] and this.recorded == 7
    assert (a.per_monitored, a.per_active, a.monitored, a.calendar) == (4, 4, 1, 1)
    assert abs(a.per_calendar - 4 / 3 * 7) < 1e-9                           # 6-8 Nov: three days, 4 chests, as a week


def test_best_day_and_best_week():
    with the_fortnight() as s:
        assert s.best_day().day == date(2026, 11, 9) and s.best_day().totals.recorded == 5
        assert s.best_week().start == date(2026, 11, 9) and s.best_week().recorded == 7


def test_a_tie_goes_to_the_first_day():
    with recorder() as rec:
        rec.run(F.moment("2026-11-10 10:00:00")).chests(60, 120).end(600)
        rec.run(F.moment("2026-11-11 10:00:00")).chests(60, 120).end(600)
        assert snapshot(rec).best_day().day == date(2026, 11, 10)


def test_last_days_starts_where_history_starts():
    with the_fortnight() as s:
        assert [day.day.day for day in s.last_days(7)] == [6, 7, 8, 9, 10, 11, 12]
        assert [day.day.day for day in s.last_days(3)] == [10, 11, 12]
        assert len(s.last_days(30)) == 7


def test_a_daylight_saving_day_is_one_calendar_day():
    with recorder() as rec:
        rec.run(F.moment("2026-10-25 01:00:00")).chests(60, 7000).end(7200)          # 01:00 CEST to 02:00 CET
        s = snapshot(rec, now=F.moment("2026-10-25 23:00:00"))
    assert [day.day for day in s.days] == [date(2026, 10, 25)] and s.day(0).totals.recorded == 2 and s.day(0).counted_seconds == 7200


# ------------------------------------------------------------------ sessions, hours

def test_sessions_newest_first_with_their_rates():
    with the_fortnight() as s:
        rows = s.session_rows()
    assert [row.totals.recorded for row in rows] == [2, 0, 5, 4]
    assert [row.per_hour for row in rows] == [2.0, 0.0, 2.5, 8.0]


def test_the_best_hour_lies_inside_counting():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(*(60 * m for m in (5, 10, 50, 64, 70, 71, 100))).end(7200)
        best = snapshot(rec).best_hour()
    assert best.totals.recorded == 5 and best.start == F.moment("2026-11-12 10:50:00") and best.end == F.moment("2026-11-12 11:50:00")


def test_a_session_shorter_than_an_hour_has_no_best_hour():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(*range(30, 1800, 60)).end(3000)
        assert snapshot(rec).best_hour() is None


def test_a_quick_restart_does_not_break_the_hour_but_a_real_gap_does():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(600, 1200).end(2400)
        rec.run(F.moment("2026-11-12 10:41:00")).chests(600, 1200).end(2400)       # 60 s later
        best = snapshot(rec).best_hour()                                           # 10:10-11:10 holds 10:10, 10:20, 10:51, 11:01
        assert best.totals.recorded == 4 and best.start == F.moment("2026-11-12 10:10:00")
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(600, 1200).end(2400)
        rec.run(F.moment("2026-11-12 10:45:00")).chests(600, 1200).end(2400)       # five minutes later: not counted in between
        assert snapshot(rec).best_hour() is None


def test_a_correction_after_counting_stopped_stays_out_of_the_best_hour():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 10:00:00")).chests(1800).end(3600)
        rec.correction(F.moment("2026-11-12 11:10:00"), 1)
        best = snapshot(rec).best_hour()
    assert best.totals.recorded == 1 and best.start == F.moment("2026-11-12 10:00:00")


def test_corrections_count_in_the_hour():
    with recorder() as rec:
        run = rec.run(F.moment("2026-11-12 10:00:00")).chests(600, 1200).end(3600)
        rec.correction(F.moment("2026-11-12 10:30:00"), 1, H.BROKEN_CHEST, run_id=run.run_id)
        rec.correction(F.moment("2026-11-12 10:31:00"), -1, run_id=run.run_id)
        rec.correction(F.moment("2026-11-12 10:32:00"), 1, run_id=run.run_id)
        best = snapshot(rec).best_hour()
    assert (best.totals.recorded, best.totals.manual_added, best.totals.manual_removed) == (3, 2, 1)


def test_the_current_hour_says_how_much_of_it_was_counted():
    with recorder() as rec:
        rec.run(F.moment("2026-11-12 17:30:00")).chests(60, 600).beats(60)
        now = snapshot(rec, counting_now=True).current_hour()
    assert now.totals.recorded == 2 and now.covered_seconds == 1800
    with the_fortnight() as s:
        assert s.current_hour().totals.recorded == 0 and s.current_hour().covered_seconds == 0


# ------------------------------------------------------------------ nothing known

def test_an_empty_history_has_no_values():
    with recorder() as rec:
        s = snapshot(rec)
    p = s.progress("all")
    assert s.days == [] and s.first_day is None and p.per_hour is None and p.totals.recorded == 0 and p.active_seconds is None
    assert s.best_day() is None and s.best_week() is None and s.best_hour() is None and s.this_week() is None
    a = s.day_averages()
    assert (a.per_calendar, a.per_monitored, a.per_active, a.calendar) == (None, None, None, 0)


def test_reading_changes_no_file():
    with recorder() as rec:
        fortnight(rec)
        before = {f.name: f.read_bytes() for f in rec.folder.iterdir()}
        snapshot(rec)
        assert {f.name: f.read_bytes() for f in rec.folder.iterdir()} == before


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
    print(f"{len(tests) - failed}/{len(tests)} progression checks passed")
    sys.exit(1 if failed else 0)
