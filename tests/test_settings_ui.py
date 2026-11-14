"""
Settings save controls (v0.5.1): Save and the save status stay in view while the page scrolls, a change that is not saved yet says so, leaving
the page or closing the app with unsaved changes asks (save / discard / stay), a failed save keeps the changes and says why, and a mouse
wheel over a choice box scrolls the page instead of changing the setting. Also: the HUD Scale a run really uses is announced and logged.
Runs the real window off screen. No video is decoded here.

Run:   python tests/test_settings_ui.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import json
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import profiles, settings

import test_update_gui as G


@contextlib.contextmanager
def shown(answer="stay"):
    """The real window, shown at its smallest size, on Settings, with the unsaved-changes question answered `answer`. -> (w, page, asked)."""
    with G.window() as w:
        from PySide6.QtWidgets import QApplication
        asked = []
        w.win.resize(w.win.minimumSize())
        w.win.show()
        w.win.show_page(w.win.settings_page)
        G.settle(w)
        page = w.win.settings_page

        def fake(parent, action):
            asked.append(action)
            return answer

        try:
            with patch.object(w.A, "ask_unsaved", fake):
                yield w, page, asked
        finally:
            w.win.hide()                     # the fixture closes the window after the patches are gone: nothing may ask then
            QApplication.processEvents()


def hud_75(page):
    page.hud.setCurrentIndex(page.hud.findData("75"))


def active_hud(w):
    from fortnite_chest_counter.gui import app
    return app.load_cfg()[0]["detector"]["hud"]


# ------------------------------------------------------------------ the header stays in view

def test_save_and_status_are_outside_the_scrolling_part():
    with shown() as (w, page, _):
        content = page.page_scroll.widget()
        for part in (page.save_button, page.saved):
            assert not content.isAncestorOf(part), "it would scroll away"
            assert part.isVisible()
        page.page_scroll.verticalScrollBar().setValue(page.page_scroll.verticalScrollBar().maximum())
        G.settle(w)
        assert page.page_scroll.verticalScrollBar().maximum() > 0, "the page should scroll at the smallest window size"
        top_left = page.save_button.mapTo(w.win, page.save_button.rect().topLeft())
        assert 0 <= top_left.y() and top_left.y() + page.save_button.height() <= w.win.height()
        assert top_left.x() + page.save_button.width() <= w.win.width(), "Save must fit at the smallest window size"


# ------------------------------------------------------------------ unsaved changes are visible

def test_a_change_shows_unsaved_and_enables_save():
    with shown() as (w, page, _):
        assert page.saved.text() == "All changes saved" and not page.save_button.isEnabled()
        hud_75(page)
        assert "Unsaved changes" in page.saved.text() and page.save_button.isEnabled() and page.is_dirty()
        page.hud.setCurrentIndex(page.hud.findData("standard"))
        assert page.saved.text() == "All changes saved" and not page.save_button.isEnabled() and not page.is_dirty()


def test_every_kind_of_setting_marks_the_page_unsaved():
    with shown() as (w, page, _):
        for change in (lambda: page.language.setCurrentIndex((page.language.currentIndex() + 1) % page.language.count()),
                       lambda: page.fps.setCurrentIndex((page.fps.currentIndex() + 1) % page.fps.count()),
                       lambda: page.logging.setChecked(not page.logging.isChecked()),
                       lambda: page.match_on.setChecked(not page.match_on.isChecked()),
                       lambda: page.remember_window.setChecked(not page.remember_window.isChecked()),
                       lambda: page.update_limit.setValue(page.update_limit.value() + 1)):
            page.load()
            assert not page.is_dirty()
            change()
            assert page.is_dirty() and "Unsaved changes" in page.saved.text()
        page.load()


def test_saving_persists_the_hud_scale_into_the_profile_and_says_so():
    with shown() as (w, page, _):
        hud_75(page)
        assert active_hud(w) == "standard", "nothing is saved before Save"
        assert page.save() is True
        assert active_hud(w) == "75" and "Settings saved" in page.saved.text() and not page.save_button.isEnabled()
        reg = json.loads((w.dir / "state" / "profiles.json").read_text(encoding="utf-8"))
        assert [p.get("hud") for p in reg["profiles"] if p["id"] == reg["active"]] == ["75"]
        assert '"Default": 75% (experimental)' in page.hud_profile.text()
        hud_75(page)                                         # the same value again: nothing to save
        assert not page.is_dirty()


def test_a_failed_save_keeps_the_changes_and_says_why():
    with shown() as (w, page, _):
        hud_75(page)
        with patch.object(profiles, "set_hud", side_effect=profiles.ProfileError("disk full")):
            assert page.save() is False
        assert "Not saved: disk full" in page.saved.text() and page.save_button.isEnabled() and page.is_dirty()
        assert w.errors and "disk full" in w.errors[-1]
        assert page.save() is True and active_hud(w) == "75"


def test_a_value_that_does_not_stick_is_not_reported_as_saved():
    with shown() as (w, page, _):
        hud_75(page)
        with patch.object(profiles, "set_hud", lambda *a, **k: None):           # written nowhere
            assert page.save() is False
        assert "Not saved" in page.saved.text() and "HUD Scale Standard" in page.saved.text() and page.is_dirty()
        page.load()


# ------------------------------------------------------------------ leaving with unsaved changes asks

def test_leaving_with_unsaved_changes_can_stay():
    with shown("stay") as (w, page, asked):
        hud_75(page)
        w.win.show_page(w.win.dashboard)
        assert asked == ["leave Settings"]
        assert w.win.pages.currentWidget() is page and w.win.nav.currentRow() == w.win.pages.indexOf(page)
        assert page.is_dirty() and page.hud.currentData() == "75" and active_hud(w) == "standard"
        page.load()


def test_leaving_with_unsaved_changes_can_save():
    with shown("save") as (w, page, asked):
        hud_75(page)
        w.win.show_page(w.win.dashboard)
        assert asked and w.win.pages.currentWidget() is w.win.dashboard and active_hud(w) == "75"


def test_leaving_with_unsaved_changes_can_discard():
    with shown("discard") as (w, page, asked):
        hud_75(page)
        w.win.show_page(w.win.dashboard)
        assert asked and w.win.pages.currentWidget() is w.win.dashboard and active_hud(w) == "standard"
        w.win.show_page(page)
        assert page.hud.currentData() == "standard" and not page.is_dirty()


def test_a_failed_save_on_leaving_stays():
    with shown("save") as (w, page, asked):
        hud_75(page)
        with patch.object(profiles, "set_hud", side_effect=profiles.ProfileError("locked")):
            w.win.show_page(w.win.dashboard)
        assert w.win.pages.currentWidget() is page and page.is_dirty()
        page.load()


def test_leaving_without_changes_asks_nothing():
    with shown() as (w, page, asked):
        w.win.show_page(w.win.dashboard)
        w.win.show_page(page)
        w.win.show_page(w.win.analytics)
        assert asked == [] and w.win.pages.currentWidget() is w.win.analytics


def test_closing_with_unsaved_changes_asks_and_can_stay():
    with shown("stay") as (w, page, asked):
        hud_75(page)
        w.win.close()
        assert asked == ["close the app"] and w.win.isVisible()
        page.load()


# ------------------------------------------------------------------ the mouse wheel scrolls the page

def test_the_wheel_over_a_choice_scrolls_the_page_and_changes_nothing():
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication
    with shown() as (w, page, _):
        bar = page.page_scroll.verticalScrollBar()
        bar.setValue(0)
        before = [(box, box.currentIndex()) for box in (page.hud, page.language, page.fps, page.heartbeat)]
        for box, _ in before:
            for delta in (-120, 120, -120):
                event = QWheelEvent(QPointF(5, 5), QPointF(box.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, delta),
                                    Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
                QApplication.sendEvent(box, event)
        assert [(box, box.currentIndex()) for box, _ in before] == before and not page.is_dirty()
        event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(page.hud, event)
        assert bar.value() > 0, "the page scrolled"
        page.update_limit.setVisible(True)
        value = page.update_limit.value()
        QApplication.sendEvent(page.update_limit, event)
        assert page.update_limit.value() == value


def test_a_click_and_the_keyboard_still_change_a_choice():
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    with shown() as (w, page, _):
        page.hud.setFocus()
        QTest.keyClick(page.hud, Qt.Key_Down)
        assert page.hud.currentData() == "75" and page.is_dirty()
        page.load()


# ------------------------------------------------------------------ the HUD Scale a run uses is visible

def test_the_run_announces_and_logs_its_hud_scale():
    assert C.hud_line({"detector": {"hud": "75"}, "profile": {"name": "Me"}}) == 'Fortnite HUD Scale: 75% (experimental) (profile "Me")'
    assert C.hud_line({"detector": {"hud": "standard"}}) == "Fortnite HUD Scale: Standard"
    text = (ROOT / "src" / "fortnite_chest_counter" / "counter.py").read_text(encoding="utf-8")
    assert '"hud": cfg["detector"].get("hud", "standard")})' in text, "session_start records the HUD Scale"
    assert text.count("hud_line(cfg)") >= 2, "both the live counter and simulate announce it"


def test_diagnostics_report_the_active_profiles_hud_scale():
    import io
    import tempfile
    from contextlib import redirect_stdout
    from pathlib import Path
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        state = Path(tmp) / "state" / "chest_state.json"
        state.parent.mkdir(parents=True)
        (Path(tmp) / "config.toml").write_text(f'[state]\npath = "{state.as_posix()}"\n', encoding="utf-8")
        reg = profiles.load(str(state))
        profiles.set_hud(str(state), reg["active"], "75")
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                C.main(["diagnostics", "--config", str(Path(tmp) / "config.toml")])
            except SystemExit:
                pass
        assert "HUD Scale:        75% (experimental) (active profile)" in buf.getvalue(), buf.getvalue()


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
    print(f"{len(tests) - failed}/{len(tests)} settings UI checks passed")
    sys.exit(1 if failed else 0)
