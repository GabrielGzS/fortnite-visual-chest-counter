"""
Match state machine (v0.3.0, M2): every lifecycle situation has a deterministic test, and the recorded cue timelines give the expected story.

tests/fixtures/match/timelines.json.gz holds one sample per second of M1's scores for the labelled clips and two gameplay videos, made by
research/match_cues_eval.py --write-timelines. Chests come from the frozen M0 baselines. No video is decoded here.

Run:   python tests/test_match_state.py     (or pytest)
"""

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "src"))   # run without installing

import ast
import gzip
import json
from pathlib import Path

from fortnite_chest_counter import match_state as S

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TIMELINES = json.loads(gzip.open(HERE / "fixtures" / "match" / "timelines.json.gz").read())
HP = 180


class Script:
    """Feeds one observation per second. Each `show` is a stretch of video with the same things on screen."""

    def __init__(self, start=0.0):
        self.t = start
        self.machine = S.MatchStateMachine()
        self.events = []

    def show(self, seconds, *signals, health=0, black=False, frozen=False, chests=()):
        for i in range(seconds):
            self.events += self.machine.update(S.Observation(self.t, {s: 0.95 for s in signals}, health, black, frozen, tuple(chests) if i == 0 else ()))
            self.t += 1
        return self

    def jump(self, seconds):
        self.t += seconds
        return self

    def finish(self, reason=S.STOPPED):
        self.events += self.machine.finish(self.t, reason)
        return self

    @property
    def records(self):
        return [e for e in self.events if isinstance(e, S.MatchRecord)]

    @property
    def path(self):
        return [e.state for e in self.events if isinstance(e, S.Transition)]

    @property
    def state(self):
        return self.machine.state


def start_match(script):
    """Lobby, loading, the waiting island, the bus countdown, then the bus."""
    return script.show(5, "lobby_menu").show(8, "connecting").show(20, "waiting_for_players", health=HP).show(10, "bus_launching", health=HP).show(6)


def played_match(script=None):
    return start_match(script or Script()).show(60, health=HP)


def replay(name, chests=()):
    machine, events, waiting = S.MatchStateMachine(), [], sorted(chests)
    timeline = TIMELINES[name]
    for t, scores, health, black, frozen in timeline:
        ready = []
        while waiting and waiting[0][0] + 3 <= t:                  # a chest is only known a moment after it happened
            ready.append(waiting.pop(0)[1])
        events += machine.update(S.Observation(t, scores, health, bool(black), bool(frozen), tuple(ready)))
    events += machine.finish(timeline[-1][0] + 1)
    return events


def counted_chests(baseline):
    rows = json.loads((HERE / "baselines" / f"{baseline}_v0.3.0-base.json").read_text(encoding="utf-8"))
    return [(e["time"], S.chest_language(e["popup_template"])) for e in rows if e["certain_counted"] or e["approx_counted"]]


def story(events):
    return [(e.t, e.state) for e in events if isinstance(e, S.Transition) and e.reason != S.STOPPED]


def near(actual, expected, margin=2.0):
    assert len(actual) == len(expected) and all(a[1] == b[1] and abs(a[0] - b[0]) <= margin for a, b in zip(actual, expected)), (actual, expected)


# ---- normal matches

def test_a_normal_match_is_complete():
    s = played_match().show(10, "you_placed", health=40).show(5, "connecting").show(5, "lobby_menu").finish()
    assert s.path == [S.LOBBY, S.LOADING, S.PRE_GAME, S.IN_MATCH, S.ELIMINATED, S.LOADING, S.LOBBY, S.UNKNOWN]
    assert len(s.records) == 1
    r = s.records[0]
    assert r.completion == S.COMPLETE and r.english_confirmed and r.ended_by == S.PLACED and r.observed_from_start and not r.discontinuity
    assert r.start_confidence == S.HIGH and r.end_confidence == S.HIGH and r.match_number == 1
    assert r.ended_t is not None and r.complete_duration_seconds == r.ended_t - r.played_from_t


