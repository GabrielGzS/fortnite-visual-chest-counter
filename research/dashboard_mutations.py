"""Small, reproducible sabotage checks for M8A's Dashboard views.

Mutates a private in-memory copy of gui/app.py, never repository files. Each mutation must be rejected by a named test in
tests/test_dashboard_views.py. Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_dashboard_views as D
from fortnite_chest_counter import gui as gui_package
from fortnite_chest_counter.gui import app as real_app


MUTATIONS = [
    ("        self.views.setCurrentIndex(index)\n", "", "test_clicking_a_tab_switches_the_view"),
    ("self.view_buttons.idClicked.connect(self.show_view)", "pass", "test_clicking_a_tab_switches_the_view"),
    ("self.view_buttons.button(OVERVIEW_VIEW).setChecked(True)", "self.view_buttons.button(GAME_VIEW).setChecked(True)", "test_there_are_three_views_starting_on_overview"),
    ("        self.views.setCurrentIndex(index)\n", "        self.views.setCurrentIndex(index); self.win.set_counts(1, 1)\n", "test_switching_views_changes_nothing_else"),
    ("overview, game, console = pages", "overview, console, game = pages", "test_every_control_is_on_its_view"),
    ("        layout.addWidget(self.banner)\n", "        self.views_banner = self.banner\n", "test_status_and_errors_stay_above_the_views"),
    ("        if message.get(\"type\") in (\"warn\", \"error\"):\n            self.dashboard.note_warning()\n", "", "test_warnings_are_flagged_on_the_tab_when_the_log_is_out_of_sight"),
    ("message.get(\"type\") in (\"warn\", \"error\")", "message.get(\"type\") in (\"warn\",)", "test_warnings_are_flagged_on_the_tab_when_the_log_is_out_of_sight"),
    ("message.get(\"type\") in (\"warn\", \"error\")", "message.get(\"type\") in (\"warn\", \"error\", \"info\")", "test_ordinary_lines_do_not_flag_the_tab"),
    ("            self._unread_warnings = 0\n            self._label_console()\n", "            pass\n", "test_opening_the_console_clears_the_flag"),
    ("        if self.views.currentIndex() != CONSOLE_VIEW:\n            self._unread_warnings += 1", "        if True:\n            self._unread_warnings += 1", "test_a_warning_while_reading_the_console_needs_no_flag"),
    ("return {OVERVIEW_VIEW: d.mini_preview, GAME_VIEW: d.preview}.get(d.views.currentIndex())", "return d.preview", "test_the_preview_runs_only_while_its_view_is_open"),
    ("        self.win.preview_visibility_changed()\n\n    def note_warning", "\n    def note_warning", "test_the_preview_runs_only_while_its_view_is_open"),
    ("        self.preview.setVisible(on)\n", "        self.preview.setVisible(True)\n", "test_the_preview_can_be_hidden"),
    ("        d.show_game(message, text, color)\n", "", "test_a_match_fills_the_tiles"),
    ("self.game_unclear.set_value(match_clock(match.get(\"uncertain_seconds\")))", "self.game_unclear.set_value(match_clock(match.get(\"observed_seconds\")))", "test_a_match_fills_the_tiles"),
    ("self.game_start.set_value({True: \"Yes\", False: \"No\"}.get(match.get(\"observed_from_start\")))", "self.game_start.set_value(\"Yes\")", "test_a_match_fills_the_tiles"),
    ("self.value.setText(UNKNOWN_VALUE if value is None else str(value))", "self.value.setText(\"0\" if value is None else str(value))", "test_no_open_match_shows_dashes_not_zeros"),
    ("            for line in (self.dashboard.match, self.dashboard.game_status):\n", "            for line in (self.dashboard.match,):\n", "test_silence_reaches_the_game_view"),
    ("mode = self.session_match_mode if running else load_cfg()[0][\"match\"][\"mode\"]", "mode = load_cfg()[0][\"match\"][\"mode\"]", "test_a_session_keeps_the_mode_it_started_with"),
    ("        if mode == \"on\":\n            d.show_game_idle(", "        if mode != \"off\":\n            d.show_game_idle(", "test_shadow_counts_as_off_in_the_app"),
    ("        self.update_game_idle()\n        self.update_correction_buttons()\n", "        self.update_correction_buttons()\n", "test_stopping_resets_the_game_view"),
    ("        self.game_settings.setVisible(offer_settings)\n", "", "test_tracking_on_but_not_counting"),
    ("on_click=lambda: win.show_page(win.settings_page)", "on_click=lambda: None", "test_the_links_open_their_pages"),
    ("        if page is self.overlay:\n            self.overlay.load()\n", "        if False:\n            pass\n", "test_opening_a_page_still_reloads_it"),
]


def main():
    caught = 0
    source = Path(real_app.__file__).read_text(encoding="utf-8")
    for number, (old, new, test_name) in enumerate(MUTATIONS, 1):
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(real_app.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = real_app.__file__, real_app.__package__
        sys.modules[mutant.__name__] = mutant
        exec(compile(source.replace(old, new, 1), real_app.__file__, "exec"), mutant.__dict__)
        with patch.object(gui_package, "app", mutant):
            try:
                getattr(D, test_name)()
            except (AssertionError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
                caught += 1
                print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
            else:
                print(f"SURVIVED {number:02d}: {test_name}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} dashboard mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
