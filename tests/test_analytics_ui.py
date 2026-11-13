"""
The v0.4.0 Analytics page and Game status (M4-M7, M10): four tabs, the period choice, one scroller at a time in History (UX-04), a new match
brought into view and nothing else moving the list (UX-06), a refresh when a match ends while the page is open (UX-07), Days & weeks,
Personal Bests, sessions, where chests came from, and the calmer Partial status (UX-05).

Histories are dated relative to one fixed "now", the last local noon, and the page reads the same clock (see ANCHOR).

Run:   python tests/test_analytics_ui.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import os
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import match_analytics as A
from fortnite_chest_counter import match_history as H
from fortnite_chest_counter import progression as P
from fortnite_chest_counter import timeline as TL

import history_fixtures as F
import test_match_analytics as MA
import test_update_gui as G
import test_match_ui as U

UTC = timezone.utc
DASH = "—"


def _last_local_noon():
    local = datetime.now().astimezone()
    noon = local.replace(hour=12, minute=0, second=0, microsecond=0)
    return (noon if noon <= local else noon - timedelta(days=1)).astimezone(UTC)


# The fixtures place runs "3 days and 2 hours ago" and "30 minutes ago". Run between 00:00 and about 02:00, those crossed local midnight
# and the day charts got an extra day (v0.4.1: failed at 01:42, also on untouched v0.4.0). So "now" is the last local noon, for these
# fixtures and for the two modules the Analytics page takes the time from.
ANCHOR = _last_local_noon()


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return ANCHOR.astimezone(tz) if tz is not None else ANCHOR.astimezone().replace(tzinfo=None)


_CLOCKS = [patch.object(TL, "datetime", _FrozenDatetime), patch.object(P, "datetime", _FrozenDatetime)]


def setup_module(module=None):
    """Only while these checks run: pytest runs every test file in one process, and other files read the real clock."""
    for clock in _CLOCKS:
        clock.start()


def teardown_module(module=None):
    for clock in _CLOCKS:
        clock.stop()


def now():
    return ANCHOR


def history(w):
    return F.Recorder(w.dir / "state" / "history" / "default", zone=None)


class LocalRecorder(F.Recorder):
    """Rows dated in the PC's own zone, as the app writes them."""

    def iso(self):
        return self.clock.astimezone().isoformat(timespec="milliseconds")


def recorder(w):
    return LocalRecorder(w.dir / "state" / "history" / "default")


def today_and_three_days_ago(w):
    """Today: 3 chests in a 20-minute run that started 30 minutes ago. Three days ago: 5 chests and a broken-chest +1 in a 70-minute run."""
    rec = recorder(w)
    rec.run(now() - timedelta(days=3, hours=2)).chests(60, 120, 180, 240, 300).match(1, opened=30, played=50, closed=1500, active=1300, ended=1450).end(4200)
    rec.correction(now() - timedelta(days=3, hours=1, minutes=30), 1, H.BROKEN_CHEST)
    rec.run(now() - timedelta(minutes=30)).chests(60, 120, 180).end(1200)
    return rec


def opened(w):
    page = w.win.analytics
    w.win.show_page(page)
    MA.settle(w)
    return page


def period(page, key):
    page.period_buttons.button([k for k, _ in __import__("fortnite_chest_counter.progression", fromlist=["PERIODS"]).PERIODS].index(key)).click()


# ------------------------------------------------------------------ the tabs

def test_four_tabs_and_performance_first():
    with G.window() as w:
        page = w.win.analytics
        names = [page.view_buttons.button(i).text().replace("&&", "&") for i in range(4)]
        assert names == ["Performance", "Days & weeks", "Personal Bests", "History"] and page.views.currentIndex() == 0
        page.show_view(3)
        assert page.views.currentIndex() == 3 and page.view_buttons.button(3).isChecked()


def test_the_period_choice_changes_performance():
    with G.window() as w:
        today_and_three_days_ago(w)
        page = opened(w)
        assert page.approx.value.text() == "9" and "1 broken" not in page.approx.sub.text() and "+1 manual" in page.approx.sub.text()
        period(page, "today")
        assert page.approx.value.text() == "3" and page.session_time.value.text() == "20m 00s" and page.hour_rate.value.text() == DASH
        assert "Needs 30 minutes" in page.hour_rate.sub.text()
        period(page, "all")
        assert page.hour_rate.value.text() != DASH and "breaks included" in page.hour_rate.sub.text()


