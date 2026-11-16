"""
Overlay page save controls: two tabs (Display, OBS WebSocket) and ONE Save for both, the same way as Settings. A change says it is
not saved yet, switching tabs keeps it and asks nothing, leaving the page or closing the app with unsaved changes asks (save /
discard / stay), a failed save keeps the changes and writes nothing, and a save is used only once it is written and read back:
the OBS text files are rewritten when the wording changed, and OBS is reconnected only when its address or password changed.
The OBS password has three states - unchanged (empty box), newly typed, forgotten (at once, after asking) - and lives only in
the credential store. What the OBS link reports in the background never changes what is being edited.
Runs the real window off screen, with an in-memory stand-in for Windows Credential Manager. No video is decoded here.

Run:   python tests/test_overlay_ui.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))                                     # run without installing
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import counter as C
from fortnite_chest_counter import settings

import test_update_gui as G

OBS_ON = '[obs_websocket]\nenabled = true\nhost = "127.0.0.1"\nport = 4455\nsource = "Chests"\nsource_uuid = "u-1"\n'


class Store:
    """Windows Credential Manager, in memory: the tests never touch the real one."""

    def __init__(self, password="", broken=False):
        self.password, self.broken, self.saves, self.forgets = password, broken, 0, 0

    def save_password(self, password, target=None):
        if self.broken:
            raise OSError("Windows Credential Manager is not available")
        self.saves += 1
        self.password = password

    def load_password(self, target=None):
        return self.password

    def forget_password(self, target=None):
        self.forgets += 1
        self.password = ""

    def has_password(self, target=None):
        return bool(self.password)


@contextlib.contextmanager
def shown(answer="stay", config=None, store=None):
    """The real window on the Overlay page. -> (w, page, asked, applied, store): applied = [reconnect, ...] per OBS apply."""
    store = store or Store()
    with G.window(config=config) as w:
        from PySide6.QtWidgets import QApplication
        asked, applied = [], []
        creds = w.A.obs_credentials

        def fake_ask(parent, action):
            asked.append(action)
            return answer

        try:
            with patch.object(w.A, "ask_unsaved", fake_ask), \
                    patch.multiple(creds, save_password=store.save_password, load_password=store.load_password,
                                   forget_password=store.forget_password, has_password=store.has_password), \
                    patch.object(w.win, "apply_obs_settings", lambda reconnect=False: applied.append(reconnect)):
                w.win.resize(w.win.minimumSize())
                w.win.show()
                w.win.show_page(w.win.overlay)
                G.settle(w)
                yield w, w.win.overlay, asked, applied, store
        finally:
            w.win.hide()                     # the fixture closes the window after the patches are gone: nothing may ask then
            QApplication.processEvents()


def saved_cfg(w):
    return settings.load_config(w.dir / "config.toml")[0]


def config_bytes(w):
    path = w.dir / "config.toml"
    return path.read_bytes() if path.exists() else None


def sources(*names):
    return [{"name": n, "uuid": f"u-{n}", "kind": "text_gdiplus"} for n in names]


def pick_source(page, name):
    index = next(i for i in range(page.ws_source.count()) if (page.ws_source.itemData(i) or {}).get("name") == name)
    page.ws_source.setCurrentIndex(index)
    page.ws_source.activated.emit(index)


# ------------------------------------------------------------------ the page and its tabs

def test_two_tabs_and_the_save_controls_stay_in_view():
    with shown() as (w, page, _, _, _):
        assert [page.tab_buttons.button(i).text() for i in range(2)] == ["Display", "OBS WebSocket"]
        for index in range(2):
            page.show_tab(index)
            G.settle(w)
            content = page.page_scroll.widget()
            for part in (page.save_button, page.discard_button, page.saved):
                assert part.isVisible() and not content.isAncestorOf(part)
        assert page.tab_scrolls[0].widget().isAncestorOf(page.certain_text)
        assert page.tab_scrolls[1].widget().isAncestorOf(page.ws_host)
        assert page.saved.text() == "All changes saved" and not page.save_button.isEnabled() and not page.discard_button.isEnabled()


# ------------------------------------------------------------------ unsaved, saved, used

def test_a_wording_change_is_unsaved_until_saved_then_written_and_used():
    with shown() as (w, page, _, applied, _):
        before = saved_cfg(w)["display"]["certain_text"]
        page.certain_text.setText("Chest Hunt: #/500")
        assert page.is_dirty() and "Unsaved changes" in page.saved.text() and page.save_button.isEnabled()
        assert saved_cfg(w)["display"]["certain_text"] == before, "nothing is written before Save"
        assert page.save() is True
        assert saved_cfg(w)["display"]["certain_text"] == "Chest Hunt: {count}/500"
        assert "Overlay saved" in page.saved.text() and "text file was updated" in page.saved.text() and not page.is_dirty()
        assert "Chest Hunt: 0/500" in (w.dir / "obs_output" / "certain_chests.txt").read_text(encoding="utf-8")
        assert applied == [], "a wording change never touches OBS"


def test_changing_things_back_is_no_change():
    with shown() as (w, page, _, _, _):
        page.mode_buttons["inline"].setChecked(True)
        page.mode_buttons[C.display_mode(saved_cfg(w)["display"])].setChecked(True)
        page.certain_text.setText(page.certain_text.text() + "   ")   # trailing spaces: the same saved text
        page.certain_text.setText(page.certain_text.text().rstrip())
        assert not page.is_dirty() and page.saved.text() == "All changes saved"


def test_switching_tabs_keeps_unsaved_changes_and_asks_nothing():
    with shown(config=OBS_ON) as (w, page, asked, applied, _):
        page.certain_text.setText("Opened: #")
        page.show_tab(1)
        page.ws_port.setValue(4466)
        page.show_tab(0)
        page.show_tab(1)
        assert asked == [] and page.certain_text.text() == "Opened: #" and page.ws_port.value() == 4466 and page.is_dirty()
        assert page.save() is True and page.current_tab() == 1
        cfg = saved_cfg(w)
        assert cfg["display"]["certain_text"] == "Opened: {count}" and cfg["obs_websocket"]["port"] == 4466
        assert applied == [True], "the port changed: OBS is reconnected once"


def test_save_and_discard_keep_the_tab_on_screen():
    with shown(config=OBS_ON) as (w, page, _, _, _):
        page.show_tab(1)
        page.ws_host.setText("192.168.1.50")
        assert page.discard_button.isEnabled()
        page.discard_button.click()
        assert page.current_tab() == 1 and page.ws_host.text() == "127.0.0.1" and not page.is_dirty()
        page.ws_port.setValue(4400)
        page.save_button.click()
        assert page.current_tab() == 1 and saved_cfg(w)["obs_websocket"]["port"] == 4400


# ------------------------------------------------------------------ OBS is reconnected only when it has to be

def test_obs_settings_reconnect_only_when_the_address_or_password_changes():
    with shown(config=OBS_ON) as (w, page, _, applied, _):
        page.show_obs_status({"state": "live", "message": "", "source": "Chests", "sources": sources("Chests", "Other")})
        pick_source(page, "Other")
        assert page.is_dirty() and page.save() is True
        assert saved_cfg(w)["obs_websocket"]["source"] == "Other" and applied == [False], "a new source: re-target, no reconnect"
        page.ws_enabled.setChecked(False)
        assert page.save() is True and applied == [False, False] and saved_cfg(w)["obs_websocket"]["enabled"] is False
        page.ws_enabled.setChecked(True)
        page.ws_host.setText("192.168.1.50")
        assert page.save() is True and applied[-1] is True


def test_saving_with_no_obs_change_never_calls_obs():
    with shown(config=OBS_ON) as (w, page, _, applied, store):
        page.thousands.setChecked(not page.thousands.isChecked())
        assert page.save() is True and applied == [] and store.saves == 0 and store.forgets == 0


def test_while_counting_the_counter_rewrites_the_files_not_the_app():
    with shown() as (w, page, _, _, _):
        w.win.worker.is_running = True
        written = []
        with patch.object(w.win, "write_obs_files", lambda *a, **k: written.append(1)):
            page.certain_text.setText("Live: #")
            assert page.save() is True
        assert written == [] and "within a second" in page.saved.text()
        w.win.worker.is_running = False


# ------------------------------------------------------------------ the background never changes what is being edited

def test_obs_status_updates_never_change_what_is_being_edited():
    with shown(config=OBS_ON) as (w, page, _, _, _):
        page.show_obs_status({"state": "live", "message": "", "source": "Chests", "sources": sources("Chests", "Other", "Third")})
        pick_source(page, "Third")
        page.ws_host.setText("10.0.0.5")
        for _ in range(3):                                   # the link reports again and again, still targeting the saved source
            page.show_obs_status({"state": "live", "message": "", "source": "Chests", "sources": sources("Chests", "Other", "Third")})
        assert page.ws_source.currentData()["name"] == "Third" and page.ws_host.text() == "10.0.0.5" and page.is_dirty()
        assert page.save() is True and saved_cfg(w)["obs_websocket"]["source"] == "Third"


def test_a_rename_followed_in_the_background_is_not_undone_by_saving_the_wording():
    with shown(config=OBS_ON) as (w, page, _, _, _):
        page.certain_text.setText("Mine: #")
        w.win.obs_status_changed({"state": "live", "message": "updating 'Renamed'", "source": "Renamed", "uuid": "u-1",
                                  "sources": sources("Renamed")})
        assert saved_cfg(w)["obs_websocket"]["source"] == "Renamed"
        assert page.ws_source.currentData()["name"] == "Renamed" and page.is_dirty(), "the wording is still unsaved"
        assert page.save() is True
        cfg = saved_cfg(w)
        assert cfg["obs_websocket"]["source"] == "Renamed" and cfg["display"]["certain_text"] == "Mine: {count}"
        assert not page.is_dirty()


# ------------------------------------------------------------------ the password: unchanged, new, forgotten

def test_a_typed_password_is_stored_only_in_the_credential_store():
    with shown(config=OBS_ON) as (w, page, _, applied, store):
        page.ws_password.setText("s3cret-pass")
        assert page.is_dirty() and "s3cret" not in repr(page._values()), "the page never keeps the text as a setting"
        assert page.save() is True
        assert store.password == "s3cret-pass" and applied == [True] and page.ws_password.text() == ""
        assert "Saved" in page.ws_password.placeholderText() and not page.is_dirty()
        assert b"s3cret" not in (config_bytes(w) or b"")
        page.certain_text.setText("Other: #")                # an unrelated save keeps the stored password as it is
        assert page.save() is True and store.saves == 1 and store.forgets == 0 and store.password == "s3cret-pass"


def test_forget_password_asks_first():
    with shown(config=OBS_ON, store=Store("kept")) as (w, page, _, applied, store):
        assert not page.ws_forget.isHidden()
        w.answers[0] = False
        page._ws_forget()
        assert store.password == "kept" and w.asked and applied == []
        w.answers[0] = True
        page._ws_forget()
        assert store.password == "" and applied == [True] and page.ws_forget.isHidden()
        assert not page.is_dirty(), "forgetting is not a setting waiting for Save"


def test_credential_manager_unavailable_saves_nothing_and_keeps_the_typing():
    with shown(config=OBS_ON, store=Store(broken=True)) as (w, page, _, applied, store):
        before = config_bytes(w)
        page.ws_port.setValue(4499)
        page.ws_password.setText("new-pass")
        assert page.save() is False
        assert config_bytes(w) == before, "all or nothing: the port was put back too"
        assert page.ws_password.text() == "new-pass" and page.ws_port.value() == 4499 and page.is_dirty()
        assert "Not saved" in page.saved.text() and "Credential Manager" in page.saved.text() and applied == []
        assert w.errors and "Credential Manager" in w.errors[-1]


def test_a_password_that_does_not_read_back_is_not_saved_and_the_old_one_returns():
    store = Store("old")
    with shown(config=OBS_ON, store=store) as (w, page, _, applied, _):
        before = config_bytes(w)
        page.ws_port.setValue(4411)
        page.ws_password.setText("new")
        with patch.object(w.A.obs_credentials, "load_password", side_effect=["old", "garbled"]):
            assert page.save() is False
        assert store.password == "old" and config_bytes(w) == before and page.is_dirty() and applied == []


# ------------------------------------------------------------------ failures keep the changes

def test_a_failed_save_keeps_the_changes_and_writes_nothing():
    with shown() as (w, page, _, applied, _):
        before = config_bytes(w)
        page.certain_text.setText("Kept: #")
        with patch.object(C, "update_config_sections", side_effect=C.UserError("disk full")):
            assert page.save() is False
        assert config_bytes(w) == before and page.certain_text.text() == "Kept: #" and page.is_dirty()
        assert "Not saved: disk full" in page.saved.text() and page.save_button.isEnabled() and applied == []
        assert page.save() is True and saved_cfg(w)["display"]["certain_text"] == "Kept: {count}"


def test_a_bad_obs_address_is_refused_before_anything_is_written():
    with shown(config=OBS_ON) as (w, page, _, applied, _):
        before = config_bytes(w)
        page.ws_host.setText("my pc")
        page.certain_text.setText("Also: #")
        assert page.save() is False and config_bytes(w) == before and applied == [] and page.is_dirty()
        assert "127.0.0.1" in page.saved.text()
        page.discard()


def test_a_typo_in_config_toml_is_repaired_by_the_next_save_without_reconnecting():
    typo = '[display]\nshow = "bogus"\n[obs_websocket]\nenabled = true\nport = 99999\nsource = "Chests"\n'
    with shown(config=typo) as (w, page, _, applied, _):
        assert page.ws_port.value() == settings.DEFAULTS["obs_websocket"]["port"], "the page shows the default the counter uses"
        assert not page.is_dirty()
        page.certain_text.setText("Fixed: #")
        assert page.save() is True
        cfg, _, warnings = settings.load_config(w.dir / "config.toml")
        assert warnings == [], warnings
        assert cfg["obs_websocket"]["port"] == settings.DEFAULTS["obs_websocket"]["port"] and cfg["obs_websocket"]["source"] == "Chests"
        assert applied == [], "writing the default OBS already used changes nothing for OBS"


# ------------------------------------------------------------------ Connect is an action, not a setting

def test_connect_uses_the_saved_settings_or_saves_first():
    with shown(config=OBS_ON) as (w, page, _, applied, _):
        page.show_tab(1)
        assert page.ws_connect.text() == "Connect"
        page.ws_connect.click()
        assert applied == [True] and not page.is_dirty()
        page.ws_port.setValue(4477)
        assert page.ws_connect.text() == "Save and connect"
        with patch.object(C, "update_config_sections", side_effect=C.UserError("locked")):
            page.ws_connect.click()
        assert applied == [True] and page.is_dirty(), "a failed save does not connect"
        page.ws_connect.click()
        assert applied == [True, True] and saved_cfg(w)["obs_websocket"]["port"] == 4477 and page.ws_connect.text() == "Connect"


# ------------------------------------------------------------------ leaving with unsaved changes asks

def test_leaving_the_overlay_with_unsaved_changes_can_stay():
    with shown("stay") as (w, page, asked, _, _):
        page.certain_text.setText("Stay: #")
        w.win.show_page(w.win.settings_page)
        assert asked == ["leave Overlay"] and w.win.pages.currentWidget() is page and page.certain_text.text() == "Stay: #"
        page.discard()


def test_leaving_the_overlay_with_unsaved_changes_can_save_or_discard():
    with shown("save") as (w, page, asked, _, _):
        page.certain_text.setText("Saved on leaving: #")
        w.win.show_page(w.win.dashboard)
        assert asked and w.win.pages.currentWidget() is w.win.dashboard
        assert saved_cfg(w)["display"]["certain_text"] == "Saved on leaving: {count}"
    with shown("discard") as (w, page, asked, _, _):
        before = saved_cfg(w)["display"]["certain_text"]
        page.certain_text.setText("Thrown away: #")
        w.win.show_page(w.win.dashboard)
        assert asked and saved_cfg(w)["display"]["certain_text"] == before
        w.win.show_page(page)
        assert C.text_from_hash(page.certain_text.text()) == before and not page.is_dirty()


def test_closing_with_unsaved_overlay_changes_asks_and_can_stay():
    with shown("stay") as (w, page, asked, _, _):
        page.ws_enabled.setChecked(not page.ws_enabled.isChecked())
        w.win.close()
        assert asked == ["close the app"] and w.win.isVisible()
        page.discard()


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
    print(f"{len(tests) - failed}/{len(tests)} overlay UI checks passed")
    sys.exit(1 if failed else 0)
