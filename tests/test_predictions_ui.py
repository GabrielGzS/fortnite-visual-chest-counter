"""
The v0.5.0 Predictions page: its place in the sidebar, My Progress from the active profile's history, Start new cycle / Mark obtained /
Undo saved to that profile only, the team scenario, live updates while counting, What If? rolls (never saved), and the smallest window.

Run:   python tests/test_predictions_ui.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import itertools
import os
import random
import subprocess
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import predictions as R
from fortnite_chest_counter import profiles

import history_fixtures as F
import test_update_gui as G

POOL = R.load_pool()
NOW = POOL.start + timedelta(days=3, hours=5)       # inside week 1 of the pool


def folder(w, profile="default"):
    return w.dir / "state" / "history" / profile


def play(w, profile="default"):
    """A 70-minute session on day 2 of the pool: 70 chests, one a minute."""
    rec = F.Recorder(folder(w, profile))
    rec.run(POOL.start + timedelta(days=2)).chests(*range(30, 4200, 60)).end(4200)
    return rec


def opened(w):
    page = w.win.predictions
    page_now(page)
    w.win.show_page(page)
    settle(page)
    return page


def page_now(page):
    """Pin the page's clock inside the pool, a second further at each look, so these checks do not depend on today's date."""
    ticks = itertools.count()
    page.clock = lambda: NOW + timedelta(seconds=next(ticks))


def settle(page):
    if page._thread is not None:
        page._thread.join(30)
    page._collect()


def card(page, rid):
    return page.cards[rid]


def test_predictions_is_its_own_page_after_analytics_with_two_tabs():
    with G.window() as w:
        assert [w.win.nav.item(i).text() for i in range(w.win.nav.count())][:3] == ["Dashboard", "Analytics", "Predictions"]
        page = w.win.predictions
        assert w.win.pages.widget(2) is page and [page.view_buttons.button(i).text() for i in range(2)] == ["My Progress", "What If?"]
        assert list(page.cards) == [r.id for r in POOL.rewards]


def test_my_progress_shows_the_profiles_chests_pace_and_odds():
    with G.window() as w:
        play(w)
        page = opened(w)
        assert "70 chests counted this season" in page.chests_line.text() and "60 chests per hour" in page.pace_line.text()
        gizmo = card(page, "gizmo")
        assert gizmo.chance.text() == R.percent(R.chance(70, 1 / 127)) and "70 of 292 chests to the 90% mark" in gizmo.bar_text.text()
        assert "50% in 18 more chests" in gizmo.forecast.text() and "0 completed 90% cycles" in gizmo.stats.text()
        assert gizmo.obtained.isHidden() and "In this cycle" in gizmo.insight.text()
        pirate = card(page, "pirate_shop_access")
        assert pirate.chance.text() == "0.05%" and "Still early" in pirate.insight.text() and "this season" in pirate.chance_sub.text()
        weekly = card(page, "weekly_loading_screen")
        assert "Week 1 of 5" in weekly.status.text() and "this week" in weekly.chance_sub.text()


def test_the_team_scenario_changes_only_the_time():
    with G.window() as w:
        play(w)
        page = opened(w)
        pirate = card(page, "pirate_shop_access")
        chance, solo = pirate.chance.text(), pirate.forecast.text()
        page.team.button(4).click()
        assert pirate.chance.text() == chance and pirate.forecast.text() != solo and "more chests" in pirate.forecast.text()


def test_start_new_cycle_mark_obtained_and_undo_are_saved_to_this_profile_only():
    with G.window() as w:
        play(w)
        other = profiles.create(w.dir / "state" / "chest_state.json", "Streamer", activate=False)["id"]
        page = opened(w)
        weekly = card(page, "weekly_jam_track")
        weekly.obtained.click()
        settle(page)
        actions, _ = R.read_actions(folder(w))
        assert [a.kind for a in actions] == [R.OBTAINED] and not (folder(w, other) / R.ACTIONS_FILE).exists()
        assert "Reported obtained" in weekly.status.text() and weekly.obtained.isHidden() and not weekly.undo.isHidden()
        assert weekly.insight.text().startswith(("Lucky find", "Right around", "A long hunt"))
        weekly.undo.click()
        settle(page)
        assert "Reported obtained" not in weekly.status.text() and not weekly.obtained.isHidden() and weekly.undo.isHidden()
        gizmo = card(page, "gizmo")
        gizmo.restart.click()
        settle(page)
        assert "New cycle since" in gizmo.status.text() and not gizmo.undo.isHidden()
        assert len(R.read_actions(folder(w))[0]) == 3


def test_a_counted_chest_refreshes_the_page_only_while_it_is_open():
    with G.window() as w:
        page = opened(w)
        page.chest_counted()
        assert page._live.isActive()
        page._live.stop()
        w.win.show_page(w.win.dashboard)
        page.chest_counted()
        assert not page._live.isActive()


def test_what_if_rolls_are_random_first_drops_and_never_saved():
    with G.window() as w:
        play(w)
        page = opened(w)
        page.show_view(1)
        page.rng = random.Random(5)
        page.roll_reward.setCurrentIndex(page.roll_reward.findData("pirate_shop_access"))
        assert "1 in 137,500" in page.odds_facts.text() and "95,308" in page.odds_facts.text()
        page.roll_button.click()
        assert page.roll_result.text().endswith(" chests") and page.roll_count.text() == "Rolls: 1"
        assert "You found it on your own" in page.roll_detail.text() and "at your pace" in page.roll_detail.text()
        assert page.roll_verdict.text().startswith(("Luckier", "Unluckier"))
        page.roll_team.button(4).click()
        page.roll_boost.setCurrentIndex(page.roll_boost.findData(2.0))
        assert "about 1 in 68,750 at 2x" in page.odds_facts.text()
        page.roll_button.click()
        assert page.roll_count.text() == "Rolls: 2" and "with 4 players" in page.roll_detail.text()
        assert not (folder(w) / R.ACTIONS_FILE).exists()


def test_edit_counts_adds_the_difference_to_predictions_only_and_undo_takes_it_back():
    from unittest.mock import patch
    from fortnite_chest_counter import progression as P
    with G.window() as w:
        play(w)
        page = opened(w)
        before = P.load(folder(w), now=NOW).progress("all")
        seen = {}

        def accept(dialog):
            dialog.approx.setValue(5070)                                   # 70 counted + 5,000 opened before the app (the counter showed 0)
            seen.update(shown=not dialog.predict_box.isHidden(), note=dialog.predict_note.text(), last_week=dialog.when.button(2).isEnabled())
            return w.A.QDialog.Accepted

        with patch.object(w.A.CountsDialog, "exec", accept):
            w.win.edit_counts()
        settle(page)
        assert seen["shown"] and "+5,000 chests for season rewards" in seen["note"] and "will use 5,070 chests" in seen["note"]
        assert not seen["last_week"]                                                                             # week 1: no last week
        assert w.win.counts == (0, 5070)                                                                         # the counter is set as always
        rows, _ = R.read_actions(folder(w))
        assert [(a.kind, a.delta, a.scope) for a in rows] == [(R.ADJUST, 5000, R.SEASON)]
        after = P.load(folder(w), now=NOW).progress("all")
        assert (before.totals, before.in_sessions, before.per_hour) == (after.totals, after.in_sessions, after.per_hour)   # Analytics: unchanged
        assert "+5,000 chests you added" in page.added_line.text() and "5,070 chests for season rewards" in page.added_line.text()
        assert card(page, "pirate_shop_access").chance.text() == R.percent(R.chance(5070, 1 / 137500))
        assert card(page, "weekly_jam_track").chance.text() == R.percent(R.chance(70, 1 / 391))                # no week known: not this week's
        assert "60 chests per hour" in page.pace_line.text()                                                    # pace: counted chests only
        page.added_undo.click()
        settle(page)
        assert "Add them with Edit counts" in page.added_line.text() and page.added_undo.isHidden()

        def lower(dialog):
            dialog.approx.setValue(4000)
            seen.update(text=dialog.predict.text(), choice=dialog.prediction_choice())
            return w.A.QDialog.Accepted

        R.append_action(folder(w), R.ADJUST, POOL.id, "", delta=2000, scope=R.SEASON, at=NOW)
        with patch.object(w.A.CountsDialog, "exec", lower):
            w.win.edit_counts()
        assert "Take the difference back" in seen["text"] and seen["choice"] == (-1070, R.SEASON, None)


def test_reset_and_typing_the_total_back_in_adds_nothing_even_with_the_page_closed():
    """The page's last read is cached; what was added must be read again, or a reset and re-entry would count 5,000 chests twice."""
    from unittest.mock import patch
    with G.window() as w:
        play(w)
        opened(w)                                                          # a cached view: nothing added yet
        w.win.show_page(w.win.dashboard)

        def to(total):
            def accept(dialog):
                dialog.approx.setValue(total)
                return w.A.QDialog.Accepted
            return accept

        with patch.object(w.A.CountsDialog, "exec", to(5070)):
            w.win.edit_counts()
        w.win._set(0, 0, "reset")
        with patch.object(w.A.CountsDialog, "exec", to(5070)):
            w.win.edit_counts()
        rows, _ = R.read_actions(folder(w))
        assert [(a.kind, a.delta) for a in rows] == [(R.ADJUST, 5000)] and w.win.counts == (0, 5070)


