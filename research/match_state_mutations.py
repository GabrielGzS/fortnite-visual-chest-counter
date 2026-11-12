"""Small, reproducible sabotage checks for what a match record claims: Complete by observation, and the waiting island.

Mutates a private in-memory copy of match_state, never a repository file. Each mutation must be rejected by a named test in tests/test_match_state.py.
Run after that file passes.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_match_state as T

SOURCE = (ROOT / "src/fortnite_chest_counter/match_state.py").read_text(encoding="utf-8")
COMPLETE_RULE = "elif match.observed_from_start and (finished or play_ended) and not match.discontinuity and not match.ambiguous_recovery:"
ISLAND_RULE = "if (match.after_loading or match.start_guessed) and not match.chest_counted and match.ended_by is None:"

MUTATIONS = [
    (COMPLETE_RULE, COMPLETE_RULE.replace("(finished or play_ended)", "finished"), "test_leaving_after_a_seen_start_is_complete_and_the_outcome_stays_unknown"),
    (COMPLETE_RULE, COMPLETE_RULE.replace("(finished or play_ended)", "True"), "test_counting_stopping_is_not_an_ending"),
    (COMPLETE_RULE, COMPLETE_RULE.replace("match.observed_from_start and ", ""), "test_leaving_cannot_complete_a_match_whose_start_was_not_seen"),
    (COMPLETE_RULE, COMPLETE_RULE.replace(" and not match.discontinuity", ""), "test_missing_video_before_leaving_stays_partial"),
    ('self._close(t, self._match.ended_by or LEFT_OR_UNKNOWN, [reason], events, play_ended=True)', 'self._close(t, self._match.ended_by or LEFT_OR_UNKNOWN, [reason], events)', "test_returning_to_the_lobby_is_complete"),
    ('self._close(t, match.ended_by or LEFT_OR_UNKNOWN, ["next match countdown seen"], events)', 'self._close(t, match.ended_by or LEFT_OR_UNKNOWN, ["next match countdown seen"], events, play_ended=True)', "test_a_countdown_without_leaving_does_not_complete_a_match"),
    ("duration = round((match.ended_t if finished else t) - match.played_from_t, 3) if completion == COMPLETE else None", "duration = round((match.ended_t if finished else match.opened_t) - match.played_from_t, 3) if completion == COMPLETE else None", "test_leaving_after_a_seen_start_is_complete_and_the_outcome_stays_unknown"),
    ("match.ended_t if finished else None, t, round(match.observed, 3)", "match.ended_t if finished else t, t, round(match.observed, 3)", "test_leaving_after_a_seen_start_is_complete_and_the_outcome_stays_unknown"),
    (ISLAND_RULE, ISLAND_RULE.replace("(match.after_loading or match.start_guessed) and ", ""), "test_a_late_join_without_a_loading_screen_is_not_called_the_island"),
    (ISLAND_RULE, ISLAND_RULE.replace(" and not match.chest_counted", ""), "test_a_counted_chest_means_it_was_not_the_island"),
    ("                    match.english.clear()              # the countdown proves play had not begun, so what confirmed it proves nothing\n", "", "test_the_countdown_retroactively_marks_the_waiting_island"),
    ("                    match.reasons.append(WAITING_ISLAND)\n", "", "test_the_countdown_retroactively_marks_the_waiting_island"),
    ("        match.after_loading = from_loading\n", "", "test_the_countdown_retroactively_marks_the_waiting_island"),
    ("            match.chest_counted = True\n", "", "test_a_counted_chest_means_it_was_not_the_island"),
    # is the game on screen at all?
    ("if lost_for >= GAME_OUT_OF_VIEW and not self._out_of_view:", "if lost_for >= 0 and not self._out_of_view:", "test_a_short_loss_of_the_hud_changes_nothing"),
    ("if lost_for >= GAME_OUT_OF_VIEW and not self._out_of_view:", "if False:", "test_time_with_the_game_out_of_view_is_not_play"),
    ("            moved = match.active - self._active_at_unseen", "            moved = 0", "test_time_with_the_game_out_of_view_is_not_play"),
    ("            self._unseen_since, self._active_at_unseen = observation.t, match.active", "            self._unseen_since, self._active_at_unseen = observation.t, 0.0", "test_no_moment_is_counted_twice"),
    ("            match.observed -= moved\n", "", "test_time_with_the_game_out_of_view_is_not_play"),
    ("        if self._out_of_view:\n            match.uncertain += elapsed\n            return\n", "", "test_time_with_the_game_out_of_view_is_not_play"),
    ("observation.hud_in_view is False and observation.health_bar_pixels", "not observation.hud_in_view and observation.health_bar_pixels", "test_a_recording_without_hud_evidence_is_never_called_out_of_view"),
    ("observation.hud_in_view is False and observation.health_bar_pixels < HEALTH_BAR_MIN_PIXELS\n", "observation.hud_in_view is False\n", "test_the_health_bar_alone_is_still_the_game"),
    ("                  and not observation.chests and not any(hit.values()))", "                  and not any(hit.values()))", "test_text_or_a_chest_is_still_the_game"),
    ("        if hud or observation.hud_in_view or observation.chests or any(hit.values()):", "        if hud or observation.chests or any(hit.values()):", "test_the_hud_keeps_a_match_alive_without_a_health_bar"),
    ("        if self._match is not None:\n            self._match.uncertain += elapsed\n        if self._countdown", "        self._unseen_since, self._out_of_view = None, False\n        if self._match is not None:\n            self._match.uncertain += elapsed\n        if self._countdown", "test_a_still_page_inside_a_switch_does_not_restart_it"),
    ("            moved = match.active - self._active_at_unseen", "            moved = min(lost_for, match.active)", "test_no_moment_is_counted_twice"),
    ("        self._unseen_since, self._out_of_view = None, False\n        self._loading_english_continuous = False\n", "        self._loading_english_continuous = False\n", "test_a_long_black_picture_still_restarts_the_count"),
    ("            match.reasons.append(OUT_OF_VIEW_REASON)\n", "            match.discontinuity = True\n            match.reasons.append(OUT_OF_VIEW_REASON)\n", "test_the_game_out_of_view_is_not_an_ending_and_does_not_decide_quality"),
    # M9H
    ("hud and (green is None or green >= HEALTH_BAR_MIN_PIXELS)", "hud", "test_party_tiles_after_leaving_a_match_do_not_start_one"),
    ("hud and (green is None or green >= HEALTH_BAR_MIN_PIXELS)", "hud and (green is not None and green >= HEALTH_BAR_MIN_PIXELS)", "test_starting_in_the_middle_of_a_match_is_partial"),
    ("        if chest and observation.first_chest_t is not None:", "        if False:", "test_the_chest_that_shows_a_match_is_being_played_belongs_to_it"),
    ("first = max(min(first, observation.first_chest_t), self._last_screen_text_t)", "first = min(first, observation.first_chest_t)", "test_a_chest_never_dates_a_match_back_into_a_menu"),
    ("        if screen_text:\n            self._last_screen_text_t = t\n", "", "test_a_chest_never_dates_a_match_back_into_a_menu"),
    (ISLAND_RULE, ISLAND_RULE.replace(" or match.start_guessed", ""), "test_an_island_guessed_to_be_a_match_is_corrected_by_the_next_countdown"),
    ("        match.start_guessed = not (gone >= COUNTDOWN_GONE_ON_BUS and no_hud_lately)", "        match.start_guessed = True", "test_a_seen_bus_departure_is_not_second_guessed"),
    ("        match.start_guessed = not (gone >= COUNTDOWN_GONE_ON_BUS and no_hud_lately)", "        match.start_guessed = False", "test_an_island_guessed_to_be_a_match_is_corrected_by_the_next_countdown"),
]


def mutated(old, new):
    assert SOURCE.count(old) == 1, old
    module = types.ModuleType("match_state_mutated")
    sys.modules[module.__name__] = module                      # dataclasses look their module up here
    exec(compile(SOURCE.replace(old, new), "match_state_mutated", "exec"), module.__dict__)
    return module


def main():
    real, survivors = T.S, 0
    for old, new, test in MUTATIONS:
        T.S = mutated(old, new)
        try:
            getattr(T, test)()
        except Exception:
            print(f"  caught by {test}")
        else:
            survivors += 1
            print(f"  SURVIVED  {test}: {old[:70]!r}")
        finally:
            T.S = real
    print(f"{len(MUTATIONS) - survivors}/{len(MUTATIONS)} mutations caught")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
