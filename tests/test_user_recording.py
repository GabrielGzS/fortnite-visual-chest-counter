"""
The maintainer's own recording (v0.4.1 M0): what v0.4.0's match tracking makes of it, against the recording's truth.

tests/fixtures/match/user_20261112_observations.json.gz holds every Observation the real pipeline fed to the match state machine on
samples/video tests/2026-11-12 12-52-32.mp4 (research/pipeline_baseline.py, then trimmed), and how the run finished. Replaying them must
give v0.4.0's two records exactly. The truth (tests/cases/user_20261112.json) says the second match was observed from its countdown to
YOU PLACED, so it should be Complete; that gap is pinned here until v0.4.1 fixes the cues, when the fixture is regenerated and this test
is changed to require Complete. Active time is pinned the same way: it is a v0.4.1 goal, not only Complete versus Partial.

These first fixtures are the Standard HUD setting, which stays as it is for every other player. The maintainer plays at Fortnite HUD
Scale 75%: user_20261112_observations_hud75.json.gz is the same pipeline with the profile's HUD set to 75% (simulate --hud 75), where the
match text is read with native templates. Those templates were cut from this recording, so it shows the setting works on its source,
not that it generalises (V0_4_1_VALIDATION.md).

Run:   python tests/test_user_recording.py     (or pytest)
"""

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "src"))   # run without installing

import gzip
import json
from pathlib import Path

from fortnite_chest_counter import match_state as S

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "match" / "user_20261112_observations.json.gz"
FIXTURE75 = HERE / "fixtures" / "match" / "user_20261112_observations_hud75.json.gz"
TRUTH = json.loads((HERE / "cases" / "user_20261112.json").read_text(encoding="utf-8"))


def replay(fixture=FIXTURE):
    data = json.loads(gzip.open(fixture, "rt", encoding="utf-8").read())
    machine, events = S.MatchStateMachine(), []
    for row in data["observations"]:
        row = dict(row, chests=tuple(row["chests"]))
        events += machine.update(S.Observation(**row))
    events += machine.finish(data["finish"]["t"], data["finish"]["reason"])
    return [e for e in events if isinstance(e, S.MatchRecord)], [e for e in events if isinstance(e, S.Transition)], data


def test_fixture_is_the_real_pipeline_input():
    for fixture in (FIXTURE, FIXTURE75):
        check_fixture(fixture)


def check_fixture(fixture):
    _, _, data = replay(fixture)
    assert data["source"]["sha256"] == TRUTH["sha256"]
    rows = data["observations"]
    assert len(rows) >= 1470 and all(b["t"] > a["t"] for a, b in zip(rows, rows[1:]))
    # live-only fields, measured as match_tracker measures them: the green bar only beside a health bar, the HUD only when nothing else
    # (health bar, chest, text) shows the game. A replay cache (research/match_replay.py) has neither.
    assert all((r["health_green_pixels"] is None) == (r["health_bar_pixels"] < S.HEALTH_BAR_MIN_PIXELS) for r in rows)
    assert all((r["hud_in_view"] is None) == (r["health_bar_pixels"] >= S.HEALTH_BAR_MIN_PIXELS or bool(r["chests"])
                                              or max(r["scores"].values(), default=0) >= S.SCORE_THRESHOLD) for r in rows)
    assert sum(r["hud_in_view"] is not None for r in rows) > 50 and sum(r["health_green_pixels"] is not None for r in rows) > 1000


def test_records_are_reproduced_exactly():
    """v0.4.0: match 1 469 s of play, match 2 974 s and open until the video stopped. v0.4.1: the READY overlay ends match 1's play
    (377 s), the brief ELIMINATED BY ends match 2's (945 s), and the grey CONNECTING of the return-to-lobby splash closes it at 1465 s."""
    records, _, _ = replay()
    got = [(r.match_number, r.completion, r.ended_by, r.opened_t, round(r.closed_t, 2), r.active_seconds) for r in records]
    assert got == [(1, "partial", "left_or_unknown", 0.0, 484.0, 377.0), (2, "partial", "left_or_unknown", 489.0, 1465.0, 945.0)], got


