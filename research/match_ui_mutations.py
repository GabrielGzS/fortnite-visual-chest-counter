"""Small, reproducible sabotage checks for M7's status line and settings.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in tests/test_match_ui.py.
Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_match_ui as U
import test_match_tracker as T
from fortnite_chest_counter import gui as gui_package
from fortnite_chest_counter.gui import app as real_app


MUTATIONS = [
    # what the line says
    ("A", "lead = \"In match\" if match.get(\"english_confirmed\") else \"Possibly in a match\"", "lead = \"In match\"", "test_a_game_without_english_evidence_is_only_possibly_a_match"),
    ("A", "    if not match.get(\"observed_from_start\"):\n        return \"partial: joined after the start\"\n", "", "test_joining_late_is_shown_as_partial"),
    ("A", "    if match.get(\"discontinuity\"):\n        return \"partial: part of it was not seen\"\n", "", "test_a_break_is_shown_as_partial"),
    ("A", "{' seen' if doubt else ''}", "", "test_joining_late_is_shown_as_partial"),
    ("A", "(\"Match over\" if match.get(\"ended_by\") in (\"placed\", \"victory\") else \"Spectating or out of the match\")", "\"Match over\"", "test_spectating_is_not_called_a_finished_match"),
    ("A", "(\"Match over\" if match.get(\"ended_by\") in (\"placed\", \"victory\") else \"Spectating or out of the match\")", "(\"Match complete\" if match.get(\"ended_by\") in (\"placed\", \"victory\") else \"Spectating or out of the match\")", "test_an_ending_is_never_called_complete"),
    ("A", "        doubt = _match_doubt(match) if match else \"\"\n", "        doubt = \"\"\n", "test_an_ending_in_a_partial_match_says_partial"),
    ("A", "if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 <= seconds < 10 ** 7:\n        return None", "if not isinstance(seconds, (int, float)):\n        return \"00:00\"", "test_an_unknown_time_is_never_shown_as_zero"),
    ("A", "return f\"{hours}:{minutes:02d}:{rest:02d}\" if hours else f\"{minutes:02d}:{rest:02d}\"", "return f\"{minutes:02d}:{rest:02d}\"", "test_long_matches_show_hours"),
    ("A", "    if message.get(\"picture\") in (\"black\", \"frozen\"):\n", "    if False:\n", "test_no_picture_is_said_out_loud"),
    ("A", "    elif state == \"IN_MATCH\" and match:\n", "    elif state == \"IN_MATCH\":\n", "test_broken_messages_mean_not_sure"),
    ("A", "        return \"Not sure yet\", theme.MUTED", "        return \"In the lobby\", theme.MUTED", "test_each_screen_has_its_own_words"),
    ("A", "    if message.get(\"failed\"):\n        return \"Stopped for this session after an error. Counting is not affected.\", theme.REJECT\n", "", "test_failures_say_counting_is_fine"),
    ("A", "    if message.get(\"unavailable\"):\n        return \"Not available for this session. Counting is not affected.\", theme.MUTED\n", "", "test_failures_say_counting_is_fine"),
    # the Dashboard
    ("A", "            self.show_match(message)\n", "            pass\n", "test_the_line_follows_the_worker"),
    ("A", "            d.match_row.hide()\n", "", "test_the_line_is_cleared_on_stop"),
    ("A", "            d.match.setText(\"\")\n            d.match_row.hide()\n", "            d.match_row.hide()\n", "test_a_new_session_starts_with_no_old_status"),
    ("A", "            self.match_seen_at = None\n            d.match.setText(\"\")", "            d.match.setText(\"\")", "test_the_line_is_cleared_on_stop"),
    ("A", "        if self.mode not in (\"connecting\", \"counting\", \"stopping\"):\n            return\n        text, color = match_line(message)", "        text, color = match_line(message)", "test_a_late_message_after_stopping_is_ignored"),
    ("A", "self.match_seen_at = None if message.get(\"failed\") or message.get(\"unavailable\") else time.monotonic()", "self.match_seen_at = time.monotonic()", "test_a_failure_stays_on_screen"),
    ("A", "        self._check_match_video()\n", "", "test_the_slow_timer_checks_for_silence"),
    ("A", "time.monotonic() - self.match_seen_at >= MATCH_STALE_SECONDS", "False", "test_silence_means_no_video"),
    ("A", "        d.match.setText(text)\n", "        d.match.setText(text); self.set_counts(99, 99)\n", "test_the_line_is_read_only"),
    ("A", "        d.match.setText(text)\n", "        d.match.setText(text); self.worker.send(\"stop\")\n", "test_the_line_is_read_only"),
    ("A", "        layout.addLayout(types)\n        self.match_row = QWidget()", "        self.match_row = QWidget()", "test_the_layout_keeps_its_pages_and_order"),
    # Settings
    ("A", "self.match_on.setChecked(self._match_mode == \"on\")", "self.match_on.setChecked(self._match_mode != \"off\")", "test_shadow_is_kept_unless_the_user_turns_tracking_on"),
    ("A", "mode = \"on\" if self.match_on.isChecked() else \"shadow\" if self._match_mode == \"shadow\" else \"off\"", "mode = \"on\" if self.match_on.isChecked() else \"off\"", "test_shadow_is_kept_unless_the_user_turns_tracking_on"),
    ("A", "            self._match_mode = mode\n", "", "test_shadow_is_kept_unless_the_user_turns_tracking_on"),
    ("A", "{\"mode\": mode, \"heartbeat_seconds\": self.heartbeat.currentData()}", "{\"mode\": mode}", "test_every_interval_saves"),
    ("A", "self.heartbeat.setCurrentIndex(max(self.heartbeat.findData(cfg[\"match\"][\"heartbeat_seconds\"]), 0))", "self.heartbeat.setCurrentIndex(1)", "test_turning_it_on_is_saved_and_read_back"),
    ("A", "        self.match_on.toggled.connect(self.heartbeat.setEnabled)\n", "", "test_turning_it_on_is_saved_and_read_back"),
    ("A", "        self.heartbeat.setEnabled(self.match_on.isChecked())\n", "", "test_settings_start_off_at_a_minute"),
    ("settings", "(300, \"5 minutes\"), ", "", "test_the_choices_are_the_supported_ones_and_shadow_is_not_offered"),
    # the worker
    ("C", "status=(lambda **fields: CONSOLE.emit(\"match\", **fields)) if history is not None else None)", "status=lambda **fields: CONSOLE.emit(\"match\", **fields))", "test_only_on_reports_a_status"),
    ("C", "status=(lambda **fields: CONSOLE.emit(\"match\", **fields)) if history is not None else None)", "status=None)", "test_on_reports_once_per_second_of_video"),
    ("C", "        if history is not None:\n            CONSOLE.emit(\"match\", unavailable=True)\n", "", "test_a_tracker_that_cannot_start_is_reported"),
    ("C", "        CONSOLE.warn(f\"match history could not start ({error}); counting is not affected\")\n        CONSOLE.emit(\"match\", unavailable=True)\n", "        CONSOLE.warn(f\"match history could not start ({error}); counting is not affected\")\n", "test_a_history_that_cannot_start_is_reported"),
    ("MT", "        self._tell(t, picture)\n", "", "test_the_status_carries_what_the_line_needs"),
    ("MT", "        except Exception:\n            self._status = None\n", "        except ZeroDivisionError:\n            self._status = None\n", "test_a_failing_status_cannot_stop_recording"),
    ("MT", "picture=\"black\" if picture.black else \"frozen\" if picture.frozen else \"live\"", "picture=\"live\"", "test_the_status_reports_a_black_picture"),
    ("S", "\"observed_from_start\": match.observed_from_start, ", "", "test_the_status_carries_what_the_line_needs"),
]


def load(name):
    return {"A": real_app, "settings": U.settings, "C": U.C, "MT": T.MT, "S": U.S}[name]


def main():
    caught = 0
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = load(name)
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__ = original.__file__
        mutant.__package__ = original.__package__
        sys.modules[mutant.__name__] = mutant                  # dataclasses need the module to be importable by name
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        targets = {"A": [(gui_package, "app")], "settings": [(real_app, "settings")], "C": [(U, "C"), (T, "C")], "MT": [(T, "MT")]}.get(name, [])
        if name == "S":                                        # the tracker's own reference is what makes the machine
            targets = [(T.MT, "S")]
        patches = [patch.object(owner, attribute, mutant) for owner, attribute in targets]
        try:
            for item in patches:
                item.start()
            getattr(U, test_name)()
        except (AssertionError, KeyboardInterrupt, RuntimeError, ZeroDivisionError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
        finally:
            for item in patches:
                item.stop()
    print(f"{caught}/{len(MUTATIONS)} match UI mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
