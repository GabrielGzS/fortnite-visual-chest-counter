"""
Predictions (v0.5.0): the maths, the pool preset, cycles, rotation, Mark obtained, Undo, the luck wording, the What If? roll, and the
chests read from a real history file with Analytics' rules.

Run:   python tests/test_predictions.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import json
import random
import statistics
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import predictions as R

import history_fixtures as F

UTC = timezone.utc
POOL = R.load_pool()
START = POOL.start


@dataclass(frozen=True)
class Ev:
    at: datetime
    delta: int = 1


def log_of(*moments):
    """Chests at these offsets from the pool's start (timedelta), or (offset, delta) for a correction."""
    return R.ChestLog([Ev(START + m) if isinstance(m, timedelta) else Ev(START + m[0], m[1]) for m in moments])


def spread(count, first, last):
    """`count` chests evenly between two offsets."""
    step = (last - first) / max(count, 1)
    return [first + step * i for i in range(count)]


def reward(rid):
    return next(r for r in POOL.rewards if r.id == rid)


def state(rid, log, actions=(), now=START + timedelta(days=2)):
    return next(s for s in R.progress(POOL, log, list(actions), now) if s.reward.id == rid)


def action(kind, rid, at, undoes=None, aid=None):
    return R.Action(aid or f"a{at.timestamp()}{kind}", kind, at, POOL.id, rid, undoes)


# ------------------------------------------------------------------ maths
def test_milestones_match_the_published_odds():
    got = {r.id: (R.chests_to(0.5, r.p), R.chests_to(0.9, r.p)) for r in POOL.rewards}
    assert got["gizmo"] == (88, 292) and got["weekly_loading_screen"] == (189, 626) and got["weekly_vehicle_decal"] == (5416, 17989)
    assert got["pirate_shop_access"] == (95308, 316605) and got["weekly_gold_outfit"] == (1083043, 3597789)
    for r in POOL.rewards:                                     # the fewest chests that reach it, at every odds
        for m in R.MILESTONES:
            n = R.chests_to(m, r.p)
            assert R.chance(n, r.p) >= m > R.chance(n - 1, r.p), (r.id, m, n)


def test_chance_is_exact_for_tiny_odds_and_never_shown_as_certain():
    assert R.chance(0, 0.5) == 0.0 and abs(R.chance(1, 1 / 1562500) - 1 / 1562500) < 1e-15
    assert abs(R.chance(240, 1 / 127) - 0.8500) < 0.0005
    assert R.percent(R.chance(10_000, 1 / 127)) == ">99.99%" and R.percent(R.chance(1, 1 / 1562500)) == "<0.01%"
    assert R.percent(0.9996) == "99.96%" and R.percent(0.0303) == "3.03%" and R.percent(0.85) == "85.0%" and R.percent(0) == "0%"


def test_hours_and_durations():
    assert R.hours(120, 60) == 2.0 and R.hours(120, None) is None and R.hours(5, 0) is None
    # teammates open 80% as many chests as you: Duo 1.8x, Trio 2.6x, Squad 3.4x your pace
    assert [round(R.team_factor(n), 6) for n in (1, 2, 3, 4)] == [1.0, 1.8, 2.6, 3.4] and abs(R.hours(340, 60, team=4) - 340 / 204) < 1e-12
    assert R.duration(0.25) == "15 min" and R.duration(2.0) == "2.0 h" and R.duration(5277) == "5,277 h (about 220 days nonstop)"


# ------------------------------------------------------------------ the preset
def test_the_shipped_pool_is_valid_and_weekly_windows_follow_the_rotations():
    assert POOL.id == "ch7-treasure-hunters" and POOL.end_estimated and len(POOL.rewards) == 7
    kinds = {r.id: r.kind for r in POOL.rewards}
    assert kinds["gizmo"] == R.REPEATABLE and kinds["pirate_shop_access"] == R.POOL
    assert all(k == R.WEEKLY for rid, k in kinds.items() if rid.startswith("weekly_"))
    weeks = POOL.weeks()
    assert weeks[0][0] == START and weeks[-1][1] == POOL.end and all(a[1] == b[0] for a, b in zip(weeks, weeks[1:]))
    assert all(w[0].weekday() == 6 and w[0].hour == 14 for w in weeks[1:])          # Sundays, 9 AM in New York (14:00 UTC in November)
    rotation = POOL.rotations[0]
    assert POOL.week_of(rotation - timedelta(seconds=1)) == 0 and POOL.week_of(rotation) == 1
    assert POOL.week_of(START - timedelta(days=1)) == 0 and POOL.week_of(POOL.end + timedelta(days=9)) == len(weeks) - 1