def test_a_period_with_nothing_counted_shows_dashes_not_zeros():
    with G.window() as w:
        recorder(w).run(now() - timedelta(days=20)).chests(60).end(600)
        page = opened(w)
        period(page, "week")
        assert page.approx.value.text() == DASH and page.session_time.value.text() == DASH and page.hour_rate.sub.text() == "Not counted in this period"


# ------------------------------------------------------------------ History: one scroller, the newest match in view

def test_history_has_one_scroller():
    from PySide6.QtWidgets import QAbstractScrollArea, QScrollArea
    with G.window() as w:
        page = w.win.analytics
        history_tab = page.views.widget(3)
        assert not history_tab.findChildren(QScrollArea) and not isinstance(history_tab, QScrollArea)
        parent = page.table.parent()
        while parent is not None:
            assert not isinstance(parent, QScrollArea), parent
            parent = parent.parent()
        for index in range(3):                                     # the other tabs scroll as one page, with no scroller inside
            tab = page.views.widget(index)
            assert isinstance(tab, QScrollArea) and not tab.widget().findChildren(QAbstractScrollArea)


def fake_matches(numbers):
    return [A.RecentMatch(None, 600.0, True, 1, 2, False, "complete", False, "Placed", "run", n) for n in numbers]


def test_a_new_match_comes_into_view_and_nothing_else_moves_the_list():
    from PySide6.QtCore import Qt
    with G.window() as w:
        page = w.win.analytics
        w.win.setAttribute(Qt.WA_DontShowOnScreen, True)
        w.win.show()
        w.win.resize(1120, 800)
        w.win.show_page(page)
        page.show_view(3)
        bar = page.table.verticalScrollBar()
        page._fill_table(fake_matches(range(60, 0, -1)))
        w.qt.processEvents()
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        page._fill_table(fake_matches(range(60, 0, -1)))          # a refresh, a correction or the checkbox: same newest match
        w.qt.processEvents()
        assert bar.value() == bar.maximum() > 0
        page._fill_table(fake_matches(range(61, 0, -1)))          # a genuinely new match
        w.qt.processEvents()
        assert bar.value() == 0


def ended(number):
    """A match status message whose last closed match is `number`."""
    return {**U.status("IN_MATCH", U.match()), "chests": {"certain": 0, "approx": 0},
            "last_match": {"match_number": number, "completion": "complete", "ended_by": "placed", "reasons": [], "active_seconds": 600,
                           "english_confirmed": True, "certain": 1, "approx": 2}}


def test_a_match_ending_refreshes_the_page_only_while_it_is_open():
    with G.window(config='[match]\nmode = "on"\n') as w:
        page = w.win.analytics
        w.win.mode = "counting"
        w.win.session_match_mode = "on"
        with patch.object(page, "refresh") as refresh:
            w.win.show_page(w.win.dashboard)
            w.win.show_match(ended(1))
            assert not page._auto_refresh.isActive()
            w.win.show_page(page)
            refresh.reset_mock()
            w.win.show_match(ended(2))
            assert page._auto_refresh.isActive()
            page._auto_refresh.timeout.emit()
            assert refresh.call_count == 1
            refresh.reset_mock()
            w.win.show_match(ended(2))
            page._auto_refresh.stop()
            assert refresh.call_count == 0                         # the same match again is no news


# ------------------------------------------------------------------ Days & weeks, Personal Bests, sessions, sources

def test_days_and_weeks_tell_counted_from_not_counted():
    with G.window() as w:
        today_and_three_days_ago(w)
        page = opened(w)
        assert page.today.value.text() == "3" and page.yesterday.value.text() == DASH and page.yesterday.sub.text() == "Not counted"
        statuses = [bar.status for bar in page.day_chart.bars]
        assert statuses[-1] == "chests" and statuses[-2] == "not_counted" and statuses[0] == "chests" and len(statuses) == 4
        assert page.per_calendar.value.text() == "2.0" and "2 not counted" in page.per_calendar.sub.text()   # 6 chests over 3 completed days
        assert page.per_monitored.value.text() == "6.0" and page.best_day.value.text() == "6"


