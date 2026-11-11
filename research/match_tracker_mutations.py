"""Small, reproducible sabotage checks for M4's isolation guarantees.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in
tests/test_match_tracker.py. Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_match_tracker as T


MUTATIONS = [
    ("MT", "SAMPLE_SECONDS = 1.0", "SAMPLE_SECONDS = 0.5", "test_one_sample_per_second_at_every_frame_rate"),
    ("MT", "        self._last_sample_t = t\n", "", "test_one_sample_per_second_at_every_frame_rate"),
    ("MT", "SAMPLE_TOLERANCE = 1e-6", "SAMPLE_TOLERANCE = -0.05", "test_one_sample_per_second_at_every_frame_rate"),
    ("MT", "if last is not None and 0 <= t - last < SAMPLE_SECONDS", "if last is not None and t - last < SAMPLE_SECONDS", "test_a_jump_in_time_is_sampled_at_once"),
    ("MT", "picture = self._cues.picture_evidence(frame, self._picture)", "frame[0, 0] = 1; picture = self._cues.picture_evidence(frame, self._picture)", "test_frames_are_not_changed_even_when_writable"),
    ("MT", "self._picture = picture.sample", "self._picture = frame", "test_frames_are_only_read"),
    ("MT", "if not (ev.get(\"certain_counted\") or ev.get(\"approx_counted\")):", "if False:", "test_only_counted_chests_are_evidence"),
    ("MT", "            self._pending.clear()\n            self._break_t = t", "            self._break_t = t", "test_a_chest_from_before_a_break_is_not_evidence_after_it"),
    ("MT", "if self._break_t is not None and ev[\"time\"] < self._break_t:", "if False:", "test_a_chest_finishing_late_after_a_break_is_dropped_too"),
    ("MT", "chests, self._pending = tuple(self._pending), []", "chests = tuple(self._pending)", "test_a_chest_is_delivered_once_with_its_language"),
    ("MT", "        except Exception as error:\n            self._fail(\"offer\", error)\n            return", "        except ZeroDivisionError as error:\n            self._fail(\"offer\", error)\n            return", "test_a_reader_failure_warns_once_and_stops_tracking"),
    ("MT", "        except Exception as error:\n            self._fail(\"chest\", error)", "        except ZeroDivisionError as error:\n            self._fail(\"chest\", error)", "test_a_malformed_event_is_contained"),
    ("MT", "        except Exception as error:\n            self._fail(\"close\", error)", "        except KeyError as error:\n            self._fail(\"close\", error)", "test_a_failure_while_closing_is_contained"),
    ("MT", "        self.failed = True\n", "", "test_a_reader_failure_warns_once_and_stops_tracking"),
    ("MT", "        except Exception as error:\n            self._fail(\"offer\", error)\n            return", "        except BaseException as error:\n            self._fail(\"offer\", error)\n            return", "test_the_user_stopping_is_not_swallowed"),
    ("MT", "            except Exception:\n                pass", "            except ZeroDivisionError:\n                pass", "test_a_failing_warning_is_contained"),
    ("MT", "{\"event\": LOG_EVENT, \"kind\": kind, **fields}", "{\"event\": LOG_EVENT, \"kind\": kind, \"time\": 0.0, **fields}", "test_every_line_is_a_match_state_line_and_none_looks_like_a_chest"),
    ("MT", "ended_by = S.LOST if reason in SOURCE_LOST_REASONS else S.STOPPED", "ended_by = S.STOPPED", "test_a_source_that_vanishes_is_recorded_as_lost"),
    ("MT", "self._report(self._machine.finish(self._last_seen_t, ended_by))", "pass", "test_stopping_mid_match_is_partial_and_says_so"),
    ("MT", "        if self.failed or self.closed:\n            return\n        begin", "        if self.failed:\n            return\n        begin", "test_closing_twice_and_offering_after_closing_do_nothing"),
    ("MT", "record[\"evidence\"] = sorted(record[\"evidence\"], key=lambda item: (item[0], item[1]))", "record[\"evidence\"] = sorted(record[\"evidence\"], key=lambda item: item[1], reverse=True)", "test_evidence_order_does_not_depend_on_the_python_hash_seed"),
    ("settings", "MATCH_MODES = (\"off\", \"shadow\", \"on\")", "MATCH_MODES = (\"off\", \"shadow\")", "test_on_can_be_chosen_explicitly"),
    ("settings", "MATCH_MODES = (\"off\", \"shadow\", \"on\")", "MATCH_MODES = (\"off\", \"shadow\", \"on\", \"maybe\")", "test_a_nonsense_mode_falls_back_to_off"),
    ("settings", "\"mode\": \"on\",                           # off | shadow (recognise", "\"mode\": \"shadow\",                       # off | shadow (recognise", "test_tracking_is_on_by_default"),
    ("settings", "SAFE_FALLBACKS = {(\"match\", \"mode\"): \"off\"}", "SAFE_FALLBACKS = {}", "test_a_nonsense_mode_falls_back_to_off"),
    ("C", "    if cfg[\"match\"][\"mode\"] == \"off\":\n        return None\n", "", "test_off_leaves_the_session_log_as_it_was"),
    ("C", "    if history is None and not cfg[\"logging\"][\"enabled\"]:\n", "    if False:\n", "test_shadow_without_logging_does_not_run"),
    ("C", "session.log.write({**stats, **tracker.stats()} if tracker is not None else stats)", "stats.update(tracker.stats() if tracker is not None else {}); session.log.write(stats)", "test_the_desktop_app_sees_no_difference"),
    ("C", "            tracker.close(stop_reason)\n", "            pass\n", "test_ctrl_c_closes_the_open_match_and_keeps_the_counts"),
    ("C", "            dt = time.perf_counter() - t0\n", "            if tracker is not None:\n                tracker.offer(t, frame)\n            dt = time.perf_counter() - t0\n", "test_shadow_reports_its_time_apart_from_detection"),
    ("C", "                for ev in applied:\n                    tracker.chest(ev)\n                tracker.offer(t, frame)\n            now_m", "                tracker.offer(t, frame)\n            now_m", "test_counted_chests_reach_the_tracker_from_both_loops"),
    ("C", "            for ev in flushed:\n                tracker.chest(ev)\n            tracker.close(stop_reason)", "            tracker.close(stop_reason)", "test_counted_chests_reach_the_tracker_from_both_loops"),
    ("C", "            for ev in applied:\n                tracker.chest(ev)\n            tracker.offer(t, frame)\n        if args.realtime", "            tracker.offer(t, frame)\n        if args.realtime", "test_counted_chests_reach_the_tracker_from_both_loops"),
    ("C", "                tracker.offer(t, frame)\n            now_m", "                tracker.offer(t, frame); state[\"certain\"] += 1\n            now_m", "test_live_counts_the_same_with_tracking_off_and_in_shadow"),
    ("C", "            tracker.offer(t, frame)\n        if args.realtime", "            tracker.offer(t, frame); state[\"approximate\"] += 1\n        if args.realtime", "test_simulate_counts_the_same_with_tracking_off_and_in_shadow"),
    ("C", "            tracker.close(stop_reason)\n", "            tracker.close(stop_reason); session.state[\"certain\"] += 1; session.write_obs(); session.save()\n", "test_live_counts_the_same_with_tracking_off_and_in_shadow"),
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
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        try:
            with patch.object(T, name, mutant):
                getattr(T, test_name)()
        except (AssertionError, KeyboardInterrupt, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} tracker mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