def test_a_broken_pool_is_refused():
    good = json.loads(R.DEFAULT_POOL.read_text(encoding="utf-8"))
    for change in ({"format": 2}, {"end": good["start"]}, {"start": "2026-11-01T08:00:00"}, {"rotations": ["2027-01-01T00:00:00Z"]},
                   {"rewards": []}, {"rewards": [{"id": "x", "name": "X", "odds": 1, "kind": "weekly"}]},
                   {"rewards": [{"id": "x", "name": "X", "odds": 9, "kind": "daily"}]}):
        try:
            R.parse_pool({**good, **change})
        except R.PoolError:
            continue
        raise AssertionError(f"accepted {change}")


# ------------------------------------------------------------------ cycles
def test_gizmo_cycles_restart_by_themselves_and_are_never_obtained():
    log = log_of(*spread(1000, timedelta(hours=1), timedelta(hours=40)))
    s = state("gizmo", log)
    assert s.pool_chests == 1000 and s.completed_cycles == 3 and s.cycle_chests == 1000 - 3 * 292 and s.milestone_chests == 292
    assert abs(s.expected - 1000 / 127) < 1e-9 and s.obtained is None and not s.frozen
    assert abs(s.chance - R.chance(124, 1 / 127)) < 1e-12 and s.remaining == {0.5: 0, 0.9: 292 - 124}


def test_a_weekly_reward_starts_again_at_the_rotation_and_its_expected_number_covers_the_pool():
    rotation = POOL.rotations[0] - START
    log = log_of(*spread(500, timedelta(hours=1), rotation - timedelta(hours=1)), *spread(100, rotation + timedelta(hours=1), rotation + timedelta(hours=20)))
    s = state("weekly_loading_screen", log, now=START + rotation + timedelta(days=1))
    assert s.week == 1 and s.weeks == len(POOL.weeks()) and s.cycle_chests == 100 and s.pool_chests == 600
    assert abs(s.chance - R.chance(100, 1 / 272)) < 1e-12 and abs(s.expected - 600 / 272) < 1e-9
    assert s.window == POOL.weeks()[1] and s.cycle_start == POOL.rotations[0]
    last_week = state("weekly_loading_screen", log, now=START + rotation - timedelta(minutes=1))
    assert last_week.week == 0 and last_week.cycle_chests == 500


def test_start_new_cycle_keeps_the_expected_number_and_undo_restores_the_cycle():
    log = log_of(*spread(300, timedelta(hours=1), timedelta(hours=30)))
    restart = action(R.RESTART, "pirate_shop_access", START + timedelta(hours=16), aid="r1")
    s = state("pirate_shop_access", log, [restart])
    assert s.cycle_start == restart.at and 0 < s.cycle_chests < 300 and s.pool_chests == 300 and abs(s.expected - 300 / 137500) < 1e-12
    assert s.last_action is restart
    undone = state("pirate_shop_access", log, [restart, action(R.UNDO, "pirate_shop_access", START + timedelta(hours=31), undoes="r1")])
    assert undone.cycle_chests == 300 and undone.cycle_start == START and undone.last_action is None


def test_mark_obtained_stops_the_chance_records_how_lucky_it_was_and_a_new_cycle_counts_again():
    log = log_of(*spread(400, timedelta(hours=1), timedelta(hours=40)))
    got = action(R.OBTAINED, "weekly_jam_track", START + timedelta(hours=11), aid="o1")       # after about 100 chests
    by_then = log.count(START, got.at)
    s = state("weekly_jam_track", log, [got])
    assert 95 < by_then < 110 and s.frozen and s.obtained is got and s.remaining is None and s.cycle_chests == by_then
    assert abs(s.obtained_chance - R.chance(by_then, 1 / 391)) < 1e-12 and s.pool_chests == 400
    assert R.insight(s).heading in ("Lucky find!", "Incredibly lucky!") and R.insight(s).level in (R.LUCKY, R.VERY_LUCKY)
    again = state("weekly_jam_track", log, [got, action(R.RESTART, "weekly_jam_track", START + timedelta(hours=21), aid="r2")])
    assert not again.frozen and again.obtained is got and 0 < again.cycle_chests < 300                # still reported; a new cycle counts
    back = state("weekly_jam_track", log, [got, action(R.UNDO, "weekly_jam_track", START + timedelta(hours=12), undoes="o1")])
    assert back.obtained is None and back.cycle_chests == 400


