"""
The Dashboard's three views (v0.3.0, M8A): every control survived the move, the views change only what is on screen, and nothing important can
hide on a view the user is not looking at. Runs the real window off screen.

Run:   python tests/test_dashboard_views.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "tests"))

import os
import subprocess
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_match_ui as U
import test_update_gui as G


def ui():
    """Looked up on each use, so a sabotage check can replace it."""
    from fortnite_chest_counter.gui import app
    return app


def counting(w):
    w.win.worker.is_running = True
    w.win.set_mode("counting")


def button_text(d, index):
    return d.view_buttons.button(index).text()


# ------------------------------------------------------------------ nothing was lost in the move

def test_there_are_three_views_starting_on_overview():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        assert d.views.count() == 3 and d.views.currentIndex() == A.OVERVIEW_VIEW
        assert [button_text(d, i) for i in range(3)][:2] == ["Overview", "Game"] and button_text(d, A.CONSOLE_VIEW).startswith("Console")
        assert d.view_buttons.button(A.OVERVIEW_VIEW).isChecked() and d.view_buttons.exclusive()


def test_every_control_is_on_its_view():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        placed = {A.OVERVIEW_VIEW: ("profile", "profile_new", "profile_rename", "profile_delete", "certain", "approx", "types", "match_row", "viewers", "obs_line", "source", "refresh", "start", "url_row", "url", "stability", "stability_hint", "source_hint", "metrics", "analyse"),
                  A.GAME_VIEW: ("game_status", "game_hint", "game_settings", "game_active", "game_seen", "game_unclear", "game_start", "game_language", "show_preview", "preview"),
                  A.CONSOLE_VIEW: ("rec_mode", "mark", "rec_status", "detail", "clear", "open_logs", "log")}
        for view, names in placed.items():
            for name in names:
                assert d.views.widget(view).isAncestorOf(getattr(d, name)), name


def test_status_and_errors_stay_above_the_views():
    with G.window() as w:
        d = w.win.dashboard
        for widget in (d.pill, d.banner, d.notice):
            assert d.isAncestorOf(widget) and not d.views.isAncestorOf(widget)


def test_an_error_is_visible_on_every_view():
    with G.window() as w:
        d = w.win.dashboard
        w.win.handle({"type": "error", "text": "the source broke"})
        for view in range(3):
            d.show_view(view)
            assert not d.banner.isHidden() and d.banner_text.text() == "the source broke"


# ------------------------------------------------------------------ switching

def test_clicking_a_tab_switches_the_view():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        d.view_buttons.button(A.CONSOLE_VIEW).click()
        assert d.views.currentIndex() == A.CONSOLE_VIEW and d.view_buttons.button(A.CONSOLE_VIEW).isChecked() and not d.view_buttons.button(A.OVERVIEW_VIEW).isChecked()
        d.view_buttons.button(A.GAME_VIEW).click()
        assert d.views.currentIndex() == A.GAME_VIEW


def test_switching_views_changes_nothing_else():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.set_counts(4, 9)
        before = (w.win.counts, w.win.mode, d.certain.value.text(), d.approx.value.text(), d.viewers.text(), sorted(p.name for p in w.dir.rglob("*")))
        with patch.object(w.win.worker, "send", create=True) as send:
            for view in (2, 1, 0, 2, 0):
                d.show_view(view)
        assert send.call_count == 0
        assert before == (w.win.counts, w.win.mode, d.certain.value.text(), d.approx.value.text(), d.viewers.text(), sorted(p.name for p in w.dir.rglob("*")))


def test_updates_reach_views_that_are_not_showing():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        counting(w)
        d.show_view(A.CONSOLE_VIEW)
        w.win.handle({"type": "counts", "certain": 3, "approx": 8})
        assert d.certain.value.text() == "3" and d.approx.value.text() == "8"
        d.show_view(A.OVERVIEW_VIEW)
        w.win.handle({"type": "info", "text": "seen while on another view"})
        assert "seen while on another view" in d.log.toPlainText()
        w.win.handle(U.status("IN_MATCH", U.match()))
        assert d.game_status.text() == "In match, 12:34" and d.match.text() == "In match, 12:34"


def test_the_links_open_their_pages():
    with G.window() as w:
        d = w.win.dashboard
        w.win.show_page(w.win.overlay)
        assert w.win.pages.currentWidget() is w.win.overlay and w.win.nav.currentRow() == w.win.pages.indexOf(w.win.overlay)
        d.game_settings.click()
        assert w.win.pages.currentWidget() is w.win.settings_page


def test_opening_a_page_still_reloads_it():
    with G.window() as w:
        with patch.object(w.win.settings_page, "load") as settings_load, patch.object(w.win.overlay, "load") as overlay_load:
            w.win.show_page(w.win.settings_page)
            w.win.show_page(w.win.overlay)
        assert settings_load.call_count == 1 and overlay_load.call_count == 1


# ------------------------------------------------------------------ the Console tab

def test_warnings_are_flagged_on_the_tab_when_the_log_is_out_of_sight():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        d.show_view(A.OVERVIEW_VIEW)
        w.win.handle({"type": "warn", "text": "careful"})
        assert button_text(d, A.CONSOLE_VIEW) == "Console (1)"
        w.win.handle({"type": "error", "text": "broken"})
        assert button_text(d, A.CONSOLE_VIEW) == "Console (2)"
        d.show_view(A.GAME_VIEW)
        assert button_text(d, A.CONSOLE_VIEW) == "Console (2)"


def test_ordinary_lines_do_not_flag_the_tab():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        for message in ({"type": "info", "text": "x"}, {"type": "line", "text": "x"}, {"type": "status", "text": "x"}):
            w.win.handle(message)
        assert button_text(d, A.CONSOLE_VIEW) == "Console"


def test_opening_the_console_clears_the_flag():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        w.win.handle({"type": "warn", "text": "careful"})
        d.show_view(A.CONSOLE_VIEW)
        assert button_text(d, A.CONSOLE_VIEW) == "Console"
        d.show_view(A.OVERVIEW_VIEW)
        assert button_text(d, A.CONSOLE_VIEW) == "Console"


def test_a_warning_while_reading_the_console_needs_no_flag():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        d.show_view(A.CONSOLE_VIEW)
        w.win.handle({"type": "warn", "text": "careful"})
        assert button_text(d, A.CONSOLE_VIEW) == "Console"


def test_the_log_controls_still_work():
    with G.window() as w:
        d = w.win.dashboard
        w.win.handle({"type": "info", "text": "keep me"})
        w.win.handle({"type": "stderr", "text": "debug only line"})
        assert "keep me" in d.log.toPlainText() and "debug only line" not in d.log.toPlainText()
        d.detail.setCurrentIndex(d.detail.findData("debug"))
        assert "debug only line" in d.log.toPlainText()
        d.clear.click()
        assert d.log.toPlainText() == "" and not w.win.entries


# ------------------------------------------------------------------ the live preview

def preview_rig(w):
    w.win.preview_reader = MagicMock()
    counting(w)
    w.win.dashboard.show_preview.setChecked(True)


def wanted(w):
    return w.win.preview_reader.set_wanted.call_args[0][0]


def test_the_preview_runs_only_while_its_view_is_open():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        preview_rig(w)
        d.show_view(A.GAME_VIEW)
        assert wanted(w) is True and w.win.preview_timer.isActive()
        d.show_view(A.OVERVIEW_VIEW)
        assert wanted(w) is False and not w.win.preview_timer.isActive()
        d.show_view(A.GAME_VIEW)
        assert wanted(w) is True
        w.win.preview_timer.stop()
        w.win.preview_reader = None


def test_the_preview_stays_off_until_asked_for():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        w.win.preview_reader = MagicMock()
        counting(w)
        d.show_view(A.GAME_VIEW)
        assert wanted(w) is False and d.preview.isHidden()
        d.show_preview.setChecked(True)
        assert not d.preview.isHidden()
        w.win.preview_timer.stop()
        w.win.preview_reader = None


# ------------------------------------------------------------------ the Game view

DASH = "—"


def tiles(d):
    return [t.value.text() for t in (d.game_active, d.game_seen, d.game_unclear, d.game_start, d.game_language)]


def test_tracking_off_explains_itself_and_offers_settings():
    with G.window() as w:
        d = w.win.dashboard
        w.win.update_game_idle()
        assert d.game_status.text() == "Match tracking is off" and not d.game_settings.isHidden() and tiles(d) == [DASH] * 5


def test_tracking_on_but_not_counting():
    with G.window(config='[match]\nmode = "on"\n') as w:
        d = w.win.dashboard
        w.win.update_game_idle()
        assert d.game_status.text() == "Not counting" and d.game_settings.isHidden()


def test_shadow_counts_as_off_in_the_app():
    with G.window(config='[match]\nmode = "shadow"\n') as w:
        w.win.update_game_idle()
        assert w.win.dashboard.game_status.text() == "Match tracking is off"


def test_a_session_keeps_the_mode_it_started_with():
    with G.window() as w:
        d = w.win.dashboard
        w.win.session_match_mode = "off"
        counting(w)
        assert d.game_status.text() == "Match tracking is off for this session"
        page = w.win.settings_page
        page.load()
        page.match_on.setChecked(True)
        page.save()
        assert d.game_status.text() == "Match tracking is off for this session"


def test_waiting_for_the_first_status():
    with G.window() as w:
        w.win.session_match_mode = "on"
        counting(w)
        assert w.win.dashboard.game_status.text() == "Waiting for the first picture"


def test_a_match_fills_the_tiles():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(U.status("IN_MATCH", {**U.match(from_start=False), "uncertain_seconds": 65.0}))
        assert "partial" in d.game_status.text() and tiles(d) == ["12:34", "13:20", "01:05", "No", "English"] and d.game_settings.isHidden()


def test_no_open_match_shows_dashes_not_zeros():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(U.status("LOBBY"))
        assert d.game_status.text() == "In the lobby" and tiles(d) == [DASH] * 5


def test_an_unknown_value_is_a_dash():
    with G.window() as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(U.status("IN_MATCH", U.match(active=None, english=False)))
        assert tiles(d)[0] == DASH and tiles(d)[4] == "Not confirmed"


def test_silence_reaches_the_game_view():
    with G.window() as w:
        d, A = w.win.dashboard, ui()
        counting(w)
        w.win.handle(U.status("IN_MATCH", U.match()))
        w.win.match_seen_at -= A.MATCH_STALE_SECONDS + 1
        w.win._check_match_video()
        assert d.game_status.text() == "No video right now"


def test_stopping_resets_the_game_view():
    with G.window(config='[match]\nmode = "on"\n') as w:
        d = w.win.dashboard
        counting(w)
        w.win.handle(U.status("IN_MATCH", U.match()))
        w.win.worker.is_running = False
        w.win.handle({"type": "exit", "code": 0})
        assert d.game_status.text() == "Not counting" and tiles(d) == [DASH] * 5


# ------------------------------------------------------------------ does it fit

FIT_CHECK = """
import os, sys
root = sys.argv[1]
for name in ("src", "tests"):
    sys.path.insert(0, os.path.join(root, name))
