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
        # Pirate Shop Access and the gold outfit first and full width, then the rest from the rarest down
        assert list(page.cards) == ["pirate_shop_access", "weekly_gold_outfit", "weekly_vehicle_decal", "weekly_pickaxe_backbling",
                                    "weekly_jam_track", "weekly_loading_screen", "gizmo"]
        assert page.cards["pirate_shop_access"].featured and page.cards["weekly_gold_outfit"].featured and not page.cards["gizmo"].featured
        assert len({c.accent for c in page.cards.values()}) == 7                                  # every reward its own colour


def test_my_progress_shows_the_profiles_chests_pace_and_odds():
    with G.window() as w:
        play(w)
        page = opened(w)
        assert page.recorded_tile.value.text() == "70" and page.season_tile.value.text() == "70" and page.week_tile.value.text() == "70"
        assert page.added_tile.value.text() == "0" and "60 chests per hour" in page.pace_line.text()
        gizmo = card(page, "gizmo")
        assert gizmo.chance.text() == R.percent(R.chance(70, 1 / 127)) and "70 of 292 chests to the 90% mark" in gizmo.bar_text.text()
        assert gizmo.rows[0.5][2].text() == "18 more chests" and gizmo.rows[0.5][1].text() == "18 min" and gizmo.forecast.isHidden()
        assert gizmo.forecast_caption.text() == "TIME AT YOUR PACE" and "0 completed 90% cycles" in gizmo.stats.text()
        assert gizmo.obtained.isHidden() and gizmo.luck.level == R.CYCLE
        pirate = card(page, "pirate_shop_access")
        assert pirate.chance.text() == "0.05%" and pirate.luck.heading.text() == "Still early" and "THIS SEASON" in pirate.chance_sub.text()
        weekly = card(page, "weekly_loading_screen")
        assert "Week 1 of 5" in weekly.status.text() and "THIS WEEK" in weekly.chance_sub.text()


def test_a_team_models_every_card_and_solo_restores_your_own_view():
    with G.window() as w:
        play(w)
        page = opened(w)
        solo = {rid: c.chance.text() for rid, c in page.cards.items()}
        page.team.button(4).click()
        squad = {rid: c.chance.text() for rid, c in page.cards.items()}
        assert all(squad[rid] != solo[rid] for rid in solo), (solo, squad)                       # every card's percentage moves
        p = 1 / 137500
        pirate, gizmo = card(page, "pirate_shop_access"), card(page, "gizmo")
        assert pirate.chance.text() == R.percent(R.chance(70 * 3.4, p)) and "SQUAD MODEL" in pirate.chance_sub.text()
        assert not pirate.actual.isHidden() and pirate.actual.text().startswith(f"Yours: {R.percent(R.chance(70, p))} from 70 chests")
        assert pirate.rows[0.9][1].text() == R.short_hours(R.more_to(0.9, p, 70 * 3.4) / (60 * 3.4))   # needed from the model, team pace
        assert "238 of 316,605 team chests" in pirate.bar_text.text() and gizmo.luck.text.text().startswith("Squad model:")
        assert "Squad model: 238" in page.season_tile.sub.text() and page.season_tile.value.text() == "70"   # your actual total stays
        assert not (folder(w) / R.ACTIONS_FILE).exists()                                         # a scenario saves nothing
        page.roll_team.button(2).click()                                                        # What If?: a team changes only the time
        assert "counts 3.4x your chests" in page.team_line.text() and "only the time changes" in page.roll_team_line.text()
        page.team.button(1).click()
        assert {rid: c.chance.text() for rid, c in page.cards.items()} == solo and pirate.actual.isHidden()


def test_the_curve_shows_your_position_and_the_teams():
    from unittest.mock import patch
    with G.window() as w:
        play(w)
        page = opened(w)
        page.team.button(3).click()
        seen = {}

        def show(dialog):
            seen.update(you=dialog.chart.you, team=dialog.chart.team_you, label=dialog.chart.team_label, mine=dialog.mine.text())
            return 0

        with patch.object(w.A.CurveDialog, "exec", show):
            card(page, "weekly_jam_track").curve_link.click()
        assert seen["you"] == 70 and abs(seen["team"] - 70 * 2.6) < 1e-9 and seen["label"] == "Trio" and "Trio model (the ring)" in seen["mine"]


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
        assert weekly.luck.level in (R.VERY_LUCKY, R.LUCKY, R.TYPICAL, R.LATE)
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
        assert not page.roll_verdict.isHidden() and page.roll_verdict.level in (R.VERY_LUCKY, R.LUCKY, R.TYPICAL, R.UNLUCKY, R.TERRIBLE)
        assert page.roll_verdict.text.text().startswith("This time it took ")
        page.roll_team.button(4).click()
        page.roll_boost.setCurrentIndex(page.roll_boost.findData(2.0))
        assert "about 1 in 68,750 at 2x" in page.odds_facts.text() and not page.boost_badge.isHidden() and "47,654" in page.boost_badge.text()
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
        assert page.added_tile.value.text() == "+5,000" and page.season_tile.value.text() == "5,070" and page.week_tile.value.text() == "70"
        assert "count for season rewards" in page.added_line.text() and "not for any week's rewards" in page.added_line.text()
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
        assert "Take the difference back" in seen["text"] and seen["choice"] == (-1070, R.SEASON, None, POOL.id, None)


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


