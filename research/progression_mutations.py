"""Small, reproducible sabotage checks for v0.4.0 M2: recorded chests, chests per hour, days, weeks and hours.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in tests/test_progression.py.
Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_progression as TP

MUTATIONS = [
    # what is counted
    ("elif chest[\"spectating\"]:\n                spectated.append(at)", "elif False:\n                spectated.append(at)", "test_recorded_chests_are_detected_plus_standing_corrections_without_the_spectated_one"),
    ("\n                    and m.get(\"english_confirmed\") is True and m[\"completion\"] in RELIABLE_FOR_SPECTATING]", "]", "test_a_spectating_chest_counts_when_attribution_is_uncertain"),
    (" and not m[\"not_a_match\"]\n", "\n", "test_a_spectating_chest_counts_when_attribution_is_uncertain"),
    ("            if correction[\"undone\"] or correction.get(\"run_id\") in left_out_runs:", "            if correction.get(\"run_id\") in left_out_runs:", "test_an_undone_correction_never_happened"),
    ("            if chest.get(\"run_id\") in left_out_runs:\n                continue\n", "", "test_simulate_runs_and_their_corrections_are_left_out"),
    ("            self.manual_removed += event.delta < 0", "            self.manual_removed += 0", "test_recorded_chests_are_detected_plus_standing_corrections_without_the_spectated_one"),
    ("        spectated = bisect_left(self.spectated, end) - bisect_left(self.spectated, start)", "        spectated = 0", "test_recorded_chests_are_detected_plus_standing_corrections_without_the_spectated_one"),
    # periods and chests per hour
    ("        return self.in_sessions / (self.session_seconds / HOUR_SECONDS)", "        return self.in_sessions / (self.counting_seconds / HOUR_SECONDS)", "test_all_time_is_session_time_with_its_gap_reported_apart"),
    ("        if self.session_seconds < MIN_HOURLY_SECONDS:", "        if self.session_seconds <= 0:", "test_half_an_hour_of_session_time_is_needed_for_a_rate"),
    ("        in_sessions = sum(self._recorded(a, b) for a, b in spans)", "        in_sessions = self._recorded(start, end)", "test_a_correction_made_while_not_counting_counts_on_its_day_but_not_in_any_session"),
    ("\"week\": TL.week_start(today)", "\"week\": today - timedelta(days=7)", "test_this_week_starts_on_monday"),
    ("\"last7\": today - timedelta(days=6)", "\"last7\": today - timedelta(days=7)", "test_last_7_and_30_days"),
    ("        session_seconds = sum(TL.total_seconds(TL.clip([(s.start, s.end)], start, end)) for s in sessions)", "        session_seconds = sum(s.span_seconds for s in sessions)", "test_today_takes_only_its_part_of_a_session_across_midnight"),
    ("for item in recognised) if recognised else None", "for item in recognised) if recognised else 0.0", "test_no_recognised_match_means_unknown_active_play_not_zero"),
    (" or self._chests_outside(recognised, start, end)", "", "test_active_play_and_time_between_matches"),
    ("            if event.manual:\n                continue\n            while index", "            while index", "test_active_play_and_time_between_matches"),
    ("running=self._running(history) if counting_now else None", "running=None", "test_the_run_counting_now_lasts_until_now"),
    # days and weeks
    ("        return \"chests\" if self.active else \"zero\" if self.monitored else \"not_counted\"", "        return \"chests\" if self.active else \"not_counted\"", "test_days_tell_chests_known_zeros_and_not_counted_apart"),
    ("                days[day].counted_seconds += seconds", "                days[day].counted_seconds += 0", "test_days_tell_chests_known_zeros_and_not_counted_apart"),
    ("if day.day < self.today]\n        return _averages", "if day.day <= self.today]\n        return _averages", "test_the_three_day_averages_use_completed_days_only"),
    ("    monitored = [recorded for recorded, is_monitored, _ in rows if is_monitored]", "    monitored = [recorded for recorded, _, _ in rows]", "test_the_three_day_averages_use_completed_days_only"),
    ("days.per_calendar * 7 if days.per_calendar is not None else None", "weeks.per_calendar", "test_weeks_and_their_averages"),
    ("key=lambda day: (day.totals.recorded, -day.day.toordinal())", "key=lambda day: (day.totals.recorded, day.day.toordinal())", "test_a_tie_goes_to_the_first_day"),
    # sessions and hours
    ("for session in reversed(self.sessions)]", "for session in self.sessions]", "test_sessions_newest_first_with_their_rates"),
    ("            if TL.seconds_between(start, end) < HOUR_SECONDS:\n                continue\n", "", "test_a_session_shorter_than_an_hour_has_no_best_hour"),
    ("TL.seconds_between(out[-1][1], start) <= COVERAGE_TOLERANCE_SECONDS", "TL.seconds_between(out[-1][1], start) <= 600", "test_a_quick_restart_does_not_break_the_hour_but_a_real_gap_does"),
    ("            latest = end - hour\n", "            latest = end\n", "test_a_correction_after_counting_stopped_stays_out_of_the_best_hour"),
    ("        covered = TL.total_seconds(TL.clip(self._counted, start, self.now))", "        covered = HOUR_SECONDS", "test_the_current_hour_says_how_much_of_it_was_counted"),
]


def main():
    caught = 0
    original = TP.P
    source = Path(original.__file__).read_text(encoding="utf-8")
    for number, (old, new, test_name) in enumerate(MUTATIONS, 1):
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = original.__file__, original.__package__
        sys.modules[mutant.__name__] = mutant                  # dataclasses need the module to be importable by name
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        try:
            with patch.object(TP, "P", mutant):
                getattr(TP, test_name)()
        except (AssertionError, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {test_name}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} progression mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
