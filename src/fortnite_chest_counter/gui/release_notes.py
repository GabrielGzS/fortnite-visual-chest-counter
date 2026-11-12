"""
Release notes in the update window, and what an automatic update check says (v0.4.0, UX-01 to UX-03). No Qt here, so it is unit-tested.

Release notes come from outside the app (the GitHub release text). They are shown as Markdown with raw HTML switched off and no remote images
(gui/app.py), and a link is followed only if it is one of this project's own GitHub pages.

Highlights first: the update window opens on the short part of the notes. A release body can mark where its highlights end with
HIGHLIGHTS_END, an HTML comment GitHub does not show; without it, the notes up to their second section heading are used, capped at
MAX_HIGHLIGHT_LINES lines. The full notes stay one click away.
"""

import urllib.parse

REPOSITORY = "https://github.com/GabrielGzS/fortnite-visual-chest-counter"
HIGHLIGHTS_END = "<!-- highlights end -->"
MAX_HIGHLIGHT_LINES = 40


def highlights(notes):
    """-> (the short part, True if more notes follow)."""
    text = (notes or "").replace("\r\n", "\n").strip()
    if HIGHLIGHTS_END in text:
        short = text.split(HIGHLIGHTS_END, 1)[0].rstrip()
    else:
        lines, headings, short_lines = text.split("\n"), 0, []
        for line in lines:
            if line.startswith("### ") or line.startswith("## ") and short_lines:
                headings += 1
                if headings == 2:
                    break
            short_lines.append(line)
        short = "\n".join(short_lines).rstrip()
    cut = short.split("\n")
    if len(cut) > MAX_HIGHLIGHT_LINES:
        short = "\n".join(cut[:MAX_HIGHLIGHT_LINES]).rstrip()
    return short, short.strip() != text.replace(HIGHLIGHTS_END, "").strip()


def link_allowed(url):
    """Only this project's GitHub pages (its releases, its download, its guides). Anything else in the notes is not followed."""
    try:
        parts = urllib.parse.urlsplit(str(url))
    except ValueError:
        return False
    project = urllib.parse.urlsplit(REPOSITORY)
    path = parts.path.rstrip("/")
    return (parts.scheme == "https" and (parts.hostname or "").lower() == project.hostname and not parts.username and not parts.password
            and parts.port in (None, 443) and (path == project.path or path.startswith(project.path + "/")))


def check_report(status, message, installed):
    """One quiet line in the activity log after an automatic check, so a check that ran is never silent. -> (level, text)."""
    if status == "up_to_date":
        return "info", f"Checked for updates: you have the latest version (v{installed})."
    if status == "available":
        return "info", f"{message} See the notice on the Dashboard, or Help & diagnostics > Updates."
    if status == "rejected":
        return "warn", f"A newer release did not pass its signature check, so it is not offered. {message}"
    return "info", f"The automatic update check did not finish: {message} It will try again the next time the app opens."