def test_personal_bests_show_their_evidence_or_what_they_need():
    with G.window() as w:
        today_and_three_days_ago(w)
        page = opened(w)
        cards = page.best_cards
        assert cards["day"].value.text() == "6" and cards["session"].value.text() == "6" and cards["match_chests"].value.text() == "5"
        assert "Complete" in cards["match_chests"].detail.text() and cards["hour"].value.text() == "6" and "incl. +1 manual" in cards["hour"].detail.text()
        assert cards["match_broken"].value.text() == DASH and cards["match_broken"].when.text().startswith("Needs:")


def test_sessions_are_listed_newest_first():
    with G.window() as w:
        today_and_three_days_ago(w)
        page = opened(w)
        table = page.sessions_table
        assert table.rowCount() == 2 and table.item(0, 3).text() == "3" and table.item(1, 3).text() == "6" and table.item(1, 5).text() == "+1 manual"


def test_where_chests_came_from():
    with G.window() as w:
        today_and_three_days_ago(w)
        page = opened(w)
        assert page.detected.value.text() == "8" and page.broken.value.text() == "1" and page.missed.value.text() == "0" and page.removed.value.text() == "0"
        assert "% of your chests" in page.broken.sub.text()


# ------------------------------------------------------------------ the Game view's status (UX-05)

def test_partial_is_a_small_note_not_a_large_warning():
    from fortnite_chest_counter.gui import app as APP
    from fortnite_chest_counter.gui import theme
    state, color, note, note_color = APP.game_status_parts("In match, 12:34 seen   ·   partial: joined after the start", theme.APPROX)
    assert (state, color, note, note_color) == ("In match, 12:34 seen", theme.TEXT, "Partial: joined after the start", theme.APPROX)
    assert APP.game_status_parts("In match, 12:34", theme.CERTAIN) == ("In match, 12:34", theme.CERTAIN, "", theme.APPROX)
    assert APP.game_status_parts("In the lobby   ·   no picture right now", theme.TEXT)[2:] == ("No picture right now", theme.MUTED)
    assert "13pt" in theme.STYLE.split("#gameStatus")[1].split("}")[0]


FIT_CHECK = """
import os, sys
from datetime import datetime, timedelta, timezone
root = sys.argv[1]
for name in ("src", "tests"):
    sys.path.insert(0, os.path.join(root, name))
import test_analytics_ui as T
import test_match_analytics as MA
import test_update_gui as G
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

with G.window() as w:
    win = w.win
    w.qt.setStyle("Fusion")
    w.qt.setStyleSheet(w.A.theme.STYLE)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    rec = T.today_and_three_days_ago(w)
    run = rec.run(datetime.now(timezone.utc) - timedelta(days=1, hours=3))
    run.chests(100).match(1, opened=30, played=50, closed=600, active=500, completion="partial", from_start=False, ended=580).end(700)
    rec.correction(datetime.now(timezone.utc) - timedelta(days=1, hours=2, minutes=55), 1, "broken_chest", run_id=run.run_id, match_number=1)
    page = win.analytics
    for width, height in ((1120, 800), (920, 640)):
        win.resize(width, height)
        win.show_page(page)
        MA.settle(w)
        for index in range(4):
            page.show_view(index)
            for _ in range(10):
                w.qt.processEvents()
            tab = page.views.widget(index)
            area = tab if isinstance(tab, QScrollArea) else page.table
            assert area.horizontalScrollBar().maximum() == 0, ("sideways", width, index)
print("fits")
"""


def test_every_tab_fits_the_smallest_window_without_scrolling_sideways():
    """In its own process with real fonts: the off-screen platform has none, so text there is the wrong size."""
    if os.name != "nt":
        return
    result = subprocess.run([sys.executable, "-c", FIT_CHECK, str(ROOT)], capture_output=True, text=True, cwd=ROOT,
                            env=dict(os.environ, QT_QPA_PLATFORM="windows"), timeout=180)
    assert result.returncode == 0 and "fits" in result.stdout, result.stderr[-800:]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    setup_module()
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}", flush=True)
        except Exception:
            failed += 1
            import traceback
            print(f"  FAIL  {name}", flush=True)
            traceback.print_exc()
    teardown_module()
    print(f"{len(tests) - failed}/{len(tests)} Analytics page checks passed")
    sys.exit(1 if failed else 0)