def test_outside_a_season_edit_counts_counts_nothing_unless_you_choose_one():
    with G.window() as w:
        page = w.win.predictions
        page.clock = lambda: POOL.end + timedelta(days=3)
        info = page.edit_info()
        assert info["default"] is None and [p.id for p in info["pools"]] == [POOL.id]
        dialog = w.A.CountsDialog(w.win, 0, 0, prediction=info)
        dialog.approx.setValue(300)
        assert not dialog.predict_box.isHidden() and not dialog.predict.isChecked() and dialog.prediction_choice() is None
        assert not dialog.when.button(1).isEnabled()                                            # no current week in a season that is over
        none = w.A.CountsDialog(w.win, 0, 0, prediction=None)
        none.approx.setValue(300)
        assert none.predict_box.isHidden() and none.prediction_choice() is None


def test_edit_counts_asks_optionally_for_the_season_and_the_period():
    from PySide6.QtCore import QDate
    with G.window() as w:
        play(w)
        page = opened(w)
        info = page.edit_info()
        assert info["default"] == POOL.id and info["info"][POOL.id]["recorded"] == 70 and info["info"][POOL.id]["week"] == 0
        d = w.A.CountsDialog(w.win, 70, 70, prediction=info)
        d.approx.setValue(5070)
        assert d.predict.isChecked() and d.season.currentData() == POOL.id and d.when.button(0).isChecked()   # default: period not known
        assert d.prediction_choice() == (5000, R.SEASON, None, POOL.id, None)
        assert d.when.button(1).isEnabled() and not d.when.button(2).isEnabled()                 # week 1: no previous week
        d.when.button(1).click()
        assert d.prediction_choice() == (5000, R.WEEK, 0, POOL.id, "2026-11-01")
        d.when.button(4).click()
        d.date_pick.setDate(QDate(2026, 11, 3))
        assert "week 1" in d.date_found.text() and d.prediction_choice() == (5000, R.WEEK, 0, POOL.id, "2026-11-01")
        d.date_pick.setDate(QDate(2026, 10, 1))
        assert "No installed season" in d.date_found.text() and d.prediction_choice() is None    # never guessed
        d.when.button(3).click()
        assert d.period_pick.count() == 1 and d.prediction_choice() == (5000, R.WEEK, 0, POOL.id, "2026-11-01")
        from unittest.mock import patch
        with patch.object(w.A.CountsDialog, "exec", lambda dialog: (dialog.approx.setValue(5070), dialog.when.button(1).click(),
                                                                   w.A.QDialog.Accepted)[-1]):
            w.win.edit_counts()
        rows, _ = R.read_actions(folder(w))
        assert [(a.kind, a.delta, a.scope, a.week, a.period, a.pool) for a in rows] == [(R.ADJUST, 5000, R.WEEK, 0, "2026-11-01", POOL.id)]


def test_every_card_opens_its_probability_curve():
    with G.window() as w:
        play(w)
        page = opened(w)
        seen = {}

        def show(dialog):
            seen[dialog.chart.p] = (dialog.chart.end, dialog.chart.you, [t.value.text() for t in dialog.tiles], dialog.explain.text(), dialog.mine.text())
            return 0

        from unittest.mock import patch
        with patch.object(w.A.CurveDialog, "exec", show):
            for reward_card in page.cards.values():
                reward_card.curve_link.click()
        assert len(seen) == 7
        end, you, tiles, explain, mine = seen[1 / 127]
        assert end == 1166 and you == 70 and tiles == ["88", "292", "583"]
        assert "about 63 find at least one" in explain and "about 37 find none" in explain and "70 chests in this cycle" in mine
        end, you, tiles, *_ = seen[1 / 1562500]
        assert tiles == ["1,083,043", "3,597,789", "7,195,577"] and you == 70


def test_assigning_added_chests_to_weeks_changes_predictions_only():
    from unittest.mock import patch
    from fortnite_chest_counter import progression as P
    with G.window() as w:
        play(w)
        R.append_action(folder(w), R.ADJUST, POOL.id, "", delta=5000, scope=R.SEASON, at=NOW - timedelta(hours=1))
        page = opened(w)
        before = P.load(folder(w), now=NOW).progress("all")
        assert not page.assign_link.isHidden() and page.week_tile.value.text() == "70"

        def assign(dialog):
            assert list(dialog.spins) == [0]                                # only weeks that have begun
            dialog.spins[0].setValue(6000)
            capped = dialog.spins[0].value()                                 # one week can never hold more than was added
            dialog.spins[0].setValue(3000)
            seen.update(capped=capped, summary=dialog.summary.text())
            return w.A.QDialog.Accepted

        seen = {}
        with patch.object(w.A.AllocationDialog, "exec", assign):
            page.assign_link.click()
        settle(page)
        assert seen["capped"] == 5000 and "Assigned: 3,000" in seen["summary"] and "Not assigned: 2,000" in seen["summary"]
        later = w.A.AllocationDialog(page, POOL, page._view, POOL.rotations[0] + timedelta(days=1))      # in week 2: two weeks to fill
        later.spins[0].setValue(4000)
        later.spins[1].setValue(4000)
        assert not later.buttons.button(w.A.QDialogButtonBox.Save).isEnabled() and "more than you added" in later.summary.text()
        assert page.week_tile.value.text() == "3,070" and page.season_tile.value.text() == "5,070"       # this week: 70 + 3,000
        assert card(page, "weekly_jam_track").chance.text() == R.percent(R.chance(3070, 1 / 391))
        assert "Assigned to weeks: 3,000" in page.added_line.text()
        after = P.load(folder(w), now=NOW).progress("all")
        assert (before.totals, before.in_sessions, before.per_hour) == (after.totals, after.in_sessions, after.per_hour)   # Analytics: unchanged
        assert w.win.counts == (0, 0)                                                                     # the counter: unchanged
        page.added_undo.click()
        settle(page)
        assert page.week_tile.value.text() == "70" and page.season_tile.value.text() == "5,070"


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
