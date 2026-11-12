"""Small, reproducible sabotage checks for M8C's manual corrections.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in tests/test_corrections.py.
Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_corrections as R
import test_match_tracker as T
import fortnite_chest_counter as package
from fortnite_chest_counter import gui as gui_package
from fortnite_chest_counter.gui import app as real_app


MUTATIONS = [
    # the counter
    ("C", "        st[\"approximate\"] += delta\n        self._corrections_done", "        st[\"approximate\"] += delta; st[\"certain\"] += delta\n        self._corrections_done", "test_plus_one_changes_only_approx"),
    ("C", "if delta < 0 and st[\"approximate\"] - 1 < st[\"certain\"]:", "if False:", "test_approx_can_never_go_below_certain"),
    ("C", "if delta > 0 and st[\"approximate\"] >= MAX_STARTING_COUNT:", "if False:", "test_the_maximum_is_respected"),
    ("C", "if correction_id in self._corrections_done or any(c[\"id\"] == correction_id for c in known):", "if False:", "test_the_same_request_twice_counts_once"),
    ("C", "if correction_id in self._corrections_done or any(c[\"id\"] == correction_id for c in known):", "if correction_id in self._corrections_done:", "test_the_same_request_after_a_restart_counts_once"),
    ("C", "            if target[\"undone\"]:\n", "            if False:\n", "test_undoing_twice_does_nothing_more"),
    ("C", "            if target.get(\"counter_token\") != token:\n", "            if False:\n", "test_a_reset_ends_the_corrections_but_keeps_the_record"),
    ("C", "            delta, match_number = -target[\"delta\"], target.get(\"match_number\")\n", "            delta, match_number = target[\"delta\"], target.get(\"match_number\")\n", "test_undo_restores_the_total_and_keeps_the_record"),
    ("C", "            delta, match_number = -target[\"delta\"], target.get(\"match_number\")\n", "            delta, match_number = -target[\"delta\"], None\n", "test_a_correction_for_a_match_keeps_its_match_and_its_undo_does_too"),
    ("C", "        if match_number is not None and (type(match_number) is not int or match_number < 1):\n", "        if False:\n", "test_a_correction_for_an_unknown_match_is_refused"),
    ("H", "    if match_number is not None:\n        row[\"match_number\"] = match_number\n", "", "test_a_correction_for_a_match_keeps_its_match_and_its_undo_does_too"),
    ("GUI", "                tally[0 if original > 0 else 1] += -1 if result.get(\"undoes\") else 1\n", "                tally[0 if original > 0 else 1] += 1\n", "test_the_game_view_corrects_the_match_on_screen"),
    ("GUI", "        if self.mode != \"counting\" or target is None:\n            return\n", "", "test_the_game_view_corrects_the_match_on_screen"),
    ("GUI", "            rated = {\"certain\": detected[\"certain\"], \"approx\": max(detected[\"approx\"] - removed + (added if include else 0), detected[\"certain\"])}", "            rated = {\"certain\": detected[\"certain\"], \"approx\": max(detected[\"approx\"] - removed + added, detected[\"certain\"])}", "test_the_game_rate_counts_plus_ones_only_when_asked"),
    ("C", "        self.sync_external_changes()\n        st = self.state\n        correction_id", "        st = self.state\n        correction_id", "test_a_running_session_adopts_a_reset_before_correcting"),
    ("C", "        self.save()\n        self.write_obs()\n        self.log.write({\"event\": \"chest_correction\"", "        self.save()\n        self.log.write({\"event\": \"chest_correction\"", "test_obs_shows_the_corrected_total"),
    ("C", "        self.save()\n        self.write_obs()\n        self.log.write({\"event\": \"chest_correction\"", "        self.write_obs()\n        self.log.write({\"event\": \"chest_correction\"", "test_the_total_is_saved_before_the_record"),
    ("C", "            self.history.counter_changed(\"correction\", st[\"certain\"], st[\"approximate\"])\n", "            pass\n", "test_a_correction_is_not_read_as_lost_chests_after_a_crash"),
    ("C", "            except OSError as error:\n                recorded = False", "            except ZeroDivisionError as error:\n                recorded = False", "test_a_history_failure_keeps_the_total_and_warns_once"),
    ("C", "        except Exception as error:\n            self._warn_once(\"correction\",", "        except ZeroDivisionError as error:\n            self._warn_once(\"correction\",", "test_a_bug_cannot_stop_counting"),
    ("C", "            if reason not in CORRECTION_REASONS[delta]:\n", "            if False:\n", "test_bad_requests_are_refused_and_change_nothing"),
    ("C", "if type(delta) is not int or delta not in CORRECTION_REASONS:", "if delta not in CORRECTION_REASONS:", "test_bad_requests_are_refused_and_change_nothing"),
    ("C", "    st[\"counter_life\"] = old.state.get(\"counter_life\", 0) + 1\n    if action != \"reset\":", "    if action != \"reset\":", "test_edit_counts_ends_them_too"),
    ("C", "    session.state[\"counter_life\"] = old.state.get(\"counter_life\", 0) + 1\n", "", "test_the_reset_command_ends_them_too"),
    ("C", "    st[\"counter_life\"] = st.get(\"counter_life\", 0) + 1\n    st[\"events_logged\"] += 1", "    st[\"events_logged\"] += 1", "test_the_set_count_command_ends_them_too"),
    ("C", "                    if isinstance(request, dict):\n                        self._corrections.append(request)", "                    pass", "test_the_worker_applies_corrections_on_top_of_counted_chests"),
    ("C", "                    if isinstance(request, dict):\n", "                    if True:\n", "test_the_worker_ignores_broken_commands"),
    ("C", "                _apply_corrections(control, session)\n            marks =", "            marks =", "test_corrections_apply_while_counting_not_only_at_the_end"),
    ("C", "        if control is not None:                            # pressed while no video was arriving, or just before stopping\n            _apply_corrections(control, session)\n", "", "test_a_correction_just_before_stopping_is_not_lost"),
    # the record
    ("H", "            merged[row[\"undoes\"]][\"undone\"] = True\n", "            pass\n", "test_undo_restores_the_total_and_keeps_the_record"),
    ("H", "            merged[row[\"corrects\"]][\"reason\"] = row.get(\"reason\")\n", "            pass\n", "test_a_reason_can_be_given_later_and_the_latest_wins"),
    ("H", "if row[\"kind\"] == \"chest_correction\" and row.get(\"delta\") in (1, -1):", "if row[\"kind\"] == \"chest_correction\":", "test_corrupt_correction_rows_are_ignored"),
    ("H", "standing = [c for c in corrections if not c[\"undone\"] and (counter_token is None or c.get(\"counter_token\") == counter_token)]", "standing = [c for c in corrections if counter_token is None or c.get(\"counter_token\") == counter_token]", "test_an_undone_correction_makes_no_claim"),
    ("H", "standing = [c for c in corrections if not c[\"undone\"] and (counter_token is None or c.get(\"counter_token\") == counter_token)]", "standing = [c for c in corrections if not c[\"undone\"]]", "test_a_reset_ends_the_corrections_but_keeps_the_record"),
    ("H", "\"detector_misses\": reasons.count(MISSED)", "\"detector_misses\": sum(c[\"delta\"] == 1 for c in standing)", "test_only_explicit_reasons_count_as_detector_errors"),
    ("H", "\"detector_false_positives\": reasons.count(FALSE_POSITIVE)", "\"detector_false_positives\": sum(c[\"delta\"] == -1 for c in standing)", "test_only_explicit_reasons_count_as_detector_errors"),
    ("H", "        if row[\"kind\"] in CORRECTION_KINDS:\n            correction_rows.append(row)\n            continue\n", "", "test_correction_rows_do_not_disturb_reading_chests"),
    # the app
    ("GUI", "        if self.worker.running():\n            if not self.worker.send(\"correct \" + json.dumps(request)):", "        if False:\n            if not self.worker.send(\"correct \" + json.dumps(request)):", "test_while_counting_the_worker_makes_the_change"),
    ("GUI", "        d.minus.setEnabled(ready and room)\n", "        d.minus.setEnabled(ready)\n", "test_minus_is_disabled_when_approx_equals_certain"),
    ("GUI", "        ready = self.mode != \"stopping\"\n", "        ready = True\n", "test_the_buttons_wait_while_stopping"),
    ("GUI", "        self.correction_memory[last[\"delta\"]] = reason\n", "", "test_choosing_a_reason_is_saved_and_remembered"),
    ("GUI", "            match_history.set_correction_reason(self._history_folder(), last[\"id\"], reason)\n", "            pass\n", "test_choosing_a_reason_is_saved_and_remembered"),
    ("GUI", "        d.correction_row.setVisible(bool(standing))\n", "        d.correction_row.setVisible(True)\n", "test_undo_from_the_dashboard"),
    ("GUI", "        for key, text in CORRECTION_WHY[last[\"delta\"]]:\n", "        for key, text in CORRECTION_WHY[1]:\n", "test_minus_one_offers_its_own_reasons"),
    ("GUI", "        self.refresh_corrections()\n        what = \"reset to 0\"", "        what = \"reset to 0\"", "test_a_reset_clears_the_line"),
    ("GUI", "        self.dashboard.types.setText(types_text(read_types(path) or C.type_breakdown(C.fresh_state())))\n        self.refresh_corrections()\n", "        self.dashboard.types.setText(types_text(read_types(path) or C.type_breakdown(C.fresh_state())))\n", "test_each_profile_shows_its_own_line"),
    ("GUI", "self.set_not_a_match(m, not m.excluded)", "self.set_not_a_match(m, True)", "test_restore_puts_it_back_exactly"),
    ("GUI", "(\"Not a match\", theme.DIM) if match.excluded else QUALITY_LOOK[match.quality]", "QUALITY_LOOK[match.quality]", "test_not_a_match_updates_the_statistics"),
    ("GUI", "        except OSError as error:\n            show_error(self, f\"The correction could not be saved ({error}).\")\n            return\n        self.refresh()", "        except ZeroDivisionError as error:\n            return\n        self.refresh()", "test_a_failed_save_is_explained"),
    ("GUI", "            if old is not None:\n                old.hide()\n", "            pass\n", "test_replaced_buttons_do_not_stay_on_screen"),
    ("GUI", "needed = [max(header.sectionSizeHint(column), table.sizeHintForColumn(column)) + 4 for column in range(last)]", "needed = [20 for column in range(last)]", "test_the_longest_labels_are_not_cut_off"),
    ("GUI", "for row in range(table.rowCount()) if table.cellWidget(row, last)] + [0]) + 24)", "for row in range(0)] + [0]) + 20)", "test_the_longest_labels_are_not_cut_off"),
    ("GUI", "if table.cellWidget(row, last)] + [0]) + 24)", "if table.cellWidget(row, last)] + [0]) + 12)", "test_the_longest_labels_are_not_cut_off"),
    ("GUI", "            table.setColumnWidth(column, width + (spare if column < last else 0))", "            table.setColumnWidth(column, width)", "test_a_wide_table_uses_its_width"),
    ("GUI", "        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)\n", "", "test_a_narrow_table_scrolls_instead_of_cutting_off"),
    ("GUI", "        self.table.viewport().installEventFilter(self)\n", "", "test_resizing_the_window_fits_the_columns_again"),
    # the statistics
    ("A", "    for match in reversed(usable):", "    for match in reversed(kept):", "test_not_a_match_updates_the_statistics"),
    ("A", "    summary.manual_added, summary.manual_removed = manual[\"added\"], manual[\"removed\"]\n", "", "test_statistics_ignore_manual_corrections"),
]


def main():
    caught = 0
    originals = {"C": R.C, "H": R.H, "GUI": real_app, "A": R.A}
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = originals[name]
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = original.__file__, original.__package__
        sys.modules[mutant.__name__] = mutant
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        targets = {"C": [(R, "C"), (T, "C")],
                   "H": [(R, "H"), (R.A, "H"), (package, "match_history"), (real_app, "match_history")],
                   "GUI": [(gui_package, "app")],
                   "A": [(R, "A"), (R.MA, "A"), (real_app, "match_analytics")]}[name]
        if name == "C":                                        # the window calls the counter through its own reference
            targets.append((real_app, "C"))
        patches = [patch.object(owner, attribute, mutant) for owner, attribute in targets]
        for item in patches:
            item.start()
        try:
            getattr(R, test_name)()
        except (AssertionError, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
        finally:
            for item in patches:
                item.stop()
    print(f"{caught}/{len(MUTATIONS)} correction mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
