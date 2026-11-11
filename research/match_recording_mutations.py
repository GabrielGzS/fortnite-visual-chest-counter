"""Small, reproducible sabotage checks for M6's recording guarantees.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in
tests/test_match_recording.py. Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_match_recording as R
import test_match_tracker as T


MUTATIONS = [
    # settings
    ("settings", "\"mode\": \"off\",                          # off | shadow (recognise", "\"mode\": \"on\",                           # off | shadow (recognise", "test_recording_is_off_by_default_and_the_interval_is_a_minute"),
    ("settings", "\"heartbeat_seconds\": 60,", "\"heartbeat_seconds\": 300,", "test_recording_is_off_by_default_and_the_interval_is_a_minute"),
    ("settings", "MATCH_HEARTBEATS = (30, 60, 300, 600)", "MATCH_HEARTBEATS = (1, 30, 60, 300, 600)", "test_anything_else_falls_back_to_a_minute"),
    ("settings", "MATCH_HEARTBEATS = (30, 60, 300, 600)", "MATCH_HEARTBEATS = (30, 60, 300)", "test_every_offered_interval_is_accepted"),
    ("settings", "type(value) is int and value in MATCH_HEARTBEATS", "value in MATCH_HEARTBEATS", "test_anything_else_falls_back_to_a_minute"),
    # the live wiring
    ("C", "    if cfg[\"match\"][\"mode\"] != \"on\":\n        return None\n", "", "test_only_on_keeps_a_history"),
    ("C", "    if not session.persist:\n        CONSOLE.warn(\"match history needs", "    if False:\n        CONSOLE.warn(\"match history needs", "test_nothing_is_kept_when_saving_is_turned_off"),
    ("C", "if self.history is not None and (certain_inc or approx_inc):", "if False:", "test_history_chests_equal_the_runs_increase_in_the_totals"),
    ("C", "            st[\"last_processed_time\"] = now_t\n            self.save()\n", "            st[\"last_processed_time\"] = now_t\n            if self.history is not None and (certain_inc or approx_inc):\n                self.history.chest(ev, st[\"certain\"], st[\"approximate\"])\n            self.save()\n", "test_the_totals_are_saved_before_history"),
    ("C", "                self.history.chest_type(event_id, u[\"time\"], new)\n", "                pass\n", "test_a_better_chest_type_reaches_history"),
    ("C", "            self.history.counter_changed(\"external\", self.state[\"certain\"], self.state[\"approximate\"])\n", "            pass\n", "test_a_reset_that_leaves_the_counts_unchanged_still_starts_a_new_epoch"),
    ("C", "            history.end_run(last_t, stop_reason, stats[\"frames_processed\"]", "            0 and history.end_run(last_t, stop_reason, stats[\"frames_processed\"]", "test_on_records_the_whole_run"),
    ("C", "        history.end_run(last_t, \"stream ended\", source.frames_processed", "        0 and history.end_run(last_t, \"stream ended\", source.frames_processed", "test_simulate_runs_end_cleanly"),
    ("C", "    return state.parent / \"history\" / state.stem", "    return state.parent / \"history\" / \"shared\"", "test_two_explicit_state_files_stay_apart"),
    ("C", "        return profiles.history_folder(profile[\"state_base\"], profile[\"id\"])", "        return profiles.history_folder(profile[\"state_base\"], \"default\")", "test_each_profile_records_into_its_own_history"),
    ("C", "    session.history = history\n    return history", "    return history", "test_history_chests_equal_the_runs_increase_in_the_totals"),
    ("C", "    tracker = _open_tracker(cfg, session, history, source)\n    last_t = None", "    tracker = _open_tracker(cfg, session, None, source)\n    last_t = None", "test_on_records_the_whole_run"),
    ("C", "    history = _open_history(cfg, session, kind)\n", "    history = _open_history(cfg, session, kind); session.state[\"certain\"] += 1\n", "test_live_counts_the_same_in_every_mode"),
    ("C", "        if history is not None:\n            history.end_run(last_t, stop_reason, stats[\"frames_processed\"]", "        if history is not None:\n            stats[\"match_recorded\"] = True\n            history.end_run(last_t, stop_reason, stats[\"frames_processed\"]", "test_the_desktop_app_sees_no_difference"),
    # the tracker's checkpoints
    ("MT", "if boundary or last is None or t < last or t - last >= self._beat_every - SAMPLE_TOLERANCE:", "if last is None or t < last or t - last >= self._beat_every - SAMPLE_TOLERANCE:", "test_checkpoints_are_written_at_match_boundaries"),
    ("MT", "t - last >= self._beat_every - SAMPLE_TOLERANCE:", "t - last >= 60 - SAMPLE_TOLERANCE:", "test_checkpoints_follow_the_interval"),
    ("MT", "self._history.heartbeat(t, processed, dropped, self._machine.snapshot())", "self._history.heartbeat(t, processed, dropped, None)", "test_every_interval_recovers_without_inventing_time"),
    ("MT", "                self._checkpoint(self._last_seen_t, True)\n", "", "test_stopping_writes_a_final_checkpoint"),
    ("MT", "                    self._history.match_closed(record)\n", "                    pass\n", "test_stopping_mid_match_is_partial_ending_as_stopped"),
    ("MT", "                    self._history.transition(asdict(event))\n", "                    pass\n", "test_a_chest_while_spectating_is_flagged_and_not_credited"),
    ("MT", "                    self._history.match_opened(asdict(event))\n", "                    pass\n", "test_checkpoints_are_written_at_match_boundaries"),
    ("MT", "SAMPLE_SECONDS = 1.0", "SAMPLE_SECONDS = 2.0", "test_sampling_stays_at_one_per_second_for_every_interval"),
    # attribution and the state machine's snapshot
    ("H", "spectating = bool(moments) and t >= min(moments)", "spectating = False", "test_a_chest_while_spectating_is_flagged_and_not_credited"),
    ("H", "moments = [m for m in (out_at.get((chest[\"run_id\"], match[\"match_number\"])), match.get(\"ended_t\")) if m is not None]", "moments = [m for m in (out_at.get((chest[\"run_id\"], match[\"match_number\"])),) if m is not None and False]", "test_a_chest_after_the_ending_is_not_credited"),
    ("H", "\"credited\": match[\"played_from_t\"] <= t and not spectating and not match[\"not_a_match\"]", "\"credited\": not spectating and not match[\"not_a_match\"]", "test_a_chest_on_the_pre_game_island_is_not_credited"),
    ("H", "\"credited\": match[\"played_from_t\"] <= t and not spectating and not match[\"not_a_match\"]", "\"credited\": match[\"played_from_t\"] <= t and not spectating", "test_a_chest_in_a_not_a_match_is_not_credited"),
    ("H", "by_run.get(chest[\"run_id\"], ())", "history.matches", "test_attribution_stays_within_a_run"),
    ("H", "if m[\"opened_t\"] <= t < m[\"closed_t\"]), None)", "), None)", "test_a_chest_outside_every_match_belongs_to_none"),
    ("H", "key = event_id, round(t, 3)", "key = event_id, t + 1", "test_a_better_chest_type_reaches_history"),
    ("S", "\"active_seconds\": round(match.active, 3),", "\"active_seconds\": round(match.observed, 3),", "test_a_snapshot_reports_the_open_match_and_nothing_otherwise"),
    ("S", "\"uncertain_seconds\": round(match.uncertain, 3),", "\"uncertain_seconds\": 0.0,", "test_a_snapshot_reports_the_open_match_and_nothing_otherwise"),
    ("S", "        match = self._match\n        if match is None:\n            return None\n        return {\"match_number\"", "        match = self._match\n        self._hud.clear()\n        if match is None:\n            return None\n        return {\"match_number\"", "test_taking_a_snapshot_changes_no_decision"),
]


def main():
    caught = 0
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = getattr(R, name)
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__ = original.__file__
        sys.modules[mutant.__name__] = mutant                  # dataclasses need the module to be importable by name
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        patches = [patch.object(R, name, mutant)]
        if hasattr(T, name):                                   # the whole-loop helpers live in test_match_tracker
            patches.append(patch.object(T, name, mutant))
        try:
            with patches[0], (patches[1] if len(patches) > 1 else patch.object(R, "HP", R.HP)):
                getattr(R, test_name)()
        except (AssertionError, KeyboardInterrupt, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} recording mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