def test_a_report_belongs_to_its_week_and_gizmos_cannot_be_marked():
    rotation = POOL.rotations[0]
    log = log_of(*spread(50, timedelta(hours=1), timedelta(hours=20)))
    got = action(R.OBTAINED, "weekly_vehicle_decal", START + timedelta(hours=10))
    assert state("weekly_vehicle_decal", log, [got]).frozen
    assert state("weekly_vehicle_decal", log, [got], now=rotation + timedelta(hours=1)).obtained is None     # next week: a new reward
    assert state("gizmo", log, [action(R.OBTAINED, "gizmo", START + timedelta(hours=10))]).obtained is None


def test_corrections_count_and_nothing_before_the_pool_or_after_now():
    log = log_of(timedelta(hours=-5), timedelta(hours=1), timedelta(hours=2), (timedelta(hours=3), -1), timedelta(days=5))
    s = state("pirate_shop_access", log, now=START + timedelta(days=1))
    assert s.pool_chests == 1 and s.cycle_chests == 1
    before = state("pirate_shop_access", log, now=START - timedelta(hours=1))
    assert not before.started and before.pool_chests == 0 and before.chance == 0.0


def test_a_pool_that_ended_stops_counting():
    log = log_of(timedelta(days=1), POOL.end - START + timedelta(hours=2))
    s = state("pirate_shop_access", log, now=POOL.end + timedelta(days=3))
    assert s.ended and s.pool_chests == 1


# ------------------------------------------------------------------ Treasure Hours
def with_hours(*hours):
    data = json.loads(R.DEFAULT_POOL.read_text(encoding="utf-8"))
    data["treasure_hours"] = [{"start": (START + a).isoformat(), "end": (START + b).isoformat(), "multipliers": m} for a, b, m in hours]
    return R.parse_pool(data)


def test_chests_in_a_treasure_hour_count_at_their_boosted_odds():
    """800 chests at 1 in 137,500 and 200 during a 2x hour: 1 - (1-p)^800 (1-2p)^200, about 0.87%, not 0.72% and not 1.45%."""
    pool = with_hours((timedelta(hours=10), timedelta(hours=12), {"pirate_shop_access": 2, "weekly_vehicle_decal": 10}))
    log = log_of(*spread(800, timedelta(hours=1), timedelta(hours=9)), *spread(200, timedelta(hours=10), timedelta(hours=11, minutes=59)))
    s = next(x for x in R.progress(pool, log, [], START + timedelta(days=1)) if x.reward.id == "pirate_shop_access")
    p = 1 / 137500
    exact = 1 - (1 - p) ** 800 * (1 - 2 * p) ** 200
    assert abs(s.chance - exact) < 1e-12 and abs(exact - 0.00869) < 0.00001 and s.cycle_chests == 1000 and s.boosted == 200
    assert abs(s.expected - (800 * p + 200 * 2 * p)) < 1e-12
    assert s.remaining[0.9] == R.more_to(0.9, p, s.cycle_effective) and R.chance(s.cycle_effective + s.remaining[0.9], p) >= 0.9   # forecasts at normal odds
    gizmo = next(x for x in R.progress(pool, log, [], START + timedelta(days=1)) if x.reward.id == "gizmo")
    assert gizmo.boosted == 0 and gizmo.completed_cycles == 1000 // 292                 # a reward the hour does not name keeps its odds


def test_a_treasure_hour_boosts_only_its_own_window():
    pool = with_hours((timedelta(hours=10), timedelta(hours=11), {"weekly_vehicle_decal": 10}))
    at = lambda h: R.progress(pool, log_of(timedelta(hours=h)), [], START + timedelta(days=1))
    vehicle = lambda h: next(x for x in at(h) if x.reward.id == "weekly_vehicle_decal")
    assert vehicle(10).boosted == 1 and vehicle(11).boosted == 0 and vehicle(9.99).boosted == 0      # start included, end excluded
    assert abs(vehicle(10).chance - 10 / 7813) < 1e-12 and abs(vehicle(11).chance - 1 / 7813) < 1e-12


