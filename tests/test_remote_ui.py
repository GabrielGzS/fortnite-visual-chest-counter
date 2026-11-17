"""
Remote Sharing and per-profile wording in the app (B2): the Overlay page's third tab (relay address and "Share" saved with the
page; the publisher key and viewer links act at once and never show a key or store a token), the Display tab's choice between
the wording every profile shares and a profile's own wording (switching profile switches the OBS text), the
CHESTS OPENED ≈ # preset, and the wording a brand-new install starts with. Runs the real window off screen with an in-memory
Credential Manager; nothing is sent anywhere (the Remote Sharing link is not started in these windows).

Run:   python tests/test_remote_ui.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fortnite_chest_counter import paths, profiles, settings
from fortnite_chest_counter.remote import protocol as P

import test_overlay_ui as O


class Creds:
    """Windows Credential Manager for Remote Sharing, in memory."""

    def __init__(self):
        self.store = {}

    def load_password(self, target=""):
        return self.store.get(target, "")

    def save_password(self, password, target="", comment="", username=""):
        self.store[target] = password

    def forget_password(self, target=""):
        self.store.pop(target, None)


@contextlib.contextmanager
def remote_page(config=None):
    creds = Creds()
    with O.shown(config=config) as (w, page, asked, applied, store):
        with patch.object(w.A.remote_sharing, "credentials", creds):
            page.load()
            yield w, page, creds


def base(w):
    return str(w.dir / "state" / "chest_state.json")


def config_text(w):
    path = w.dir / "config.toml"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def overlay_file(w):
    return (w.dir / "obs_output" / "chest_counter.txt").read_text(encoding="utf-8")


def clipboard():
    from PySide6.QtWidgets import QApplication
    return QApplication.clipboard().text()


# ==================================================================
# Remote Sharing tab
# ==================================================================

def test_relay_address_and_share_are_saved_with_the_page():
    with remote_page() as (w, page, creds):
        assert page.TABS == ("Display", "OBS WebSocket", "Remote Sharing")
        page.rs_url.setText("wss://relay.example")
        page.rs_enabled.setChecked(True)
        assert page.is_dirty()
        assert page.save() and not page.is_dirty()
        assert 'url = "wss://relay.example"' in config_text(w)
        remote = profiles.get(profiles.load(base(w)), "default")["remote"]
        assert remote["enabled"] is True and P.CHANNEL_RE.match(remote["channel"]) and remote["links"] == []
        page.rs_enabled.setChecked(False)                       # off again: the channel is kept for its links
        assert page.save()
        again = profiles.get(profiles.load(base(w)), "default")["remote"]
        assert again["enabled"] is False and again["channel"] == remote["channel"]


def test_a_bad_relay_address_or_sharing_without_one_writes_nothing():
    with remote_page() as (w, page, creds):
        before = config_text(w)
        page.rs_url.setText("ws://relay.example")              # not wss://, not this PC
        assert page.save() is False and page.is_dirty() and config_text(w) == before
        page.rs_url.setText("")
        page.rs_enabled.setChecked(True)
        assert page.save() is False and config_text(w) == before
        assert "remote" not in profiles.get(profiles.load(base(w)), "default")


def test_keys_act_at_once_and_only_the_setup_code_is_ever_shown():
    with remote_page() as (w, page, creds):
        page._rs_create_key()
        key = creds.store.get("Fortnite Visual Chest Counter/Remote Sharing publisher key")
        assert key and len(key) >= 43
        assert page.rs_setup.text() == hashlib.sha256(key.encode("ascii")).hexdigest()
        shown = " ".join(x.text() for x in (page.rs_setup, page.rs_key_state, page.rs_note, page.rs_status))
        assert key not in shown and not page.is_dirty()          # a credential, not a page setting
        page._rs_forget_key()                                   # asks first (answered yes here)
        assert not creds.store and page.rs_setup.text() == ""
        assert any("Forget the publisher key" in text or "deleted" in text for text in w.asked)


def test_a_new_link_copies_its_address_and_revoking_marks_it_without_storing_the_token():
    with remote_page() as (w, page, creds):
        assert not page.rs_new_link.isEnabled()                 # no saved relay address yet
        page.rs_url.setText("wss://relay.example")
        assert page.save() and page.rs_new_link.isEnabled()
        page.rs_new_label.setText("OBS on PC B")
        page._rs_new_link()
        remote = profiles.get(profiles.load(base(w)), "default")["remote"]
        link = remote["links"][0]
        url = clipboard()
        assert url.startswith(f"https://relay.example/o/#{remote['channel']}.{link['id']}.")
        token = url.split("#", 1)[1].split("&", 1)[0].split(".")[2]
        assert link["label"] == "OBS on PC B" and link["sha256"] == P.sha256_hex(token)
        assert token not in (w.dir / "state" / "profiles.json").read_text(encoding="utf-8")
        assert remote["enabled"] is False and not page.is_dirty()      # a link never turns sharing on by itself
        page._rs_revoke(link["id"], link["label"])
        assert profiles.get(profiles.load(base(w)), "default")["remote"]["links"][0]["revoked"] is True


def test_remote_status_is_shown_without_changing_what_is_being_edited():
    with remote_page() as (w, page, creds):
        page.rs_url.setText("wss://typed.example")
        page.show_remote_status({"state": "connected", "profile": "Default", "relay": "relay.example", "viewers": 2,
                                 "detail": "", "warning": ""})
        assert "2 viewer(s)" in page.rs_status.text() and page.rs_url.text() == "wss://typed.example"
        page.show_remote_status({"state": "key_rejected", "detail": "The relay did not accept this PC's publisher key.",
                                 "warning": "", "viewers": 0, "profile": "", "relay": ""})
        assert "did not accept" in page.rs_status.text()
        line = w.win.dashboard.remote_line                      # the Dashboard's one line (hidden while sharing is off)
        w.win.remote_status_shown({"state": "connected", "profile": "Default", "relay": "r", "viewers": 3, "detail": "", "warning": ""})
        assert not line.isHidden() and "Live, 3 viewer(s)" in line.text()
        w.win.remote_status_shown({"state": "off", "detail": "", "warning": "", "viewers": 0, "profile": "", "relay": ""})
        assert line.isHidden()


# ==================================================================
# a profile's own wording
# ==================================================================

def test_a_profile_can_keep_its_own_wording_and_switching_profile_switches_the_obs_text():
    with remote_page() as (w, page, creds):
        shared_text = overlay_file(w)
        profiles.create(base(w), "Streamer B", activate=True)
        w.win.profile_changed()
        page.load()
        assert page.scope_shared.isChecked() and "Streamer B" in page.scope_own.text()
        page.scope_own.setChecked(True)
        page._preset_chests()
        assert page.save()
        own = profiles.get(profiles.load(base(w)), "streamer-b")["display"]
        assert own["show"] == "approx" and own["approx_text"] == "CHESTS OPENED ≈ {count}"
        assert w.A.shared_display() == settings.DEFAULTS["display"] or "approx_text" not in config_text(w)
        assert overlay_file(w) == "CHESTS OPENED ≈ 0\n"
        profiles.set_active(base(w), "default")                 # another profile: the shared wording
        w.win.profile_changed()
        page.load()
        assert page.scope_shared.isChecked() and overlay_file(w) == shared_text
        profiles.set_active(base(w), "streamer-b")
        w.win.profile_changed()
        page.load()
        assert page.scope_own.isChecked() and overlay_file(w) == "CHESTS OPENED ≈ 0\n"
        page.scope_shared.setChecked(True)                      # back to the shared wording: the own one is removed
        assert page.approx_text.text() == w.A.C.hash_from_text(settings.DEFAULTS["display"]["approx_text"])
        assert page.save()
        assert "display" not in profiles.get(profiles.load(base(w)), "streamer-b")
        assert overlay_file(w) == shared_text


def test_export_and_import_from_the_dashboard_select_the_imported_profile_and_are_blocked_while_counting():
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    with remote_page() as (w, page, creds):
        profiles.create(base(w), "Streamer B", activate=True)
        w.win.profile_changed()
        target = str(w.dir / "Streamer B.fccprofile")
        shown = []
        with patch.object(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (target[:-len(".fccprofile")], ""))), \
                patch.object(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (target, ""))), \
                patch.object(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(a[2]))):
            w.win.export_profile()                              # the suffix is added when it is missing
            assert Path(target).exists() and "never this PC's settings" in shown[-1]
            asked = []
            w.win._ask_import = lambda package, clash, b: asked.append(clash["name"] if clash else None) or ("copy", "Streamer C")
            w.win.import_profile()
            assert asked == ["Streamer B"]                      # the clash was offered, the copy chosen
            reg = profiles.load(base(w))
            assert profiles.active(reg)["name"] == "Streamer C" and w.win.dashboard.profile.currentText() == "Streamer C"
            w.win.set_mode("counting")
            assert not w.win.dashboard.profile_transfer.isEnabled()
            w.win.set_mode("stopped")
            assert w.win.dashboard.profile_transfer.isEnabled()
            actions = [a.text() for a in w.win.dashboard.profile_transfer_menu.actions()]
            assert actions == ["Export this profile...", "Import a profile..."]


def test_new_setups_start_with_the_chests_opened_preset_and_existing_ones_keep_their_wording():
    from fortnite_chest_counter.gui import app as A
    saved = paths.APP_DIR
    try:
        with tempfile.TemporaryDirectory() as fresh, tempfile.TemporaryDirectory() as used:
            paths.APP_DIR = Path(fresh)
            (Path(fresh) / "state").mkdir()                     # as a release unpacks: state/ holds only a README
            (Path(fresh) / "state" / "README.txt").write_text("Your counter lives here.", encoding="utf-8")
            A.new_setup_wording()
            text = (Path(fresh) / "config.toml").read_text(encoding="utf-8")
            assert 'show = "approx"' in text and "CHESTS OPENED ≈ {count}" in text
            assert settings.load_config(str(Path(fresh) / "config.toml"))[0]["display"]["approx_text"] == "CHESTS OPENED ≈ {count}"
            paths.APP_DIR = Path(used)
            (Path(used) / "state").mkdir()                      # counted before, never saved a setting
            (Path(used) / "state" / "chest_state.json").write_text('{"certain": 3, "approximate": 9}', encoding="utf-8")
            A.new_setup_wording()
            assert not (Path(used) / "config.toml").exists()
    finally:
        paths.APP_DIR = saved


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok    {t.__name__}")
        except Exception as error:
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {t.__name__}: {error!r}")
    print(f"{len(tests) - failed}/{len(tests)} Remote Sharing UI checks passed")
    raise SystemExit(1 if failed else 0)
