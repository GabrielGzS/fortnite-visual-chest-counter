"""Small, reproducible sabotage checks for M5's storage guarantees.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in
tests/test_match_history.py. Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_match_history as T


MUTATIONS = [
    # identity
    ("H", "if self._seen.get(key, -1) >= self._restart_epoch:", "if False:", "test_the_same_event_given_twice_is_recorded_once"),
    ("H", "if number <= self._last_event:", "if False:", "test_a_real_reset_during_a_run_keeps_both_chests"),
    ("H", "self._restart_epoch, self._last_event = self._epoch, 0", "self._last_event = 0", "test_an_announced_reset_separates_even_identical_ids_and_times"),
    ("H", "key = row[\"run_id\"], row[\"counter_epoch\"], row[\"event_id\"]", "key = row[\"run_id\"], row[\"event_id\"]", "test_a_real_reset_during_a_run_keeps_both_chests"),
    ("H", "key = row[\"run_id\"], row[\"counter_epoch\"], row[\"event_id\"]", "key = row[\"counter_epoch\"], row[\"event_id\"]", "test_event_ids_may_repeat_in_another_run"),
    ("H", "key = row[\"run_id\"], row[\"counter_epoch\"], row[\"event_id\"]", "key = row[\"id\"]", "test_the_same_chest_under_a_new_row_id_counts_once"),
    ("H", "elif row[\"id\"] not in seen:", "else:", "test_a_repeated_row_of_any_kind_counts_once"),
    ("H", "epoch = self._seen.get((event_id, round(t, 3)))", "epoch = self._epoch", "test_a_type_change_reaches_the_right_chest_after_a_reset"),
    ("H", "if epoch is not None:", "if True:", "test_a_type_change_for_an_unknown_chest_writes_nothing"),
    ("H", "\"id\": f\"{self.run_id}:{self._n}\", \"run_id\": self.run_id, \"at\": self._now(), **fields})\n        self._flush()", "\"id\": f\"{self.run_id}:{self._n}\", \"run_id\": self.run_id, \"at\": \"later\", **fields})\n        self._flush()", "test_a_retried_row_keeps_its_original_wall_clock"),
    # what is stored
    ("H", "if not (ev.get(\"certain_counted\") or ev.get(\"approx_counted\")):", "if False:", "test_uncounted_events_are_not_chests"),
    ("H", "approx_counted=bool(ev.get(\"approx_counted\"))", "approx_counted=bool(ev.get(\"certain_counted\"))", "test_a_chest_keeps_its_evidence"),
    ("H", "configured_analysis_fps=configured_analysis_fps", "fps=configured_analysis_fps", "test_a_run_records_its_settings_and_what_was_really_processed"),
    ("H", "\"end_confidence\", \"discontinuity\", \"english_chests\"", "\"end_confidence\", \"discontinuity\", \"respawns\", \"english_chests\"", "test_a_real_match_record_round_trips_without_respawns"),
    ("H", "row[\"evidence\"] = sorted(row[\"evidence\"], key=lambda item: (item[0], item[1]))", "pass", "test_evidence_is_stored_in_a_stable_order"),
    ("H", "allow_nan=False", "allow_nan=True", "test_an_impossible_number_is_never_written"),
    ("H", "chests[key][\"chest_type\"] = row[\"chest_type\"]", "pass", "test_a_later_type_change_wins_without_rewriting_the_chest"),
    # writing
    ("H", "open(path, \"a+b\")", "open(path, \"w+b\")", "test_a_session_only_ever_appends"),
    ("H", "if stream.read(1) != b\"\\n\":", "if False:", "test_a_cut_line_does_not_swallow_the_next_row"),
    ("H", "        os.fsync(stream.fileno())\n", "", "test_each_row_reaches_the_disk_before_returning"),
    ("H", "                self._warn_once(str(error))\n                return\n", "                self._warn_once(str(error))\n                self._waiting.clear()\n                return\n", "test_a_failed_write_is_retried_and_nothing_is_lost"),
    ("H", "        if self._warned:\n            return\n", "", "test_a_failed_write_is_retried_and_nothing_is_lost"),
    ("H", "            self._lost[\"rows\"] += 1\n", "", "test_rows_really_lost_become_a_gap_row_at_the_next_successful_write"),
    ("H", "self._lost[\"certain\"] += int(fields[\"certain_counted\"])", "pass", "test_rows_really_lost_become_a_gap_row_at_the_next_successful_write"),
    ("H", "        except Exception as error:\n            self._warn_once(f\"{type(error).__name__}: {error}\")", "        except ZeroDivisionError as error:\n            self._warn_once(f\"{type(error).__name__}: {error}\")", "test_every_writer_call_contains_bad_input"),
    ("H", "        except Exception as error:\n            self._warn_once(f\"{type(error).__name__}: {error}\")", "        except BaseException as error:\n            self._warn_once(f\"{type(error).__name__}: {error}\")", "test_the_user_stopping_is_not_swallowed"),
    ("H", "        try:\n            self._warn(f\"chest and match history could not be saved ({detail}); counting is not affected\")\n        except Exception:\n            pass", "        self._warn(f\"chest and match history could not be saved ({detail}); counting is not affected\")", "test_a_failing_warning_is_contained"),
    ("H", "        if self._ended:\n            return None\n", "", "test_nothing_is_written_after_the_run_ends"),
    # recovery
    ("H", "            if run[\"end\"] is not None:\n                continue\n", "", "test_a_finished_run_is_left_alone_when_another_one_crashed"),
    ("H", "\"id\": f\"{self.run_id}:{self._n}\", \"run_id\": self.run_id, \"at\": self._now(), **fields})\n        self._flush()", "\"id\": f\"{fields.get('run_id', self.run_id)}:{self._n}\", \"run_id\": self.run_id, \"at\": self._now(), **fields})\n        self._flush()", "test_recovery_rows_cannot_collide_with_the_crashed_runs_rows"),
    ("H", "return f\"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}\"", "return f\"{datetime.now():%Y%m%dT%H%M%S}\"", "test_run_ids_do_not_repeat_within_the_same_second"),
    ("H", "self.folder, self.run_id = Path(folder), run_id or new_run_id()", "self.folder, self.run_id = Path(folder), run_id or \"same-every-time\"", "test_a_restarted_session_cannot_reuse_an_identity"),
    ("H", "if self._seen.get(key, -1) >= self._restart_epoch:", "if self._seen.get(key, -1) > self._restart_epoch:", "test_repeated_delivery_is_still_ignored_after_a_reset"),
    ("H", "        if self._opened is not None:                   # the tracker stopped early, so nothing closed this match\n            self._close_interrupted(self.run_id, self._opened, self._beat, False)\n            self._opened = None\n", "", "test_a_run_never_ends_with_a_match_left_open"),
    ("H", "if run_id == started[-1] else (0, 0)", "", "test_only_the_newest_unfinished_run_is_compared_with_the_totals"),
    ("H", "started = [run_id for run_id, run in history.runs.items() if run[\"start\"] is not None]\n        for run_id in started:", "started = list(history.runs)\n        for run_id in [r for r in started if history.runs[r][\"start\"] is not None]:", "test_a_run_with_no_start_row_cannot_hide_the_newest_run"),
    ("H", "lost = any(value > 0 for value in missing)", "lost = any(missing)", "test_totals_lowered_after_a_crash_are_recorded_but_lose_no_chests"),
    ("H", " and not any(g[\"run_id\"] == run_id and g[\"reason\"] in (INTERRUPTED, TOTALS_LOWERED) for g in history.gaps)", "", "test_a_recovery_cut_short_is_finished_without_duplicates"),
    ("H", "completion=\"partial\" if confirmed else \"unconfirmed\"", "completion=\"complete\"", "test_an_interrupted_match_is_never_complete"),
    ("H", "completion=\"partial\" if confirmed else \"unconfirmed\"", "completion=\"partial\"", "test_an_unconfirmed_match_stays_unconfirmed"),
    ("H", "observed = min(snapshot[\"observed_seconds\"], span) if snapshot else 0.0", "observed = min(snapshot[\"observed_seconds\"], span) if snapshot else span", "test_a_heartbeat_without_this_match_claims_no_time_either"),
    ("H", "observed = min(snapshot[\"observed_seconds\"], span) if snapshot else 0.0", "observed = snapshot[\"observed_seconds\"] if snapshot else 0.0", "test_impossible_heartbeat_totals_cannot_break_the_time_rules"),
    ("H", "active = min(snapshot[\"active_seconds\"], observed) if snapshot else 0.0", "active = observed", "test_an_open_match_closes_as_interrupted_at_the_last_heartbeat"),
    ("H", "beat[\"match\"][\"match_number\"] == number", "True", "test_a_heartbeat_from_an_earlier_match_is_not_used"),
    ("H", "if order > run[\"_order\"]:", "if True:", "test_a_reset_as_the_last_thing_before_a_crash_is_not_a_gap"),
    ("H", "    @_contained\n    def _recover(self, certain, approximate):", "    def _recover(self, certain, approximate):", "test_a_history_that_cannot_be_read_does_not_stop_a_new_run"),
    ("H", "        if all(run[\"end\"] is not None or run[\"start\"] is None for run in read(self.folder, only=RUN_KINDS).runs.values()):\n            return                                     # nothing crashed: skip reading all of it, as this runs at every start\n", "", "test_a_normal_start_does_not_parse_the_whole_history"),
    ("H", "if all(run[\"end\"] is not None or run[\"start\"] is None for run", "if any(run[\"end\"] is not None or run[\"start\"] is None for run", "test_a_finished_run_is_left_alone_when_another_one_crashed"),
    # reading
    ("H", "elif row[\"schema\"] > SCHEMA:", "elif False:", "test_a_newer_row_is_skipped_with_a_notice_and_left_alone"),
    ("H", "if key not in closed or closed[key].get(\"interrupted\"):", "if key not in closed:", "test_a_real_close_beats_an_interrupted_one"),
    ("H", "corrections[run_id, row[\"match_number\"]] = row[\"not_a_match\"]", "corrections.setdefault((run_id, row[\"match_number\"]), row[\"not_a_match\"])", "test_the_latest_correction_wins"),
    ("H", "corrections.get(key, False)", "key[1] in {k[1] for k in corrections}", "test_a_correction_targets_one_run_only"),
    ("H", "or key in incomplete", "", "test_rows_really_lost_become_a_gap_row_at_the_next_successful_write"),
    # profiles
    ("profiles", "kept = _set_history_aside(base_state_path, profile_id)", "kept = None", "test_deleting_a_profile_moves_its_history_and_erases_nothing"),
    ("profiles", "            kept.replace(history_folder(base_state_path, profile_id))\n", "            pass\n", "test_a_failed_counter_move_puts_the_history_back"),
    ("profiles", "    while kept.exists():\n", "    while False:\n", "test_deleting_twice_in_one_second_keeps_both_histories"),
    ("profiles", "return Path(base_state_path).parent / \"history\" / profile_id", "return Path(base_state_path).parent / \"history\" / \"shared\"", "test_each_profile_has_its_own_folder"),
]


def main():
    caught = 0
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = getattr(T, name)
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__ = original.__file__
        sys.modules[mutant.__name__] = mutant                  # dataclasses need the module to be importable by name
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        try:
            with patch.object(T, name, mutant):
                getattr(T, test_name)()
        except (AssertionError, KeyboardInterrupt, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} history mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