def test_a_bad_treasure_hour_is_refused_and_the_shipped_pool_boosts_nothing():
    assert R.load_pool().treasure_hours == ()
    for hours in ([(timedelta(hours=2), timedelta(hours=1), {"gizmo": 2})], [(timedelta(hours=1), timedelta(hours=2), {"nope": 2})],
                  [(timedelta(hours=1), timedelta(hours=2), {"gizmo": 0.5})], [(timedelta(hours=1), timedelta(hours=2), {"gizmo": 200})],
                  [(timedelta(hours=1), timedelta(hours=3), {"gizmo": 2}), (timedelta(hours=2), timedelta(hours=4), {"gizmo": 2})]):
        try:
            with_hours(*hours)
        except R.PoolError:
            continue
        raise AssertionError(f"accepted {hours}")


def test_what_if_multipliers_shorten_the_hunt():
    pirate = reward("pirate_shop_access")
    normal = statistics.median(R.roll(pirate, rng=random.Random(3)).chests for _ in range(4000))
    boosted = statistics.median(R.roll(pirate, rng=random.Random(3), multiplier=2.0).chests for _ in range(4000))
    assert 0.4 < boosted / normal < 0.6 and R.MULTIPLIERS == (1.0, 1.5, 2.0, 7.5, 10.0)


# ------------------------------------------------------------------ chests added with Edit counts
def adjust(delta, at, scope=R.SEASON, week=None, aid=None):
    return R.Action(aid or f"adj{at.timestamp()}{delta}", R.ADJUST, at, POOL.id, "", None, R.MANUAL, delta, scope, week)


def test_chests_added_for_the_season_count_for_season_rewards_only():
    log = log_of(*spread(2400, timedelta(hours=1), timedelta(hours=40)))
    rows = [adjust(5000, START + timedelta(hours=41))]
    now = START + timedelta(days=2)
    pirate, gizmo, weekly = (state(rid, log, rows, now) for rid in ("pirate_shop_access", "gizmo", "weekly_loading_screen"))
    p = 1 / 137500
    assert pirate.added == 5000 and pirate.cycle_chests == 7400 and abs(pirate.chance - R.chance(7400, p)) < 1e-12
    assert pirate.pool_chests == 2400 and abs(pirate.expected - 7400 * p) < 1e-12                  # recorded stays recorded
    assert gizmo.completed_cycles == 7400 // 292 and gizmo.cycle_chests == 7400 % 292
    assert weekly.added == 0 and weekly.cycle_chests == 2400 and abs(weekly.expected - 7400 / 272) < 1e-9   # no week known: not this week's


def test_chests_added_for_a_week_count_for_that_week_and_the_season():
    rotation = POOL.rotations[0]
    log = log_of(*spread(100, timedelta(hours=1), timedelta(hours=20)))
    rows = [adjust(3000, rotation + timedelta(hours=2), R.WEEK, 0), adjust(500, rotation + timedelta(hours=3), R.WEEK, 1)]
    now = rotation + timedelta(hours=5)
    weekly = state("weekly_vehicle_decal", log, rows, now)
    assert weekly.week == 1 and weekly.added == 500 and weekly.cycle_chests == 500        # this week: only this week's
    last_week = state("weekly_vehicle_decal", log, rows, rotation - timedelta(minutes=1) + timedelta(hours=0))
    assert last_week.added == 0                                                            # rows made after that moment do not exist yet
    assert state("pirate_shop_access", log, rows, now).cycle_chests == 3600 and R.added(POOL, rows, now).unknown_week == 0


def test_a_lower_count_takes_back_never_below_zero_and_undo_and_restart_leave_them_out():
    log = log_of(*spread(100, timedelta(hours=1), timedelta(hours=20)))
    now = START + timedelta(days=2)
    rows = [adjust(5000, START + timedelta(hours=21), aid="a1"), adjust(-2000, START + timedelta(hours=22))]
    assert state("pirate_shop_access", log, rows, now).added == 3000
    assert state("pirate_shop_access", log, [adjust(-50, START + timedelta(hours=21))], now).added == 0
    undone = rows[:1] + [action(R.UNDO, "", START + timedelta(hours=23), undoes="a1")]
    assert state("pirate_shop_access", log, undone, now).added == 0
    restarted = rows[:1] + [action(R.RESTART, "pirate_shop_access", START + timedelta(hours=30))]
    s = state("pirate_shop_access", log, restarted, now)
    assert s.added == 5000 and s.cycle_chests == 0 and abs(s.expected - 5100 / 137500) < 1e-12      # the new cycle starts after them


