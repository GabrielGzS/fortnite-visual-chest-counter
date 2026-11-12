"""
Release notes and update-check reports (v0.4.0, M8): highlights first, only this project's links followed, and every automatic check reported.

Run:   python tests/test_release_notes.py     (or pytest)
"""

import sys
from pathlib import Path as _P

ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fortnite_chest_counter.gui import release_notes as RN

V030 = (ROOT / "docs" / "RELEASE_NOTES_v0.3.0.md").read_text(encoding="utf-8")


def test_the_marker_ends_the_highlights():
    short, more = RN.highlights(f"Big news.\n\n- one\n- two\n{RN.HIGHLIGHTS_END}\n\n### Details\nlong text")
    assert short == "Big news.\n\n- one\n- two" and more


def test_without_a_marker_the_highlights_end_at_the_second_section():
    short, more = RN.highlights(V030)
    # v0.3.0's download line is itself a heading, so its highlights are the title, the download line and the opening paragraph
    assert short.startswith("## Fortnite Visual Chest Counter v0.3.0") and "The Match Tracking & Analytics update" in short and more
    assert "### Match tracking" not in short and "What's new at a glance" not in short
    assert len(short.split("\n")) <= RN.MAX_HIGHLIGHT_LINES


def test_short_notes_are_shown_whole():
    assert RN.highlights("Just a fix.") == ("Just a fix.", False)
    assert RN.highlights("") == ("", False) and RN.highlights(None) == ("", False)


def test_very_long_highlights_are_capped():
    short, more = RN.highlights("\n".join(f"line {n}" for n in range(500)))
    assert len(short.split("\n")) == RN.MAX_HIGHLIGHT_LINES and more


def test_only_this_projects_github_pages_are_followed():
    allowed = ["https://github.com/GabrielGzS/fortnite-visual-chest-counter", "https://github.com/GabrielGzS/fortnite-visual-chest-counter/releases/tag/v0.4.0",
               "https://github.com/GabrielGzS/fortnite-visual-chest-counter/blob/main/docs/MATCH_TRACKING.md"]
    refused = ["http://github.com/GabrielGzS/fortnite-visual-chest-counter", "https://github.com/GabrielGzS/fortnite-visual-chest-counter-evil",
               "https://github.com/someone/else", "https://github.com.evil.example/GabrielGzS/fortnite-visual-chest-counter",
               "https://user:pw@github.com/GabrielGzS/fortnite-visual-chest-counter", "javascript:alert(1)", "file:///C:/Windows/notepad.exe",
               "https://github.com:8443/GabrielGzS/fortnite-visual-chest-counter", "", "   "]
    assert all(RN.link_allowed(url) for url in allowed) and not any(RN.link_allowed(url) for url in refused)


def test_every_automatic_check_is_reported():
    assert RN.check_report("up_to_date", "You have the latest version.", "0.4.0") == ("info", "Checked for updates: you have the latest version (v0.4.0).")
    level, text = RN.check_report("available", "Version v0.4.1 is available.", "0.4.0")
    assert level == "info" and text.startswith("Version v0.4.1 is available.") and "Help & diagnostics" in text
    assert RN.check_report("rejected", "Bad signature.", "0.4.0")[0] == "warn"
    level, text = RN.check_report("failed", "GitHub is limiting update checks from this network.", "0.4.0")
    assert level == "info" and "did not finish" in text and "limiting" in text


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
    print(f"{len(tests) - failed}/{len(tests)} release note checks passed")
    sys.exit(1 if failed else 0)
