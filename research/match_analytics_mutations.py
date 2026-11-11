"""Small, reproducible sabotage checks for M8B's statistics and Analytics page.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in
tests/test_match_analytics.py. Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_match_analytics as T
from fortnite_chest_counter import gui as gui_package
from fortnite_chest_counter.gui import app as real_app


MUTATIONS = [
    # counts and times
    ("A", "summary.observed_seconds = _total(complete + partial, \"observed_seconds\")", "summary.observed_seconds = _total(kept, \"observed_seconds\")", "test_unconfirmed_matches_stay_out_of_every_statistic"),
    ("A", "summary.observed_seconds = _total(complete + partial, \"observed_seconds\")", "summary.observed_seconds = _total(complete, \"observed_seconds\")", "test_times_are_kept_apart"),
    ("A", "summary.confirmed_seconds = _total(complete, \"active_seconds\")", "summary.confirmed_seconds = _total(complete + partial, \"active_seconds\")", "test_times_are_kept_apart"),
    ("A", "    return sum(known) if known else None", "    return sum(known)", "test_partial_only_history_shows_time_but_no_complete_figures"),
    ("A", "    kept = [match for match in usable if not match[\"not_a_match\"]]", "    kept = list(usable)", "test_not_a_match_removes_it_from_every_statistic_and_undo_restores_it"),
    ("A", "        summary.sessions += 1\n", "", "test_times_are_kept_apart"),
    ("A", "            summary.sessions_cut_short += 1\n", "            pass\n", "test_an_interrupted_match_counts_as_partial_with_only_its_reported_time"),
    ("A", "summary.session_seconds = sum(known_sessions) if known_sessions else None", "summary.session_seconds = sum(known_sessions)", "test_an_empty_history_has_no_values"),
    # chests
    ("A", "bool(chest.get(\"approx_counted\") or chest.get(\"certain_counted\"))", "bool(chest.get(\"approx_counted\"))", "test_a_certain_chest_counts_once_in_approx_even_if_its_flag_is_missing"),
    ("A", "        summary.approx_chests += approx\n", "        summary.approx_chests += approx + certain\n", "test_chests_are_not_double_counted"),
    ("A", "        if chest[\"credited\"]:\n", "        if chest[\"match_number\"] is not None:\n", "test_chests_are_not_double_counted"),
    ("A", "    for match in complete + partial:\n        totals = credited", "    for match in kept:\n        totals = credited", "test_unconfirmed_matches_stay_out_of_every_statistic"),
    # rates
    ("A", "summary.complete_rate = _rate(complete_ready, credited)", "summary.complete_rate = _rate(seen_ready, credited)", "test_the_complete_rate_uses_only_complete_matches"),
    ("A", "summary.observed_rate = _rate(seen_ready, credited, MIN_OBSERVED_RATE_SECONDS)", "summary.observed_rate = _rate(complete_ready, credited, MIN_OBSERVED_RATE_SECONDS)", "test_the_observed_rate_includes_partial_matches_and_stays_separate"),
    ("A", "summary.observed_rate = _rate(seen_ready, credited, MIN_OBSERVED_RATE_SECONDS)", "summary.observed_rate = _rate(seen_ready, credited)", "test_too_little_observed_play_gives_no_observed_rate"),
    ("A", "seconds < enough_seconds:", "seconds <= enough_seconds:", "test_exactly_enough_observed_play_gives_a_rate"),
    ("A", "return active is not None and active > 0 and not match[\"history_incomplete\"]", "return active is not None and active > 0", "test_a_match_with_lost_chests_is_flagged_and_left_out_of_rates"),
    ("A", "return active is not None and active > 0 and not match[\"history_incomplete\"]", "return active is not None and not match[\"history_incomplete\"]", "test_zero_active_time_cannot_produce_a_rate"),
    ("A", "        active = _number(match.get(\"active_seconds\"))\n", "        active = _number(match.get(\"active_seconds\")) or 60.0\n", "test_unknown_active_time_is_left_out_not_counted_as_zero"),
    ("A", "    minutes = seconds / 60\n", "    minutes = seconds\n", "test_the_complete_rate_uses_only_complete_matches"),
    ("A", "sum(credited[key][0] for key in keys) / minutes, sum(credited[key][1] for key in keys) / minutes", "sum(credited[key][1] for key in keys) / minutes, sum(credited[key][0] for key in keys) / minutes", "test_the_complete_rate_uses_only_complete_matches"),
    ("A", "sum(credited[key][0] for key in keys) / len(keys), sum(credited[key][1] for key in keys) / len(keys), len(keys))", "sum(credited[key][0] for key in keys), sum(credited[key][1] for key in keys), len(keys))", "test_per_complete_match"),
    # recent matches and damaged data
    ("A", "    for match in reversed(usable[-recent:]):", "    for match in usable[-recent:]:", "test_recent_matches_are_newest_first_with_their_evidence"),
    ("A", "    for match in reversed(usable[-recent:]):", "    for match in reversed(usable):", "test_recent_is_limited"),
    ("A", "full = match[\"completion\"] == COMPLETE and _number(match.get(\"complete_duration_seconds\")) is not None", "full = True", "test_recent_matches_are_newest_first_with_their_evidence"),
    ("A", "ENDINGS.get(match.get(\"ended_by\"), \"Not seen\")", "ENDINGS.get(match.get(\"ended_by\"), \"Placed\")", "test_an_unknown_ending_says_not_seen"),
    ("A", "bool(match[\"history_incomplete\"]), match[\"completion\"]", "False, match[\"completion\"]", "test_a_match_with_lost_chests_is_flagged_and_left_out_of_rates"),
    ("A", "    usable = [match for match in history.matches if _usable(match)]", "    usable = list(history.matches)", "test_rows_with_impossible_values_are_counted_as_damaged"),
    ("A", "summary.missing_certain += max(_number(gap.get(\"missing_certain\")) or 0, 0)", "pass", "test_a_match_with_lost_chests_is_flagged_and_left_out_of_rates"),
    ("A", "        return datetime.fromisoformat(run[\"start\"][\"at\"]) + timedelta(seconds=match[\"opened_t\"])", "        return datetime.fromisoformat(run[\"start\"][\"at\"])", "test_a_match_start_comes_from_the_run_clock"),
    ("A", "if _number(seconds) is None or seconds < 0:\n        return None", "if _number(seconds) is None or seconds < 0:\n        return \"0s\"", "test_durations_read_naturally"),
    # attribution
    ("H", "if index >= 0 and t < by_run[run_id][index][\"closed_t\"] else None", "if index >= 0 else None", "test_an_interrupted_match_counts_as_partial_with_only_its_reported_time"),
    # the page
    ("GUI", "            if generation != self._generation:                # an older request: a newer one, or another profile, replaced it\n                continue\n", "", "test_an_old_request_cannot_overwrite_a_newer_one"),
    ("GUI", "        self._thread = threading.Thread(target=self._read, args=(self._generation, folder), daemon=True, name=\"analytics\")\n        self._thread.start()\n", "        self._read(self._generation, folder)\n", "test_a_slow_history_does_not_freeze_the_window"),
    ("GUI", "        self.empty.setVisible(s.empty)\n", "", "test_the_empty_page_shows_dashes_and_explains"),
    ("GUI", "self.certain.set_value(fmt(s.certain_chests) if not s.empty else None)", "self.certain.set_value(fmt(s.certain_chests))", "test_the_empty_page_shows_dashes_and_explains"),
    ("GUI", "if seen is None else seen if match.duration_is_full else f\"{seen} seen\"", "if seen is None else seen", "test_the_page_shows_the_worked_example"),
    ("GUI", "more = \"+\" if match.chests_may_be_missing else \"\"", "more = \"\"", "test_the_page_tells_the_reader_what_to_be_careful_about"),
    ("GUI", "        elif page is self.analytics:\n            self.analytics.refresh()\n", "", "test_opening_the_page_reads_the_history"),
    ("GUI", "            if self.pages.currentWidget() is self.analytics:\n                self.analytics.refresh()", "            if True:\n                self.analytics.refresh()", "test_the_page_refreshes_when_counting_stops_only_if_open"),
    ("GUI", "folder = paths.APP_DIR / profiles.history_folder(profile[\"state_base\"], profile[\"id\"])", "folder = paths.APP_DIR / profiles.history_folder(profile[\"state_base\"], \"default\")", "test_switching_profile_shows_that_profiles_history"),
    ("GUI", "self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)", "pass", "test_the_table_cannot_be_edited"),
    ("GUI", "        self.notes.setText(analytics_notes(s))\n", "", "test_the_page_tells_the_reader_what_to_be_careful_about"),
]


def main():
    caught = 0
    originals = {"A": T.A, "H": T.H, "GUI": real_app}
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = originals[name]
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = original.__file__, original.__package__
        sys.modules[mutant.__name__] = mutant
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        if name == "A":
            patches = [patch.object(T, "A", mutant), patch.object(real_app, "match_analytics", mutant)]
        elif name == "H":
            patches = [patch.object(T.A, "H", mutant)]
        else:
            patches = [patch.object(gui_package, "app", mutant)]
        for item in patches:
            item.start()
        try:
            getattr(T, test_name)()
        except (AssertionError, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
        finally:
            for item in patches:
                item.stop()
    print(f"{caught}/{len(MUTATIONS)} analytics mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