def test_added_chests_never_get_treasure_hour_odds_and_never_change_pace_or_analytics():
    pool = with_hours((timedelta(hours=0), timedelta(hours=30), {"pirate_shop_access": 2}))
    rows = [adjust(1000, START + timedelta(hours=5))]
    s = next(x for x in R.progress(pool, log_of(), rows, START + timedelta(days=1)) if x.reward.id == "pirate_shop_access")
    assert s.cycle_chests == 1000 and s.boosted == 0 and abs(s.chance - R.chance(1000, 1 / 137500)) < 1e-12
    from fortnite_chest_counter import progression as P
    with tempfile.TemporaryDirectory() as tmp:
        rec = F.Recorder(Path(tmp))
        rec.run(START + timedelta(hours=2)).chests(*range(60, 3600, 60)).end(3600)
        before = P.load(rec.folder, now=START + timedelta(days=1)).progress("all")
        R.append_action(rec.folder, R.ADJUST, POOL.id, "", delta=5000, scope=R.SEASON, at=START + timedelta(hours=5))
        after = P.load(rec.folder, now=START + timedelta(days=1)).progress("all")
        assert (before.totals, before.in_sessions, before.per_hour) == (after.totals, after.in_sessions, after.per_hour)
        view = R.load_view(rec.folder, POOL, now=START + timedelta(days=1))
        assert view.season_chests == 59 and view.added.season == 5000 and abs(view.rate - before.per_hour) < 1e-12
        try:
            R.append_action(rec.folder, R.ADJUST, POOL.id, "", delta=5, scope=R.WEEK)          # a week row needs its week
        except ValueError:
            pass
        else:
            raise AssertionError("a week row without a week was written")


def test_repeated_edits_never_count_the_same_chests_twice():
    """The maintainer's sequence: 2,000 recorded; edit to 7,000; 100 real chests; edit to 7,200 (adds 100, not 5,200); edit down to 7,000
    (takes 200 back); Reset; type 7,000 back in (adds nothing). Predictions always use what the counter says, never more."""
    rows, counter, recorded, t = [], 2000, 2000, [START + timedelta(hours=1)]

    def now_added():
        return R.added(POOL, R.effective(rows), START + timedelta(days=2))

    def edit(new_total):
        nonlocal counter
        change = R.reconcile(counter, new_total, recorded, now_added())
        if change:
            t[0] += timedelta(minutes=1)
            rows.append(adjust(change, t[0]))
        counter = new_total
        return change

    assert edit(7000) == 5000 and recorded + now_added().season == 7000
    counter, recorded = counter + 100, recorded + 100                     # 100 real chests, counted and recorded
    assert edit(7200) == 100 and recorded + now_added().season == 7200
    assert edit(7000) == -200 and recorded + now_added().season == 7000
    counter = 0                                                           # Reset: the counter only; predictions keep their chests
    assert edit(7000) == 0 and recorded + now_added().season == 7000
    assert edit(500) == -4900 and now_added().season == 0                 # below the recorded: everything added comes back, nothing more
    assert edit(0) == 0 and now_added().season == 0                       # no negative chests
    assert R.reconcile(0, 3000, 2100, R.added(POOL, [], START + timedelta(days=2))) == 900   # a reset mid-season: only above the recorded
    lifetime = R.reconcile(20000, 25000, 3000, R.added(POOL, [], START + timedelta(days=2)))
    assert lifetime == 5000                                               # a counter holding earlier seasons is not limited by them


# ------------------------------------------------------------------ wording
def test_luck_wording_follows_the_chance_and_is_conditional_without_a_report():
    log_n = lambda n: log_of(*spread(n, timedelta(hours=1), timedelta(hours=30)))
    pirate = lambda n: R.insight(state("pirate_shop_access", log_n(n)))
    assert pirate(10).heading == "Still early" and pirate(10).level == R.EARLY and ">99.99%" in pirate(10).text
    found = {n: R.insight(state("weekly_loading_screen", log_n(n))) for n in (30, 189, 350, 500, 700, 1300)}
    assert [i.level for i in found.values()] == [R.EARLY, R.TYPICAL, R.BEHIND, R.UNCOMMON, R.UNLUCKY, R.TERRIBLE]
    assert "if you are still waiting" in found[700].heading and "same chance" in found[700].text        # never a fact without a report
    assert "if you are still waiting" in found[1300].heading
    assert R.insight(state("gizmo", log_n(100))).level == R.CYCLE


