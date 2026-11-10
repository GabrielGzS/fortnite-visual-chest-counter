"""Permanent audit regressions; the initial 16 checks were RED against M2 d691310.

These assert the desired conservative behavior, not the buggy implementation.
Run separately before/after the proposed fixes: python tests/test_match_state_defects.py.
No footage, sleeps, image libraries or profile state are involved.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_match_state import Script, played_match, HP, S


def consistent(record):
    span = record.closed_t - record.opened_t
    assert span >= 0
    assert all(t >= 0 for t in (record.observed_seconds, record.active_seconds, record.spectating_seconds, record.uncertain_seconds))
    assert abs(record.observed_seconds + record.uncertain_seconds - span) < 0.005, record
    assert record.active_seconds + record.spectating_seconds <= record.observed_seconds + 0.005, record


def test_loading_language_does_not_cross_missing_footage():
    r = Script().show(5, "connecting").jump(20).show(12, health=HP).finish().records[0]
    assert not r.english_confirmed and r.completion == S.UNCONFIRMED, r


def test_loading_language_does_not_cross_black_footage():
    r = Script().show(5, "connecting").show(8, black=True).show(12, health=HP).finish().records[0]
    assert not r.english_confirmed and r.completion == S.UNCONFIRMED, r


def test_loading_language_does_not_cross_frozen_footage():
    r = Script().show(5, "connecting").show(8, frozen=True).show(12, health=HP).finish().records[0]
    assert not r.english_confirmed and r.completion == S.UNCONFIRMED, r


def test_continuous_loading_can_still_confirm_the_next_match():
    r = Script().show(5, "connecting").show(12, health=HP).finish().records[0]
    assert r.english_confirmed and r.completion == S.PARTIAL


def test_a_short_black_loading_interruption_keeps_continuous_evidence():
    r = Script().show(5, "connecting").show(2, black=True).show(12, health=HP).finish().records[0]
    assert r.english_confirmed and r.completion == S.PARTIAL


def test_fresh_confirmed_loading_restores_language_after_a_break():
    for kind in ("gap", "black", "frozen"):
        s = Script().show(5, "connecting")
        s.jump(20) if kind == "gap" else s.show(8, **{kind: True})
        r = s.show(2, "connecting").show(12, health=HP).finish().records[0]
        assert r.english_confirmed and r.completion == S.PARTIAL, kind


def test_one_loading_hit_after_a_break_cannot_reuse_the_old_confirmation():
    r = Script().show(5, "connecting").jump(20).show(1, "connecting").show(12, health=HP).finish().records[0]
    assert not r.english_confirmed and r.completion == S.UNCONFIRMED


def test_pending_pregame_language_also_cannot_cross_a_break():
    for kind in ("gap", "black", "frozen"):
        s = Script().show(8, "waiting_for_players", health=HP)
        s.jump(20) if kind == "gap" else s.show(8, **{kind: True})
        r = s.show(6).finish().records[0]
        consistent(r)
        assert not r.english_confirmed and r.completion == S.UNCONFIRMED and not r.observed_from_start, kind


def test_fresh_pregame_text_can_confirm_language_without_repairing_the_break():
    r = Script().show(8, "waiting_for_players", health=HP).show(8, black=True).show(4, "bus_launching", health=HP).show(6).finish().records[0]
    assert r.english_confirmed and r.completion == S.PARTIAL and r.discontinuity and not r.observed_from_start
    consistent(r)


def test_disappearing_spectating_text_does_not_prove_a_respawn():
    s = played_match().show(10, "spectating")
    s.show(60, health=HP)
    assert not [e for e in s.events if isinstance(e, S.Transition) and e.reason == "respawned"], s.path
    r = s.finish().records[0]
    assert r.respawns == 0


def test_disappearing_placement_does_not_restore_active_play_from_HUD():
    s = played_match().show(6, "you_placed").show(30, health=HP)
    assert s.state != S.IN_MATCH, s.path
    r = s.finish().records[0]
    assert r.respawns == 0


def test_starting_on_an_end_screen_cannot_invent_a_match_from_a_spectator_HUD():
    for signal in ("you_placed", "spectating", "victory_royale"):
        s = Script().show(8, signal).show(120, health=HP).finish()
        assert not s.records and S.IN_MATCH not in s.path, signal


def test_uncertain_recovery_does_not_contaminate_a_later_observed_match():
    s = played_match().show(8, "spectating").show(20, health=HP).show(6, "you_placed").show(4, "connecting")
    played_match(s).show(6, "you_placed").finish()
    first, second = s.records
    assert first.completion == S.PARTIAL and second.completion == S.COMPLETE
    assert first.respawns == second.respawns == 0 and second.opened_t >= first.closed_t
    consistent(first)
    consistent(second)


def test_long_missing_gap_durations_fit_the_closed_record():
    s = played_match().jump(120).show(1, health=HP)
    assert len(s.records) == 1 and s.records[0].ended_by == S.LOST
    consistent(s.records[0])


def test_no_evidence_timeout_durations_fit_the_closed_record():
    s = played_match().show(61)
    assert len(s.records) == 1 and s.records[0].ended_by == S.LOST
    consistent(s.records[0])


def test_no_evidence_after_elimination_durations_fit_the_closed_record():
    s = played_match().show(6, "you_placed").show(61)
    assert len(s.records) == 1 and s.records[0].ended_by == S.PLACED
    consistent(s.records[0])


def test_normal_black_and_frozen_intervals_keep_consistent_time():
    for signal in ("black", "frozen"):
        s = played_match().show(8, **{signal: True}).show(10, health=HP).finish()
        consistent(s.records[0])
        assert s.records[0].completion == S.PARTIAL


def test_stopping_after_a_missing_tail_accounts_for_that_tail():
    s = played_match().jump(20).finish()
    consistent(s.records[0])
    assert s.records[0].uncertain_seconds >= 20 and s.records[0].discontinuity


def test_stopping_on_black_does_not_add_active_time():
    s = played_match().show(8, black=True)
    before = s.machine._match.active
    r = s.finish().records[0]
    consistent(r)
    assert r.active_seconds == before and r.uncertain_seconds == 9, r


def test_a_break_after_countdown_does_not_become_active_time():
    s = Script().show(8, "waiting_for_players", health=HP).show(20, black=True).show(6).finish()
    assert len(s.records) == 1
    r = s.records[0]
    consistent(r)
    assert r.completion != S.COMPLETE and r.active_seconds == 6 and r.played_from_t == 28, r


def test_uncertainty_before_a_fresh_countdown_is_not_subtracted_from_later_play():
    s = Script().show(8, "waiting_for_players", health=HP).show(8, black=True).show(4, "bus_launching", health=HP).show(6).show(10, health=HP).finish()
    r = s.records[0]
    consistent(r)
    assert r.active_seconds == r.closed_t - r.played_from_t and r.uncertain_seconds == 8


def test_missing_stop_tail_after_an_observed_ending_keeps_that_ending_complete():
    r = played_match().show(6, "you_placed").jump(20).finish().records[0]
    consistent(r)
    assert r.completion == S.COMPLETE and not r.discontinuity and r.uncertain_seconds >= 20


def test_time_invariants_hold_across_timeout_and_stop_combinations():
    for ending in (None, "you_placed", "spectating"):
        for gap in (0, 3, 6, 60, 120):
            for black_samples in (0, 1, 4, 61):
                s = played_match()
                if ending:
                    s.show(6, ending)
                s.jump(gap).show(black_samples, black=True).finish()
                assert s.records, (ending, gap, black_samples)
                for r in s.records:
                    consistent(r)
                assert all(a.closed_t <= b.opened_t for a, b in zip(s.records, s.records[1:]))


def test_long_victory_banner_is_one_match():
    s = played_match().show(120, "victory_royale", health=HP).finish()
    assert len(s.records) == 1 and s.records[0].ended_by == S.VICTORY


def test_victory_celebration_without_banner_is_not_another_match():
    s = played_match().show(6, "victory_royale", health=HP).show(120, health=HP).finish()
    assert len(s.records) == 1, [(r.match_number, r.completion) for r in s.records]
    assert s.records[0].ended_by == S.VICTORY


def test_real_countdown_after_victory_can_open_a_new_match():
    s = played_match().show(6, "victory_royale", health=HP).show(60, health=HP)
    s.show(10, "waiting_for_players", health=HP).show(5, "bus_launching", health=HP).show(6).show(10, health=HP).finish()
    assert len(s.records) == 2, [(r.match_number, r.completion) for r in s.records]
    assert s.records[0].ended_by == S.VICTORY and s.records[1].observed_from_start


if __name__ == "__main__":
    import traceback
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}", flush=True)
        except Exception:
            failed += 1
            print(f"  FAIL  {name}", flush=True)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} audit regression checks passed; {failed} failed")
    raise SystemExit(bool(failed))
