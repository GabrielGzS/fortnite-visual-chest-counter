"""Small, reproducible sabotage checks for M9F: the live match numbers, the one preview, the default, the chest type and the per-match rate.

Mutates private in-memory module copies, never repository files. Each mutation must be rejected by a named test in tests/test_live_match.py.
Run after that file passes.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_live_match as L
import fortnite_chest_counter as package
from fortnite_chest_counter import console as real_console
from fortnite_chest_counter import gui as gui_package
from fortnite_chest_counter import match_analytics as real_analytics
from fortnite_chest_counter import match_tracker as real_tracker
from fortnite_chest_counter import settings as real_settings
from fortnite_chest_counter.gui import app as real_app


MUTATIONS = [
    # the tracker
    ("T", "self._counted.append((ev[\"time\"], bool(ev.get(\"certain_counted\")), True))", "self._counted.append((ev[\"time\"], True, True))", "test_certain_and_approx_are_counted_apart"),
    ("T", "            if not (ev.get(\"certain_counted\") or ev.get(\"approx_counted\")):\n                return\n            self._counted", "            self._counted", "test_a_rejected_candidate_is_not_counted"),
    ("T", "if opened_t <= t and played_from_t <= t and", "if opened_t <= t and", "test_a_chest_before_play_began_is_not_this_matchs"),
    ("T", "and (out_at is None or t < out_at):", "and True:", "test_after_elimination_chests_are_not_this_players"),
    ("T", "and (closed_t is None or t < closed_t) and", "and", "test_a_chest_after_the_match_closed_is_not_its"),
    ("T", "if opened_t <= t and played_from_t <= t and (closed_t is None or t < closed_t) and (out_at is None or t < out_at):", "if True:", "test_a_new_match_starts_again_from_zero"),
    ("T", "                if event.state == S.ELIMINATED and event.match_number is not None and self._out_at is None:\n                    self._out_at = event.t\n", "", "test_after_elimination_chests_are_not_this_players"),
    ("T", "        moments = [moment for moment in (closed[\"out_at\"], closed[\"ended_t\"]) if moment is not None]\n", "        moments = []\n", "test_live_numbers_equal_the_history_after_the_match"),
    ("T", "chests=self._credited(match[\"opened_t\"], match[\"played_from_t\"], None, self._out_at) if match else None", "chests={\"certain\": 0, \"approx\": 0}", "test_no_match_means_no_numbers"),
    ("T", "last_match=self._last_match())", "last_match=None)", "test_the_finished_match_keeps_its_numbers"),
    ("T", "self._closed, self._out_at = {**record, \"out_at\": self._out_at}, None", "self._closed, self._out_at = {**record, \"out_at\": None}, None", "test_chests_after_being_out_do_not_join_the_finished_match"),
    # the rate and the ending
    ("A", "if active is None or active < MIN_MATCH_RATE_SECONDS:", "if active is None:", "test_no_rate_in_the_first_minute"),
    ("A", "    return Rate(certain / minutes, approx / minutes, 1, minutes)\n", "    return Rate(approx / minutes, certain / minutes, 1, minutes)\n", "test_the_rate_uses_active_play"),
    ("A", "fair = rate_ready(match) and match[\"completion\"] != UNCONFIRMED and not match[\"not_a_match\"]", "fair = rate_ready(match) and not match[\"not_a_match\"]", "test_an_unconfirmed_match_has_no_rate"),
    ("A", "fair = rate_ready(match) and match[\"completion\"] != UNCONFIRMED and not match[\"not_a_match\"]", "fair = rate_ready(match) and match[\"completion\"] != UNCONFIRMED", "test_a_match_marked_not_a_match_has_no_rate"),
    ("A", "    if ended_by == \"left_or_unknown\" and reasons and reasons[-1] in LEFT_ENDINGS:", "    if reasons and reasons[-1] in LEFT_ENDINGS:", "test_a_seen_ending_is_not_relabelled"),
    ("A", "\"menu_seen\": \"Returned to lobby\"", "\"menu_seen\": \"Player quit\"", "test_leaving_never_claims_why"),
    # the type
    ("C", "    return CHEST_LABELS.get(ev.get(\"chest_type\"), \"Unknown chest\")", "    return CHEST_LABELS.get(ev.get(\"chest_type\"), \"Regular chest\")", "test_an_unread_type_is_never_guessed"),
    ("C", "    if not (ev.get(\"certain_counted\") or ev.get(\"approx_counted\")):\n        return \"\"\n    return CHEST_LABELS", "    return CHEST_LABELS", "test_what_was_not_counted_has_no_type"),
    ("C", "\"evidence\": _evidence(ev), \"chest_label\": type_label(ev),", "\"evidence\": _evidence(ev),", "test_the_app_message_carries_it"),
    ("C", "(f\"{type_label(ev)}, \" if type_label(ev) else \"\") + _evidence(ev)", "_evidence(ev)", "test_the_terminal_shows_it_too"),
    # the default
    ("S", "\"mode\": \"on\",  ", "\"mode\": \"off\", ", "test_a_new_install_tracks_matches"),
    # the window
    ("G", "        known = match.get(\"english_confirmed\") is True and chests is not None\n", "        known = chests is not None\n", "test_an_unconfirmed_match_shows_no_numbers"),
    ("G", "        self.game_approx.set_value(chests[\"approx\"] if known else None)\n", "        self.game_approx.set_value(chests[\"approx\"] if known else 0)\n", "test_no_match_shows_dashes_not_zeros"),
    ("G", "        self.game_approx.set_value(chests[\"approx\"] if known else None)\n", "        self.game_approx.set_value(self.win.counts[1])\n", "test_the_game_shows_this_matchs_numbers_not_the_totals"),
    ("G", "    if match.get(\"observed_from_start\") is False:\n        return \"Since the app joined this match\"\n", "", "test_a_late_join_says_so"),
    ("G", "    if match.get(\"discontinuity\"):\n        return \"Part of this match was not seen\"\n", "", "test_a_break_says_so"),
    ("G", "                tile.set_value(None, \"No video right now\")", "                pass", "test_stalled_video_stops_the_rate_but_keeps_the_count"),
    ("G", "            d.game_last.setText(\"\")\n            d.game_last.hide()\n", "", "test_stopping_clears_the_match"),
    ("G", "    if not last[\"approx\"] and active < match_analytics.MIN_MATCH_RATE_SECONDS:\n        return \"\"\n", "", "test_a_weak_record_does_not_replace_the_last_match"),
    ("G", "    return f\"{match.rate.approx_per_minute:.2f}\" + (\"\" if match.quality == \"complete\" else \" seen\")", "    return f\"{match.rate.approx_per_minute:.2f}\"", "test_the_table_shows_the_rate_and_marks_partial"),
    ("G", "if not d.show_preview.isChecked() or self.isMinimized() or self.pages.currentWidget() is not d:", "if not d.show_preview.isChecked() or self.isMinimized():", "test_another_page_stops_the_preview"),
    ("G", "if not d.show_preview.isChecked() or self.isMinimized() or self.pages.currentWidget() is not d:", "if not d.show_preview.isChecked() or self.pages.currentWidget() is not d:", "test_minimising_stops_the_preview"),
    ("G", "if not d.show_preview.isChecked() or self.isMinimized() or self.pages.currentWidget() is not d:", "if self.isMinimized() or self.pages.currentWidget() is not d:", "test_hiding_it_stops_it_without_stopping_counting"),
    ("G", "return {OVERVIEW_VIEW: d.mini_preview, GAME_VIEW: d.preview}.get(d.views.currentIndex())", "return d.preview", "test_only_the_visible_preview_is_active"),
    ("G", "            panel.show_frame(width, height, data)", "            d = self.dashboard\n            d.preview.show_frame(width, height, data)\n            d.mini_preview.show_frame(width, height, data)", "test_a_picture_goes_only_to_the_visible_preview"),
    ("G", "            self.analytics.refresh()\n        self.preview_visibility_changed()\n", "            self.analytics.refresh()\n", "test_another_page_stops_the_preview"),
    ("G", "        if event.type() == QEvent.WindowStateChange and hasattr(self, \"dashboard\"):\n            self.preview_visibility_changed()", "        if False:\n            pass", "test_a_minimise_event_is_noticed"),
    ("G", "        link_help_showing = (self.source.currentData() or {}).get(\"source\") == \"stream\" and not counting", "        link_help_showing = False", "test_the_overview_preview_makes_room_for_the_link_help_until_counting"),
    ("G", "        d.url_note.setVisible(not running)\n", "", "test_the_overview_preview_makes_room_for_the_link_help_until_counting"),
    ("G", "        self.source.currentIndexChanged.connect(lambda _: self._panels())\n", "", "test_another_source_shows_the_preview_box_before_counting"),
    ("G", "self.view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)", "self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)", "test_the_picture_cannot_make_the_page_longer"),
    ("G", "        self.win.remember_preview(on)\n", "", "test_the_choice_is_remembered"),
    ("G", "        self.dashboard.set_preview_on(load_cfg()[0][\"app\"][\"show_preview\"])\n", "        self.dashboard.set_preview_on(True)\n", "test_the_choice_is_remembered"),
    ("G", "        for toggle in (self.show_preview, self.show_mini):\n", "        for toggle in (self.show_preview,):\n", "test_the_two_buttons_are_one_setting"),
    ("G", "        for preview in (self.dashboard.preview, self.dashboard.mini_preview):\n", "        for preview in (self.dashboard.preview,):\n", "test_a_message_reaches_both_panels"),
    ("G", "            for panel in (d.preview, d.mini_preview):\n                panel.view.setStyleSheet(\"\")", "            for panel in (d.preview,):\n                panel.view.setStyleSheet(\"\")", "test_stopping_clears_both_panels"),
    ("G", "    tile.value.setText(UNKNOWN_VALUE if rate is None else f\"{rate.approx_per_minute:.2f}\")", "    tile.value.setText(UNKNOWN_VALUE if rate is None else f\"{rate.certain_per_minute:.2f}\")", "test_the_headline_is_the_fuller_rate_with_approx_first"),
    ("G", "still in progress: left out of the match count, match time and chests per minute until it ends.", "not finished yet, so not counted.", "test_an_unfinished_match_says_what_it_is_left_out_of"),
    ("G", "        kind_of_chest = f\"{_pad(message['chest_label'], 15)}\" if message.get(\"chest_label\") else \"\"\n", "        kind_of_chest = \"\"\n", "test_the_activity_log_shows_it_and_keeps_the_evidence"),
]


def main():
    caught = 0
    originals = {"T": real_tracker, "A": real_analytics, "C": real_console, "S": real_settings, "G": real_app}
    owners = {"T": [(package, "match_tracker")], "A": [(package, "match_analytics"), (real_app, "match_analytics")], "C": [(package, "console")], "S": [(L, "settings")], "G": [(gui_package, "app")]}
    for number, (name, old, new, test_name) in enumerate(MUTATIONS, 1):
        original = originals[name]
        source = Path(original.__file__).read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"mutation {number} no longer applies; review this check")
        mutant = types.ModuleType(original.__name__ + "_mutated")
        mutant.__file__, mutant.__package__ = original.__file__, original.__package__
        sys.modules[mutant.__name__] = mutant
        exec(compile(source.replace(old, new, 1), original.__file__, "exec"), mutant.__dict__)
        targets = list(owners[name])
        if name == "T":
            targets.append((L.T, "MT"))
        patches = [patch.object(owner, attribute, mutant) for owner, attribute in targets]
        for item in patches:
            item.start()
        try:
            getattr(L, test_name)()
        except (AssertionError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration) as error:
            caught += 1
            print(f"caught {number:02d}: {test_name} ({type(error).__name__})", flush=True)
        else:
            print(f"SURVIVED {number:02d}: {name}: {test_name}", flush=True)
        finally:
            for item in patches:
                item.stop()
    print(f"{caught}/{len(MUTATIONS)} live match mutations caught")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