def test_v041_gap_the_fully_observed_match_is_not_complete():
    records, transitions, _ = replay()
    truth = {m["id"]: m for m in TRUTH["matches"]}
    assert truth["m2-full-placed-3"]["completion"] == "complete"
    m2 = records[1]
    assert m2.completion == "partial" and not m2.observed_from_start            # the 0.90x countdown is never read
    assert m2.ended_t is None                                                      # YOU PLACED (0.90x) is not read
    assert not any(t.state == S.PRE_GAME for t in transitions)                     # the 0.90x countdown is not read
    out = [(round(t.t), t.reason) for t in transitions if t.state == S.ELIMINATED]
    assert out == [(392, "ready_overlay_seen"), (1434, "eliminated_by_seen")], out        # v0.4.1: READY overlay, brief ELIMINATED BY
    loading = [(round(t.t), t.reason) for t in transitions if t.state == S.LOADING]
    assert loading == [(484, "connecting_seen"), (1465, "connecting_seen")], loading      # 1465: the grey CONNECTING


def test_v041_gap_active_time_includes_screens_that_are_not_play():
    records, _, _ = replay()
    truth = {m["id"]: m for m in TRUTH["matches"]}
    true_m2 = truth["m2-full-placed-3"]["active"][1] - truth["m2-full-placed-3"]["active"][0]
    true_m1 = truth["m1-rebooted-win"]["active"][1] - truth["m1-rebooted-win"]["active"][0]
    assert round(records[1].active_seconds - true_m2) == 33             # the waiting island counted as play (v0.4.0: 62, after death too)
    assert round(records[0].active_seconds - true_m1) == 40             # waiting for a reboot, Victory and recap (v0.4.0: 132, the READY overlay too)


def test_hud75_the_fully_observed_match_is_complete():
    """The countdown (WAITING FOR PLAYERS at 490 s), the bus and YOU PLACED are read at 75%, so match 2 is Complete and ended by its
    placement. Match 1 began before the recording, so it stays Partial, and ends by its Victory Royale."""
    records, transitions, data = replay(FIXTURE75)
    assert data["source"]["hud"] == "75"
    got = [(r.match_number, r.completion, r.ended_by, r.opened_t, round(r.closed_t, 2), r.active_seconds) for r in records]
    assert got == [(1, "partial", "victory", 0.0, 484.0, 364.0), (2, "complete", "placed", 489.0, 1465.0, 913.0)], got
    truth = {m["id"]: m for m in TRUTH["matches"]}["m2-full-placed-3"]
    m2 = records[1]
    assert m2.completion == truth["completion"] and m2.ended_by == truth["ended_by"] and m2.observed_from_start
    assert abs(m2.ended_t - truth["ended_t"]) <= 1.0 and abs(m2.played_from_t - truth["played_from_t"]) <= 1.0
    pre = [(round(t.t), t.reason) for t in transitions if t.state == S.PRE_GAME]
    assert pre == [(490, "countdown_seen")], pre                                      # the countdown begins at 488 s


def test_hud75_active_time():
    records, _, _ = replay(FIXTURE75)
    truth = {m["id"]: m for m in TRUTH["matches"]}
    true_m2 = truth["m2-full-placed-3"]["active"][1] - truth["m2-full-placed-3"]["active"][0]
    true_m1 = truth["m1-rebooted-win"]["active"][1] - truth["m1-rebooted-win"]["active"][0]
    assert abs(records[1].active_seconds - true_m2) <= 2.0                     # 913 s against 912.3 s: bus to YOU PLACED
    # match 1: the first 24 s are the wait for a reboot, which the v0.3.0 rule cannot tell from play (a design question, see the truth)
    assert round(records[0].active_seconds - true_m1) == 27


if __name__ == "__main__":
    passed = 0
    for name, test in list(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
            print(f"  ok    {name}")
            passed += 1
    print(f"{passed}/{passed} user recording checks passed")
