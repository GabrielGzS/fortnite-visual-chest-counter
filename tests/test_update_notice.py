"""
The update notice, the Updates card and the release notes window (v0.4.0, M8: UX-01 to UX-03). Presentation only: the checks below also
confirm that the update's download, verification and installation code is byte for byte what v0.3.0 shipped.

Run:   python tests/test_update_notice.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import subprocess
from unittest.mock import patch

import test_update_gui as G
from fortnite_chest_counter.gui import release_notes as RN

NOTES = ("## v9.9.9\n\nFaster **Analytics**.\n\n- one\n- two\n" + RN.HIGHLIGHTS_END + "\n\n### Details\n\nEverything else, <b>raw</b> and "
         "<script>alert(1)</script>.\n\n![x](https://example.com/x.png)\n\n[project](https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases) "
         "[elsewhere](https://evil.example/)")


def auto_checked(w):
    w.win.auto_check()
    G.poll(w)


def log_lines(w):
    return w.win.dashboard.log.toPlainText().splitlines()


def test_an_automatic_check_is_never_silent():
    for result, expected in ((G.UP_TO_DATE, "Checked for updates: you have the latest version"), (G.NO_NETWORK, "did not finish: Could not reach GitHub."),
                             (G.available(), "is available. See the notice on the Dashboard")):
        with G.window(result) as w:
            if not w:
                return
            auto_checked(w)
            assert any(expected in line for line in log_lines(w)), (expected, log_lines(w))


def test_a_manual_check_is_not_logged_twice():
    with G.window(G.UP_TO_DATE) as w:
        if w:
            w.win.check_for_updates()
            G.poll(w)
            assert not any("Checked for updates" in line for line in log_lines(w))


def test_an_available_update_shows_a_quiet_notice_that_later_puts_away():
    with G.window(G.available()) as w:
        if not w:
            return
        d = w.win.dashboard
        assert d.update_notice.isHidden()
        auto_checked(w)
        assert not d.update_notice.isHidden() and f"v{G.NEW} is available" in d.update_notice_text.text() and w.win.update_dialog is None
        d.update_later.click()
        assert d.update_notice.isHidden()
        w.win.update_changed()
        assert d.update_notice.isHidden()                             # put away for this version


def test_no_notice_without_an_update():
    with G.window(G.UP_TO_DATE) as w:
        if w:
            auto_checked(w)
            assert w.win.dashboard.update_notice.isHidden()


def test_help_has_an_updates_card():
    with G.window(G.UP_TO_DATE) as w:
        if not w:
            return
        help_page = w.win.help
        w.win.update_changed()
        assert "Not checked since the app opened" in help_page.update_line.text() and help_page.update_open.isHidden()
        auto_checked(w)
        assert "Last checked at" in help_page.update_line.text() and "You have the latest version" in help_page.update_line.text()
    with G.window(G.available()) as w:
        if w:
            auto_checked(w)
            assert not w.win.help.update_open.isHidden() and f"v{G.NEW}" in w.win.help.update_line.text()
            w.win.help.update_open.click()
            assert w.win.update_dialog is not None and w.win.update_dialog.isVisible()


def test_notes_open_on_their_highlights_and_show_the_rest_on_request():
    with G.window(G.available(G.fake_update(notes=NOTES))) as w:
        if not w:
            return
        w.win.check_for_updates()
        G.poll(w)
        dialog = w.win.update_dialog
        text = dialog.notes.toPlainText()
        assert "Faster Analytics." in text and "Everything else" not in text and not dialog.more.isHidden()
        dialog.more.click()
        assert "Everything else" in dialog.notes.toPlainText() and dialog.more.text() == "Show only the highlights"


def test_raw_html_is_text_nothing_is_fetched_and_only_project_links_open():
    with G.window(G.available(G.fake_update(notes=NOTES))) as w:
        if not w:
            return
        w.win.check_for_updates()
        G.poll(w)
        dialog = w.win.update_dialog
        dialog.more.click()
        view = dialog.notes
        html = view.document().toHtml()
        assert "<b>raw</b>" in view.toPlainText() and "<script" not in html and "font-weight:700" in html     # bold Markdown, never raw HTML
        fetched = []
        real = view.loadResource
        with patch.object(view, "loadResource", side_effect=lambda kind, url: fetched.append(url.toString()) or real(kind, url)):
            view.resize(500, 600)
            view.grab()
        assert all(real(0, url) is None for url in fetched)            # asked, perhaps, but never given anything
        from PySide6.QtCore import QUrl
        with patch.object(G_app(), "QDesktopServices") as desktop:
            view._follow(QUrl("https://evil.example/"))
            view._follow(QUrl("javascript:alert(1)"))
            assert not desktop.openUrl.called
            view._follow(QUrl("https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases"))
            assert desktop.openUrl.call_count == 1
        assert view.isReadOnly() and not view.openLinks() and not view.openExternalLinks()


def G_app():
    from fortnite_chest_counter.gui import app
    return app


def test_the_update_path_itself_is_what_v030_shipped():
    """M8 changes the window only: download, verification, staging and installation are byte for byte v0.3.0's."""
    result = subprocess.run(["git", "diff", "--stat", "v0.3.0", "--", "src/fortnite_chest_counter/update/"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:                                        # not a git checkout (a release folder): nothing to compare
        return
    assert result.stdout.strip() == "", result.stdout


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
    print(f"{len(tests) - failed}/{len(tests)} update notice checks passed")
    sys.exit(1 if failed else 0)