import test_update_gui as G
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

with G.window() as w:
    win, d = w.win, w.win.dashboard
    w.qt.setStyle("Fusion")
    w.qt.setStyleSheet(w.A.theme.STYLE)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    d.source.addItem("Livestream URL", {"source": "stream"})
    d.source.setCurrentIndex(0)
    for width, height, down in ((1120, 800, True), (920, 640, False)):
        win.resize(width, height)
        for view in range(3):
            d.show_view(view)
            for _ in range(10):
                w.qt.processEvents()
            area = d.findChild(QScrollArea)
            assert area.horizontalScrollBar().maximum() == 0, ("sideways", width, view)
            assert not down or area.verticalScrollBar().maximum() == 0, ("down", width, view)
print("fits")
"""


def test_the_views_fit_without_scrolling_at_the_default_size():
    """In its own process with real fonts: the off-screen platform has none, so text there is the wrong size."""
    if os.name != "nt":
        return
    result = subprocess.run([sys.executable, "-c", FIT_CHECK, str(ROOT)], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, QT_QPA_PLATFORM="windows"), timeout=120)
    assert result.returncode == 0 and "fits" in result.stdout, result.stderr[-800:]


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
    print(f"{len(tests) - failed}/{len(tests)} dashboard view checks passed")
    sys.exit(1 if failed else 0)