def test_outside_the_season_edit_counts_has_no_predictions_part():
    with G.window() as w:
        page = w.win.predictions
        page.clock = lambda: POOL.end + timedelta(days=3)
        assert page.edit_info() is None
        dialog = w.A.CountsDialog(w.win, 0, 0, prediction=None)
        dialog.approx.setValue(300)
        assert dialog.predict_box.isHidden() and dialog.prediction_choice() is None


FIT_CHECK = """
import os, sys
root = sys.argv[1]
for name in ("src", "tests"):
    sys.path.insert(0, os.path.join(root, name))
import test_predictions_ui as T
import test_update_gui as G
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

with G.window() as w:
    win = w.win
    w.qt.setStyle("Fusion")
    w.qt.setStyleSheet(w.A.theme.STYLE)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    T.play(w)
    page = T.opened(w)
    for width, height in ((1120, 800), (920, 640)):
        win.resize(width, height)
        for index in range(2):
            page.show_view(index)
            w.qt.processEvents()
            area = page.views.currentWidget()
            assert isinstance(area, QScrollArea)
            inner = area.widget()
            assert inner.width() <= area.viewport().width() + 1, (width, index, inner.width(), area.viewport().width())
print("fits")
"""


def test_both_tabs_fit_the_smallest_window_without_scrolling_sideways():
    """In its own process with real fonts: the off-screen platform has none, so text there is the wrong size."""
    if os.name != "nt":
        return
    result = subprocess.run([sys.executable, "-c", FIT_CHECK, str(ROOT)], capture_output=True, text=True, cwd=ROOT,
                            env=dict(os.environ, QT_QPA_PLATFORM="windows"), timeout=180)
    assert result.returncode == 0 and "fits" in result.stdout, (result.stdout[-400:], result.stderr[-800:])


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}", flush=True)
        except Exception:
            failed += 1
            import traceback
            print(f"  FAIL  {name}", flush=True)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} Predictions page checks passed")
    sys.exit(1 if failed else 0)