def test_a_win_with_its_start_seen_is_complete():
    s = played_match().show(6, "victory_royale", health=HP).show(5, "connecting").finish()
    r = s.records[0]
    assert r.completion == S.COMPLETE and r.ended_by == S.VICTORY and r.end_confidence == S.MEDIUM and r.complete_duration_seconds is not None


def test_joining_only_at_the_bus_countdown_is_less_sure():
    s = Script().show(5, "bus_launching", health=HP).show(6).show(30, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert s.records[0].start_confidence == S.MEDIUM and s.records[0].completion == S.COMPLETE


def test_the_countdown_ending_with_a_health_bar_still_starts_the_match():
    s = Script().show(5, "waiting_for_players", health=HP).show(14, health=HP)
    assert s.state == S.PRE_GAME
    s.show(3, health=HP)
    assert s.state == S.IN_MATCH and [e.reason for e in s.events if isinstance(e, S.Transition)][-1] == "countdown_timed_out"


def test_leaving_the_island_before_the_bus_is_not_a_match():
    s = Script().show(8, "waiting_for_players", health=HP).show(4, "lobby_menu").finish()
    assert s.records == [] and S.PRE_GAME in s.path and not [e for e in s.events if isinstance(e, S.MatchOpened)]


# ---- starting late

def test_starting_in_the_middle_of_a_match_is_partial():
    s = Script().show(30, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    r = s.records[0]
    assert r.completion == S.PARTIAL and not r.observed_from_start and r.start_confidence == S.LOW and r.ended_by == S.PLACED and r.complete_duration_seconds is None
    assert r.observed_seconds > 0 and r.active_seconds > 0, "observed time is kept even though the match is partial"


def test_a_recording_opened_halfway_behaves_the_same_on_its_own_time():
    a = Script().show(30, health=HP).show(6, "you_placed").show(4, "connecting").finish().records[0]
    b = Script(start=5000.0).show(30, health=HP).show(6, "you_placed").show(4, "connecting").finish().records[0]
    assert a.completion == b.completion and a.active_seconds == b.active_seconds and b.opened_t == a.opened_t + 5000.0


def test_loading_straight_into_gameplay_is_partial():
    s = Script().show(5, "connecting").show(12, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert s.records[0].completion == S.PARTIAL and not s.records[0].observed_from_start


def test_a_loading_screen_counts_as_english_evidence_for_the_match_after_it():
    s = Script().show(5, "connecting").show(12, health=HP).finish()
    assert s.records[0].english_confirmed and s.records[0].completion == S.PARTIAL


def test_a_counted_chest_shows_a_match_is_being_played():
    s = Script().show(2).show(1, chests=("en",))
    assert s.state == S.IN_MATCH


def test_a_chest_counted_just_after_a_menu_does_not_start_a_match():
    s = Script().show(5, "lobby_menu").show(1).show(1, chests=("en",))
    assert s.state == S.LOBBY and s.records == [] and s.machine.open_match_number is None


def test_starting_on_an_end_screen_invents_no_match():
    s = Script().show(8, "you_placed").show(4, "connecting").finish()
    assert s.records == [] and S.ELIMINATED in s.path


def test_gameplay_after_an_end_screen_with_no_match_is_a_new_late_record():
    s = Script().show(8, "you_placed")
    assert s.state == S.ELIMINATED and s.machine.open_match_number is None
    s.show(12, health=HP)
    assert s.path == [S.ELIMINATED, S.UNKNOWN, S.IN_MATCH] and s.machine.open_match_number == 1
    r = s.finish().records[0]
    assert r.completion == S.UNCONFIRMED and not r.observed_from_start, "the end screen belonged to a match that was never observed"


# ---- brief problems

def test_one_stray_sample_changes_nothing():
    s = Script()
    for signal in S.ALL_SIGNALS:
        s.show(1, signal).show(3)
    assert s.state == S.UNKNOWN and s.path == []


def test_two_of_three_samples_are_enough():
    s = Script().show(20, health=HP).show(1, "you_placed").show(1).show(1, "you_placed")
    assert s.state == S.ELIMINATED


def test_a_short_gap_in_samples_is_tolerated_but_not_forgotten():
    s = played_match().jump(3).show(10, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert s.records[0].completion == S.COMPLETE, "up to 5 s between samples is not a break"


def test_missing_video_breaks_the_match():
    s = played_match().jump(20).show(10, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    r = s.records[0]
    assert r.completion == S.PARTIAL and r.discontinuity and r.uncertain_seconds >= 20


def test_a_very_long_gap_closes_the_match_as_lost():
    s = played_match().jump(120).show(1, health=HP)
    assert s.records[0].ended_by == S.LOST and s.state != S.IN_MATCH


def test_no_evidence_for_a_minute_closes_the_match():
    s = played_match().show(61)
    assert s.records[0].ended_by == S.LOST and s.state == S.UNKNOWN and s.records[0].completion == S.PARTIAL


def test_a_black_picture_decides_nothing():
    s = played_match().show(2, "connecting", black=True).show(1, health=HP)
    assert s.state == S.IN_MATCH and s.records == []


def test_a_frozen_loading_screen_decides_nothing():
    s = Script().show(5, "connecting", frozen=True)
    assert s.state == S.UNKNOWN and s.path == []


def test_a_short_black_picture_does_not_break_a_match():
    s = played_match().show(2, black=True).show(10, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert s.records[0].completion == S.COMPLETE and s.records[0].uncertain_seconds == 2


def test_a_long_black_picture_may_hide_a_jump():
    s = played_match().show(5, black=True).show(10, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert s.records[0].completion == S.PARTIAL and s.records[0].discontinuity


def test_a_long_freeze_during_the_countdown_also_breaks_the_match():
    s = Script().show(8, "waiting_for_players", health=HP).show(5, frozen=True).show(4, "bus_launching", health=HP).show(6)
    s.show(30, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    r = s.records[0]
    assert r.completion == S.PARTIAL and r.discontinuity and not r.observed_from_start, "the real start may be hidden in the freeze"


def test_a_long_black_picture_is_not_counted_as_silence():
    s = played_match().show(30).show(50, black=True).show(1)
    assert s.state == S.IN_MATCH and s.records == []


def test_a_picture_gone_for_a_minute_closes_the_match_as_lost():
    s = played_match().show(61, frozen=True)
    r = s.records[0]
    assert r.ended_by == S.LOST and r.discontinuity and r.completion == S.PARTIAL and s.state == S.UNKNOWN
    assert r.observed_seconds + r.uncertain_seconds == r.closed_t - r.opened_t


def test_black_after_the_ending_leaves_the_match_complete():
    s = played_match().show(6, "you_placed").show(8, black=True).show(4, "connecting").finish()
    r = s.records[0]
    assert r.completion == S.COMPLETE and not r.discontinuity and r.uncertain_seconds == 8


def test_missing_video_after_the_ending_leaves_the_match_complete():
    s = played_match().show(6, "you_placed").jump(20).show(4, "connecting").finish()
    assert s.records[0].completion == S.COMPLETE and not s.records[0].discontinuity


def test_a_rewind_after_the_ending_leaves_the_match_complete():
    s = played_match().show(6, "you_placed")
    s.t = 20.0
    s.show(1, health=HP)
    assert s.records[0].completion == S.COMPLETE and s.records[0].ended_by == S.PLACED


def test_video_time_running_backwards_ends_the_match_honestly():
    s = played_match()
    s.t = 20.0
    s.show(1, health=HP)
    r = s.records[0]
    assert r.ended_by == S.DISCONTINUITY and r.completion == S.PARTIAL and r.discontinuity and s.state == S.UNKNOWN
    s.show(10, health=HP)
    assert s.state == S.IN_MATCH and s.machine.open_match_number == 2, "what follows is a new, late-joined record"
    s.finish()
    assert s.records[1].opened_t < r.closed_t, "the old clock must not hold back a match on the new one"


def test_silence_after_time_runs_backwards_is_still_noticed():
    s = played_match()
    s.t = 20.0
    s.show(10, health=HP).show(61)
    assert s.state == S.UNKNOWN and s.records[-1].ended_by == S.LOST


def test_a_repeated_timestamp_is_ignored():
    s = played_match()
    last = s.t - 1
    for _ in range(3):                                             # counted as new samples, these would confirm a loading screen
        assert s.machine.update(S.Observation(last, {"connecting": 1.0}, 0)) == []
    assert s.state == S.IN_MATCH and s.records == []


def test_gameplay_appearing_after_the_lobby_counts_as_joined_late():
    """What a rewound stream looks like: lobby, then gameplay with no loading screen."""
    s = Script().show(5, "lobby_menu").show(10, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert s.records[0].completion == S.PARTIAL and not s.records[0].observed_from_start


# ---- endings

def test_leaving_without_dying_is_partial():
    s = played_match().show(4, "connecting").finish()
    r = s.records[0]
    assert r.ended_by == S.LEFT_OR_UNKNOWN and r.completion == S.PARTIAL and r.ended_t is None and r.end_confidence == S.LOW


def test_the_lobby_appearing_also_closes_the_match():
    s = played_match().show(4, "lobby_menu").finish()
    assert s.records[0].ended_by == S.LEFT_OR_UNKNOWN


def test_spectating_after_death_keeps_one_ending_and_stops_active_time():
    s = played_match()
    active_before = s.t
    s.show(30, "you_placed", "spectating", health=60)
    assert s.state == S.ELIMINATED and s.records == [], "spectating does not finish the record"
    s.show(4, "connecting").finish()
    r = s.records[0]
    assert len(s.records) == 1 and r.spectating_seconds >= 30 and r.active_seconds <= active_before - r.played_from_t + 2 and r.ended_by == S.PLACED


def test_a_spectated_players_health_bar_is_not_a_respawn():
    s = played_match().show(40, "you_placed", health=HP)
    assert s.state == S.ELIMINATED


def test_you_placed_shown_for_a_long_time_is_one_ending():
    s = played_match().show(20, "you_placed", health=40)
    first = next(e.t for e in s.events if isinstance(e, S.Transition) and e.state == S.ELIMINATED)
    s.show(2).show(10, "you_placed", health=40).show(4, "connecting").finish()
    assert len(s.records) == 1 and sum(1 for e in s.events if isinstance(e, S.Transition) and e.state == S.ELIMINATED) == 1
    assert first - 2 <= s.records[0].ended_t <= first


def test_a_reboot_continues_the_same_match():
    s = played_match().show(10, "spectating")
    assert s.state == S.ELIMINATED and s.records == []
    s.show(12, health=HP)
    assert s.state == S.IN_MATCH and s.machine.open_match_number == 1
    s.show(6, "you_placed").show(4, "connecting").finish()
    r = s.records[0]
    assert len(s.records) == 1 and r.respawns == 1 and r.completion == S.COMPLETE


def test_coming_back_after_a_break_in_the_video_needs_the_full_ten_samples():
    s = played_match().show(6, "spectating").jump(20).show(9, health=HP)
    assert s.state == S.ELIMINATED
    assert s.show(1, health=HP).state == S.IN_MATCH


def test_coming_back_after_you_placed_withdraws_that_ending():
    s = played_match().show(6, "you_placed").show(12, health=HP)
    assert s.state == S.IN_MATCH and s.machine.open_match_number == 1
    s.finish()
    r = s.records[0]
    assert r.ended_by == S.STOPPED and r.ended_t is None and r.completion == S.PARTIAL


def test_a_later_ending_after_a_withdrawn_one_is_still_only_partial():
    s = played_match().show(6, "you_placed").show(12, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert s.records[0].completion == S.PARTIAL and s.records[0].ended_by == S.PLACED


def test_elimination_without_placement_is_not_a_complete_match():
    s = played_match().show(6, "eliminated_by").show(4, "connecting").finish()
    assert s.records[0].ended_by == S.LEFT_OR_UNKNOWN and s.records[0].completion == S.PARTIAL


def test_a_win_never_comes_back_as_the_same_match():
    s = played_match().show(6, "victory_royale", health=HP).show(30, health=HP)
    assert s.state == S.ELIMINATED and s.machine.open_match_number == 1


def test_long_gameplay_after_a_win_is_another_match_and_never_overlaps():
    s = played_match().show(6, "victory_royale", health=HP).show(60, health=HP)
    assert s.state == S.IN_MATCH and s.machine.open_match_number == 2
    s.finish()
    first, second = s.records
    assert first.ended_by == S.VICTORY and not second.observed_from_start and second.opened_t >= first.closed_t


def test_no_evidence_after_elimination_closes_it():
    s = played_match().show(6, "you_placed").show(61)
    assert s.records[0].ended_by == S.PLACED and s.state == S.UNKNOWN


# ---- identity

def test_back_to_back_matches_are_separate():
    s = played_match().show(6, "you_placed").show(5, "connecting").show(3, "lobby_menu")
    played_match(s).show(6, "you_placed").show(5, "connecting").finish()
    assert [r.match_number for r in s.records] == [1, 2] and all(r.completion == S.COMPLETE for r in s.records)
    assert s.records[0].closed_t <= s.records[1].opened_t


def test_going_straight_into_the_next_countdown_closes_the_last_match():
    s = played_match().show(6, "you_placed").show(10, "waiting_for_players", health=HP).show(6).show(20, health=HP).show(6, "you_placed").show(4, "connecting").finish()
    assert [r.match_number for r in s.records] == [1, 2] and s.records[0].ended_by == S.PLACED and all(r.completion == S.COMPLETE for r in s.records)


def test_transitions_name_the_match():
    s = played_match().show(6, "you_placed")
    assert next(e for e in s.events if isinstance(e, S.Transition) and e.state == S.ELIMINATED).match_number == 1


def test_stopping_during_a_match_is_partial():
    s = played_match().finish()
    assert s.records[0].ended_by == S.STOPPED and s.records[0].completion == S.PARTIAL and s.state == S.UNKNOWN


def test_stopping_after_you_placed_keeps_the_ending():
    s = played_match().show(6, "you_placed").finish()
    assert s.records[0].ended_by == S.PLACED and s.records[0].completion == S.COMPLETE


def test_stopping_with_nothing_open_changes_nothing():
    s = Script().finish()
    assert s.events == []


def test_a_restart_begins_a_new_partial_record():
    first = played_match().finish()
    second = Script(start=first.t + 30).show(10, health=HP).finish()
    assert second.records[0].match_number == 1 and not second.records[0].observed_from_start and second.records[0].completion != S.COMPLETE


def test_changing_source_closes_like_stopping():
    s = played_match().finish("source_changed")
    assert s.records[0].ended_by == "source_changed" and s.records[0].completion == S.PARTIAL and s.state == S.UNKNOWN


def test_modes_without_any_cues_record_nothing_confirmed():
    s = Script().show(300, health=HP).finish()
    assert [r.completion for r in s.records] == [S.UNCONFIRMED] and not s.records[0].english_confirmed


# ---- the English-first rule

def test_a_health_bar_alone_never_confirms_a_match():
    assert Script().show(30, health=HP).finish().records[0].completion == S.UNCONFIRMED


def test_portuguese_chests_do_not_confirm_a_match():
    s = Script().show(30, health=HP, chests=("pt", "pt")).finish()
    assert s.records[0].completion == S.UNCONFIRMED and s.records[0].portuguese_chests == 2


def test_a_chest_of_unknown_language_does_not_confirm_a_match():
    assert Script().show(30, health=HP, chests=("unknown",)).finish().records[0].completion == S.UNCONFIRMED


def test_victory_royale_alone_does_not_establish_the_language():
    r = Script().show(30, health=HP).show(6, "victory_royale", health=HP).finish().records[0]
    assert r.completion == S.UNCONFIRMED and not r.english_confirmed and r.ended_by == S.VICTORY


def test_an_english_chest_confirms_a_match():
    r = Script().show(30, health=HP, chests=("en",)).finish().records[0]
    assert r.completion == S.PARTIAL and r.english_confirmed and r.english_chests == 1


def test_english_end_screens_confirm_a_match():
    for signal in ("you_placed", "spectating", "eliminated_by"):
        assert Script().show(30, health=HP).show(6, signal).finish().records[0].english_confirmed, signal


def test_english_text_elsewhere_does_not_confirm_a_later_match():
    r = Script().show(10, "lobby_menu").show(30, health=HP).finish().records[0]
    assert r.completion == S.UNCONFIRMED


def test_loading_artwork_is_not_mistaken_for_a_health_bar():
    s = Script().show(20, "connecting", health=HP)
    assert s.state == S.LOADING and s.records == []
    s.show(3)
    assert s.state == S.LOADING and s.machine.open_match_number is None, "the artwork must not be remembered as play once the text has gone"


# ---- what the later stages receive

def test_the_time_values_add_up():
    s = played_match().show(4, black=True).show(10, health=HP).show(20, "you_placed", health=40).show(4, "connecting").finish()
    r = s.records[0]
    assert r.observed_seconds + r.uncertain_seconds == r.closed_t - r.opened_t
    assert r.active_seconds + r.spectating_seconds <= r.observed_seconds and r.uncertain_seconds == 4 and r.spectating_seconds > 0


def test_the_time_values_still_add_up_when_stopped_mid_match():
    r = played_match().finish().records[0]
    assert r.observed_seconds + r.uncertain_seconds == r.closed_t - r.opened_t


def test_the_ending_is_when_the_text_first_appeared():
    s = played_match()
    first_seen = s.t
    r = s.show(6, "you_placed").show(4, "connecting").finish().records[0]
    assert r.ended_t == first_seen


def test_records_hold_plain_values_with_reasons_and_evidence():
    r = played_match().show(6, "you_placed").show(4, "connecting").finish().records[0]
    data = json.loads(json.dumps(r.to_dict()))
    expected = {"match_number", "completion", "english_confirmed", "ended_by", "observed_from_start", "opened_t", "played_from_t", "ended_t", "closed_t", "observed_seconds", "active_seconds",
                "spectating_seconds", "uncertain_seconds", "complete_duration_seconds", "start_confidence", "end_confidence", "discontinuity", "respawns", "english_chests", "portuguese_chests", "reasons", "evidence"}
    assert set(data) == expected
    assert data["reasons"] and any(item[1] == "you_placed" for item in data["evidence"])


def test_the_same_input_always_gives_the_same_result():
    make = lambda: played_match().show(6, "you_placed").show(4, "connecting").finish().events
    assert make() == make()


def test_chest_languages_are_read_from_the_template_name():
    assert [S.chest_language(v) for v in ("en:CHEST", "pt:BAÚ", None, "", "xx:THING")] == ["en", "pt", "unknown", "unknown", "unknown"]


def test_the_rules_agree_with_the_cue_module():
    """Read from its source, so that these tests need no image libraries."""
    tree = ast.parse((ROOT / "src/fortnite_chest_counter/match_cues.py").read_text(encoding="utf-8"))
    values = {node.targets[0].id: node.value for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    assert {key.value for key in values["SIGNALS"].keys} == S.ALL_SIGNALS
    assert S.ENGLISH_SIGNALS == S.ALL_SIGNALS - ast.literal_eval(values["NOT_ENGLISH_SPECIFIC"].args[0])
    assert ast.literal_eval(values["SCORE_THRESHOLD"]) == S.SCORE_THRESHOLD and ast.literal_eval(values["HEALTH_BAR_MIN_PIXELS"]) == S.HEALTH_BAR_MIN_PIXELS


def test_this_module_touches_no_images_files_or_clocks():
    tree = ast.parse((ROOT / "src/fortnite_chest_counter/match_state.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported == {"collections", "dataclasses"}, imported
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {"open", "time", "datetime", "random", "print", "Path"}, names


def test_counting_does_not_use_this_module_yet():
    for file in (ROOT / "src/fortnite_chest_counter").rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            names = [alias.name for alias in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
            assert "match_state" not in " ".join(names + [getattr(node, "module", None) or ""]), file.name


# ---- the recorded footage

def test_clip_1_tells_the_expected_story():
    events = replay("clip1")
    near(story(events), [(4, S.IN_MATCH), (9, S.ELIMINATED), (19, S.LOADING), (30, S.LOBBY)])
    records = [e for e in events if isinstance(e, S.MatchRecord)]
    assert len(records) == 1 and records[0].completion == S.PARTIAL and records[0].ended_by == S.PLACED and records[0].english_confirmed and abs(records[0].ended_t - 8) <= 1


def test_clip_3_tells_the_expected_story():
    events = replay("clip3")
    near(story(events), [(1, S.LOBBY), (18, S.LOADING), (24, S.PRE_GAME), (48, S.IN_MATCH)])
    r = next(e for e in events if isinstance(e, S.MatchRecord))
    assert r.observed_from_start and r.start_confidence == S.HIGH and r.ended_by == S.STOPPED and r.completion == S.PARTIAL and r.uncertain_seconds == 2, r


def test_clip_2_recovers_from_the_stream_being_rewound():
    events = replay("clip2")
    near(story(events), [(1, S.LOBBY), (19, S.IN_MATCH), (40, S.ELIMINATED), (49, S.LOADING), (61, S.LOBBY)])
    records = [e for e in events if isinstance(e, S.MatchRecord)]
    assert len(records) == 1 and records[0].completion == S.PARTIAL and not records[0].observed_from_start, "a rewound match can never count as complete"


def test_english_gameplay_has_only_its_two_real_endings():
    events = replay("new", counted_chests("en"))
    records = [e for e in events if isinstance(e, S.MatchRecord)]
    assert [r.ended_by for r in records] == [S.VICTORY, S.VICTORY]
    assert abs(records[0].ended_t - 258) <= 2 and abs(records[1].ended_t - 499) <= 2
    assert sum(1 for e in events if isinstance(e, S.Transition) and e.state == S.ELIMINATED) == 2
    assert records[0].english_confirmed and records[0].english_chests == 6
    assert records[1].completion == S.UNCONFIRMED, "the second win has no English evidence of its own in this edited video"
    assert records[0].closed_t <= records[1].opened_t and not any(r.completion == S.COMPLETE for r in records)


def test_portuguese_footage_confirms_no_english_match():
    events = replay("ps5", counted_chests("ps5"))
    records = [e for e in events if isinstance(e, S.MatchRecord)]
    assert records and all(not r.english_confirmed and r.completion == S.UNCONFIRMED for r in records)
    assert sum(r.portuguese_chests for r in records) == 11 and sum(r.english_chests for r in records) == 0


def test_portuguese_gameplay_has_no_false_ending():
    events = replay("ps5", counted_chests("ps5"))
    ends = [e for e in events if isinstance(e, S.Transition) and e.state == S.ELIMINATED]
    assert len(ends) == 1 and ends[0].t >= 1019, "only the real win near the end"


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
    print(f"{len(tests) - failed}/{len(tests)} match state checks passed")
    sys.exit(1 if failed else 0)
