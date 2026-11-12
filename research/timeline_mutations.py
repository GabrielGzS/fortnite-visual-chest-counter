"""Small, reproducible sabotage checks for v0.4.0 M1: real-life time, sessions, calendar days, and history kept with tracking off.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in tests/test_timeline.py.
Run after that file passes. Two checks (17, 18) need the PC's time zone to differ from UTC, which it does where this project is developed.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_timeline as TT
import test_match_tracker as T

LIVE_BEAT = ("    tracker = _open_tracker(cfg, session, _tracker_history(cfg, history), source)\n"
             "    beat = HistoryHeartbeat(history, cfg[\"match\"][\"heartbeat_seconds\"], lambda: (source.frames_processed, source.frames_dropped)) if history is not None else None\n"
             "    last_t = None")

MUTATIONS = [
    # runs
    ("TL", "                end, clean = start + timedelta(seconds=elapsed), True", "                end, clean = (at_end or start), True", "test_a_changed_clock_cannot_stretch_a_run"),
    ("TL", "abs(seconds_between(start, at_end) - elapsed) > CLOCK_TOLERANCE_SECONDS", "abs(seconds_between(start, at_end) - elapsed) > 0", "test_a_small_difference_is_not_a_clock_change"),
    ("TL", "            end = parse_at(end_row.get(\"last_seen_at\")) or start", "            end = parse_at(end_row.get(\"at\")) or start", "test_recovery_days_later_does_not_count_as_counting"),
    ("TL", "        elif run_id == running:", "        elif False:", "test_the_run_counting_now_lasts_until_now"),
    ("TL", "            beat = heartbeats.get(run_id) or run.get(\"last_heartbeat\")", "            beat = run.get(\"last_heartbeat\")", "test_a_crashed_run_lasts_until_its_last_heartbeat_at_least"),
    ("TL", "            end = end or start", "            end = end or now", "test_a_crashed_run_without_its_heartbeats_read_is_not_stretched"),
    ("TL", "        if start is None or source in LEFT_OUT_SOURCES:", "        if start is None:", "test_simulate_runs_are_nobodys_play"),
    ("TL", "    return moment.astimezone(UTC) if moment.utcoffset() is not None else None", "    return moment.astimezone(UTC)", "test_a_time_without_its_offset_is_not_guessed"),
    ("TL", "    out.sort(key=lambda r: r.start)\n    return out", "    return out", "test_runs_come_out_oldest_first"),
    ("TL", "        return not self.ended_cleanly and not self.in_progress", "        return not self.ended_cleanly", "test_the_run_counting_now_lasts_until_now"),
    # sessions
    ("TL", "seconds_between(out[-1].end, run.start) < break_seconds", "seconds_between(out[-1].end, run.start) <= break_seconds", "test_runs_less_than_thirty_minutes_apart_are_one_session_and_the_gap_is_not_counting"),
    ("TL", "seconds_between(out[-1].end, run.start) < break_seconds", "seconds_between(out[-1].runs[-1].start, run.start) < break_seconds", "test_overlapping_runs_are_not_counted_twice"),
    ("TL", "        if result and start <= result[-1][1]:", "        if False:", "test_overlapping_runs_are_not_counted_twice"),
    ("TL", "        return max(self.span_seconds - self.counted_seconds, 0.0)", "        return 0.0", "test_runs_less_than_thirty_minutes_apart_are_one_session_and_the_gap_is_not_counting"),
    ("TL", "        return any(run.cut_short for run in self.runs)", "        return False", "test_a_session_with_a_crashed_run_is_cut_short_and_one_counting_now_is_in_progress"),
    # calendar
    ("TL", "        boundary = min(day_start(day + timedelta(days=1), zone), end)", "        boundary = min(cursor + timedelta(days=1), end)", "test_the_spring_day_has_23_hours_and_the_autumn_day_25"),
    ("TL", "    return moment.astimezone(zone) if zone is not None else moment.astimezone()", "    return moment.astimezone(zone or UTC)", "test_the_pcs_own_zone_is_used_when_none_is_given"),
    ("TL", "    aware = naive.astimezone() if zone is None else naive.replace(tzinfo=zone)", "    aware = naive.replace(tzinfo=zone or UTC)", "test_the_pcs_own_zone_is_used_when_none_is_given"),
    ("TL", "    for start, end in merged((run.start, run.end) for run in all_runs):", "    for start, end in ((run.start, run.end) for run in all_runs):", "test_overlapping_runs_count_once_on_their_day"),
    ("TL", "    return day - timedelta(days=day.weekday())", "    return day - timedelta(days=(day.weekday() + 1) % 7)", "test_day_start_and_week_start"),
    ("TL", "        if a < b:\n            out.append((a, b))", "        if a <= b:\n            out.append((a, b))", "test_clip_and_totals"),
    # last heartbeats
    ("H", "                if run_id not in found or order > found[run_id][0]:", "                if True:", "test_last_heartbeats_takes_the_newest_by_write_order"),
    ("H", "        if not line.startswith(b'{\"kind\":\"heartbeat\"'):\n            continue\n", "", "test_last_heartbeats_reads_only_the_runs_asked_for"),
    # the live loop (D7)
    ("C", "        if tracker is not None and tracker.keeps_history:", "        if False:", "test_with_tracking_on_only_the_tracker_writes_heartbeats"),
    ("C", LIVE_BEAT, LIVE_BEAT.replace("    beat = HistoryHeartbeat(", "    beat = None and HistoryHeartbeat("), "test_history_is_kept_with_match_tracking_off_or_in_shadow_but_without_match_rows"),
    ("C", "        if last is None or t < last or t - last >= self.seconds - 1e-6:", "        if last is None or t < last or t - last >= 1:", "test_history_is_kept_with_match_tracking_off_or_in_shadow_but_without_match_rows"),
    ("C", "    tracking = cfg[\"match\"][\"mode\"] == \"on\"\n    if not session.persist:", "    tracking = cfg[\"match\"][\"mode\"] == \"on\"\n    if not tracking:\n        return None\n    if not session.persist:", "test_history_is_kept_with_match_tracking_off_or_in_shadow_but_without_match_rows"),
    ("MT", "        return self._history is not None and not self.failed and not self.closed", "        return self._history is not None", "test_a_tracker_that_stops_after_an_error_hands_the_heartbeats_over"),
]


def main():
    caught = 0
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = getattr(TT, name)
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = original.__file__, original.__package__
        sys.modules[mutant.__name__] = mutant                  # dataclasses need the module to be importable by name
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        patches = [patch.object(TT, name, mutant)]
        if hasattr(T, name):                                   # the whole-loop helpers live in test_match_tracker
            patches.append(patch.object(T, name, mutant))
        if name == "MT":                                       # counter imports the tracker by name when it opens one
            patches.append(patch.dict(sys.modules, {original.__name__: mutant}))
        for item in patches:
            item.start()
        try:
            getattr(TT, test_name)()
        except (AssertionError, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
        finally:
            for item in reversed(patches):
                item.stop()
    print(f"{caught}/{len(MUTATIONS)} timeline mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