# ------------------------------------------------------------------ What If?
def test_the_roll_is_a_geometric_draw():
    rng = random.Random(7)
    gizmo = reward("gizmo")
    draws = [R.roll(gizmo, rng=rng).chests for _ in range(20_000)]
    assert min(draws) >= 1 and abs(statistics.median(draws) - 88) <= 4 and abs(statistics.fmean(draws) - 127) <= 4
    r = R.roll(reward("pirate_shop_access"), team=4, rate=60, rng=random.Random(1))
    assert 0 <= r.finder < 4 and r.team == 4 and abs(r.hours - r.chests / 204) < 1e-9 and abs(r.earlier + r.later + (1 / 137500) * (1 - 1 / 137500) ** (r.chests - 1) - 1) < 1e-9
    finders = [R.roll(gizmo, team=4, rng=rng).finder for _ in range(20_000)]
    assert abs(finders.count(0) / 20_000 - 1 / 3.4) < 0.02 and all(abs(finders.count(k) / 20_000 - 0.8 / 3.4) < 0.02 for k in (1, 2, 3))
    assert R.roll(gizmo, rate=None, rng=random.Random(2)).hours is None
    assert R.finder_name(R.Roll(5, 0, 1, None, 0.1, 0.8)) == "You" and R.finder_name(R.Roll(5, 2, 4, None, 0.1, 0.8)) == "Teammate 2"
    assert [R.roll_verdict(R.Roll(5, 0, 1, None, e, l)).level for e, l in ((0.02, 0.95), (0.1, 0.85), (0.4, 0.55), (0.7, 0.25), (0.97, 0.02))] ==         [R.VERY_LUCKY, R.LUCKY, R.TYPICAL, R.UNLUCKY, R.TERRIBLE]
    v = R.roll_verdict(R.Roll(112528, 0, 1, None, 0.559, 0.44))
    assert v.heading == "Pretty average luck" and v.text == "This time it took 112,528 chests. About 55.9% of first drops happen sooner."


# ------------------------------------------------------------------ storage and the real history
def test_actions_are_appended_read_back_and_bad_lines_are_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        assert R.read_actions(folder) == ([], 0)
        first = R.append_action(folder, R.RESTART, POOL.id, "gizmo", chests=12)
        R.append_action(folder, R.UNDO, POOL.id, "gizmo", undoes=first)
        with open(folder / R.ACTIONS_FILE, "ab") as f:
            f.write(b'{"kind":"prediction_restart","schema":1,"id":"x"\n{"kind":"prediction_restart","schema":99,"id":"y","at":"2026-11-02T00:00:00Z","pool":"p","reward":"r"}\n')
        actions, bad = R.read_actions(folder)
        assert [a.kind for a in actions] == [R.RESTART, R.UNDO] and bad == 2 and R.effective(actions) == []
        assert actions[0].at.tzinfo is not None and actions[0].source == R.MANUAL


def test_the_history_reader_ignores_the_predictions_file():
    """Rollback safety: predictions.jsonl sits in the profile's history folder, and v0.4.x reads only its own files there."""
    with tempfile.TemporaryDirectory() as tmp:
        rec = F.Recorder(Path(tmp))
        rec.run(START + timedelta(hours=2)).chests(60, 120).end(600)
        R.append_action(rec.folder, R.RESTART, POOL.id, "gizmo")
        history = H.read(rec.folder)
        assert history.bad_lines == 0 and len(history.chests) == 2


def test_the_view_reads_chests_with_the_analytics_rules():
    with tempfile.TemporaryDirectory() as tmp:
        rec = F.Recorder(Path(tmp))
        rec.run(START - timedelta(hours=3)).chests(60).end(600)                       # last season: not in the pool
        rec.run(START + timedelta(hours=2)).chests(*range(60, 3600, 60)).end(3600)    # 59 chests in an hour
        rec.correction(START + timedelta(hours=2, minutes=30), 1)                      # a +1 counts
        rec.run(START + timedelta(hours=5), source="simulate").chests(60, 120).end(600)   # a test run: nobody's play
        view = R.load_view(rec.folder, POOL, now=START + timedelta(days=1))
        assert view.season_chests == 60 and view.first_chest is not None and view.bad_lines == 0
        # pace is v0.4.0's chests per real-life hour over the last 7 days, last season's run included: 61 chests in 70 minutes
        assert abs(view.rate - 61 / (70 / 60)) < 1e-9 and view.rate_period == "last 7 days"
        gizmo = next(s for s in view.states if s.reward.id == "gizmo")
        assert gizmo.cycle_chests == 60 and gizmo.completed_cycles == 0


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
    print(f"{len(tests) - failed}/{len(tests)} prediction checks passed")
    sys.exit(1 if failed else 0)
