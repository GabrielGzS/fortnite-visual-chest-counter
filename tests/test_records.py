"""
Personal Bests (v0.4.0, M3): each best follows its eligibility rule, carries its evidence, and changes when a match is excluded or a
correction undone. Expected values worked out by hand from the two days below (Central European time).

    Mon 9 Nov   20:00-21:10  one run (70 minutes)
                  match 1  Complete, 1300 s active      chests at 20:03:20, 20:05, 20:06:40, 20:08:20      4
                  match 2  Partial (joined late)        chests every 100 s from 20:28:20 to 20:36:40           6, + 2 broken chests (yours)
                  match 3  Complete, only 200 s active  chests at 20:53:20, 20:54:10, 20:55                    3
                  -> the day: 13 detected + 2 = 15
    Tue 10 Nov  10:00-10:40  one run (40 minutes), 10 chests                                               10

Run:   python tests/test_records.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import tempfile
from datetime import date
from pathlib import Path

from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import progression as P
from fortnite_chest_counter import records as R

import history_fixtures as F

NOW = F.moment("2026-11-12 18:00:00")


@contextlib.contextmanager
def recorder():
    with tempfile.TemporaryDirectory() as tmp:
        yield F.Recorder(Path(tmp) / "history" / "p")


def two_days(rec):
    run = rec.run(F.moment("2026-11-09 20:00:00"))
    run.chests(200, 300, 400, 500).match(1, opened=60, played=120, closed=1500, active=1300, ended=1450)
    run.chests(1700, 1800, 1900, 2000, 2100, 2200).match(2, opened=1600, played=1600, closed=3000, active=1300, completion="partial", from_start=False, ended=2900)
    run.chests(3200, 3250, 3300).match(3, opened=3100, played=3150, closed=3400, active=200, ended=3350)
    run.end(4200)
    for minute in (0, 1):
        rec.correction(F.moment("2026-11-09 21:00:00").replace(second=minute), 1, H.BROKEN_CHEST, run_id=run.run_id, match_number=2)
    rec.run(F.moment("2026-11-10 10:00:00")).chests(*range(60, 660, 60)).end(2400)
    return run


def bests(rec, include_manual=False):
    return R.personal_bests(P.load(rec.folder, now=NOW, zone=F.CET, include_manual=include_manual))


@contextlib.contextmanager
def the_two_days():
    with recorder() as rec:
        run = two_days(rec)
        yield rec, run, bests(rec)


def test_every_best_has_a_label():
    assert [key for key, _ in R.BESTS] == ["match_chests", "match_rate", "hour", "day", "week", "session", "session_rate", "longest_session", "match_broken"]


def test_the_best_match_is_complete_even_when_a_partial_one_had_more():
    with the_two_days() as (_, run, b):
        best = b["match_chests"]
    assert best.value == 4 and best.certain == 0 and best.quality == "complete" and best.source == (run.run_id, 1)
    assert best.start == F.moment("2026-11-09 20:01:00") and best.seconds == 1330 and not best.cut_short


def test_the_best_rate_needs_five_minutes_of_play():
    with the_two_days() as (_, run, b):
        best = b["match_rate"]
    assert best.source == (run.run_id, 1) and abs(best.value - 4 / (1300 / 60)) < 1e-9          # match 3 is faster but had 200 s


def test_the_best_rate_follows_the_count_my_plus_ones_setting():
    with recorder() as rec:
        run = two_days(rec)
        rec.correction(F.moment("2026-11-09 20:10:00"), 1, H.BROKEN_CHEST, run_id=run.run_id, match_number=1)
        plain, counted = bests(rec), bests(rec, include_manual=True)
    assert abs(plain["match_rate"].value - 4 / (1300 / 60)) < 1e-9 and abs(counted["match_rate"].value - 5 / (1300 / 60)) < 1e-9
    assert plain["match_chests"].value == 5 and plain["match_chests"].manual_added == 1                # the count always includes it (D3)


def test_most_broken_chests_counts_partial_matches_as_reported():
    with the_two_days() as (_, run, b):
        best = b["match_broken"]
    assert best.value == 2 and best.quality == "partial" and best.source == (run.run_id, 2) and best.certain is None


def test_the_best_hour_is_sixty_counted_minutes_with_its_corrections():
    with the_two_days() as (_, _, b):
        best = b["hour"]
    assert best.value == 15 and best.manual_added == 2 and best.seconds == 3600
    assert best.start == F.moment("2026-11-09 20:03:20") and best.end == F.moment("2026-11-09 21:03:20")


def test_day_week_and_sessions():
    with the_two_days() as (_, _, b):
        assert (b["day"].value, b["day"].start, b["day"].manual_added) == (15, date(2026, 11, 9), 2)
        assert (b["week"].value, b["week"].start) == (25, date(2026, 11, 9))
        assert (b["session"].value, b["session"].start, b["session"].seconds) == (15, F.moment("2026-11-09 20:00:00"), 4200)
        assert abs(b["session_rate"].value - 15 / (4200 / 3600)) < 1e-9 and b["longest_session"].value == 4200


def test_a_session_under_an_hour_has_no_pace_best_and_no_best_hour():
    with recorder() as rec:
        rec.run(F.moment("2026-11-10 10:00:00")).chests(*range(60, 660, 60)).end(2400)
        b = bests(rec)
    assert b["session_rate"] is None and b["hour"] is None and b["session"].value == 10 and b["longest_session"].value == 2400


def test_not_a_match_moves_the_match_bests_and_restore_brings_them_back():
    with recorder() as rec:
        run = two_days(rec)
        H.correct_match(rec.folder, run.run_id, 1)
        excluded = bests(rec)
        H.correct_match(rec.folder, run.run_id, 1, not_a_match=False)
        restored = bests(rec)
    assert excluded["match_chests"].source == (run.run_id, 3) and excluded["match_chests"].value == 3 and excluded["match_rate"] is None
    assert restored["match_chests"].source == (run.run_id, 1)


def test_undoing_a_correction_changes_the_best():
    with recorder() as rec:
        run = two_days(rec)
        added = rec.correction(F.moment("2026-11-09 20:10:00"), 1, run_id=run.run_id, match_number=1)
        before = bests(rec)
        rec.undo(F.moment("2026-11-09 20:11:00"), added, run_id=run.run_id)
        after = bests(rec)
    assert before["match_chests"].value == 5 and after["match_chests"].value == 4 and after["match_chests"].manual_added == 0
    assert before["day"].value == 16 and after["day"].value == 15


def test_a_tie_goes_to_the_first():
    with recorder() as rec:
        run = rec.run(F.moment("2026-11-09 20:00:00"))
        run.chests(200, 300).match(1, opened=60, played=120, closed=1500, active=1300, ended=1450)
        run.chests(1700, 1800).match(2, opened=1600, played=1660, closed=3000, active=1300, ended=2900).end(3600)
        b = bests(rec)
    assert b["match_chests"].source == (run.run_id, 1) and b["match_rate"].source == (run.run_id, 1)


def test_a_match_cut_short_is_marked():
    with recorder() as rec:
        run = rec.run(F.moment("2026-11-09 20:00:00"))
        run.chests(200, 300).match(1, opened=60, played=120, closed=1500, active=1300, ended=1450)
        with open(rec.folder / H.MATCHES, "ab") as f:                     # history lost rows in that match
            f.write(H._encode({"kind": "gap", "schema": 1, "id": "gap:1", "run_id": run.run_id, "at": "2026-11-09T20:30:00.000+01:00",
                               "reason": H.WRITE_FAILED, "match_number": 1, "lost_rows": 1, "missing_certain": 0, "missing_approximate": 1}))
        run.end(3600)
        assert bests(rec)["match_chests"].cut_short


def test_one_load_gives_the_whole_page():
    with recorder() as rec:
        two_days(rec)
        a = R.load(rec.folder, now=NOW, zone=F.CET)
    assert set(a.periods) == {key for key, _ in P.PERIODS} and a.periods["all"].totals.recorded == 25
    assert a.summary.complete == 2 and a.summary.partial == 1 and a.bests["day"].value == 15 and a.snapshot.first_day == date(2026, 11, 9)


def test_nothing_yet_means_no_bests():
    with recorder() as rec:
        b = bests(rec)
        assert set(b) == {key for key, _ in R.BESTS} and all(value is None for value in b.values())
        rec.run(F.moment("2026-11-10 10:00:00")).match(1, opened=60, played=120, closed=1500, active=1300, ended=1450).end(1600)
        b = bests(rec)                                                    # a match and a session with no chest
    assert b["match_chests"] is None and b["match_rate"] is None and b["day"] is None and b["session"] is None and b["hour"] is None
    assert b["longest_session"].value == 1600
    with recorder() as rec:
        rec.run(F.moment("2026-11-10 10:00:00")).end(4000)                # a fully counted hour with no chest is no best hour
        assert bests(rec)["hour"] is None


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
    print(f"{len(tests) - failed}/{len(tests)} personal best checks passed")
    sys.exit(1 if failed else 0)
