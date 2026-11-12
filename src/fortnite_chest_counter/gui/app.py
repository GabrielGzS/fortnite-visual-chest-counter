"""
Fortnite Visual Chest Counter - the desktop app.

    runtime\\python\\pythonw.exe -m fortnite_chest_counter.gui      (what "Fortnite Visual Chest Counter.exe" starts)

The window is a remote control and a viewer. Counting runs in a separate worker process - the same `live` command the
console version uses - and the window only observes it (see worker.py). Closing the activity panel, hiding the preview,
minimising or even a crash of the window never interrupts counting; every setting it changes goes through the same
config.toml / state file as the command line, so the two always agree.
"""

import ctypes
import json
import os
import queue
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QPoint, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QIcon, QImage, QPalette, QPixmap, QTextDocument
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QTextBrowser,
                               QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from fortnite_chest_counter import counter as C
from fortnite_chest_counter.console import CHEST_LABELS
from fortnite_chest_counter import match_analytics, match_history, paths, profiles, progression, records, settings, timeline
from fortnite_chest_counter.detection import chest_types
from fortnite_chest_counter.gui import charts, release_notes, theme
from fortnite_chest_counter.gui import update_manager as UM
from fortnite_chest_counter.gui.worker import Worker, run_command
from fortnite_chest_counter.obs import credentials as obs_credentials
from fortnite_chest_counter.obs.link import TextOutputLink
from fortnite_chest_counter.preview import PreviewReader, block_name
from fortnite_chest_counter.progress import Eta, clock_text, describe
from fortnite_chest_counter.update import install as update_install
from fortnite_chest_counter.version import APP_NAME, RELEASE_CHANNEL, TAGLINE, __version__

ASSETS = Path(__file__).resolve().parent / "assets"
APP_ID = "GabrielGzS.FortniteVisualChestCounter"
HOTKEY_ID = 0xC0DE
RECORDING_CHOICES = (("Off", "off"), ("Only around my marks  (smallest)", "marks"),
                     ("Around chest decisions and my marks", "events"), ("Whole session  (about 10 GB per hour)", "session"))
RECORDING_TEXT = {"marks": "only around your marks", "events": "around chest decisions and your marks",
                  "session": "the whole session"}
REPO_URL = "https://github.com/GabrielGzS/fortnite-visual-chest-counter"
UPDATE_HEALTH_DELAY_MS = 2000                                  # the window must have been running this long before it counts as started
AUTO_CHECK_DELAY_MS = 6000                                     # after the window is up, so a check never competes with starting
INSTALL_STOP_DEADLINE_MS = 45000                               # longer than the worker's own 30 seconds to stop
RESULT_WATCH_SECONDS = 300
LOG_LIMIT = 3000
fmt = settings.format_count
# OBS WebSocket output (obs/link.py) states -> (short name, colour)
OBS_STATES = {"off": ("Off", theme.MUTED), "connecting": ("Connecting", theme.INFO), "waiting": ("Waiting for OBS", theme.APPROX),
              "pick": ("Connected - pick a Text source", theme.APPROX), "missing": ("Connected - source not found", theme.APPROX),
              "reads_file": ("Connected - the source reads a file", theme.APPROX), "live": ("Connected", theme.CERTAIN),
              "password": ("Password problem", theme.REJECT), "kicked": ("Disconnected by OBS", theme.REJECT),
              "unsupported": ("Not OBS WebSocket 5", theme.REJECT), "error": ("Problem", theme.REJECT)}


# ==================================================================
# small helpers
# ==================================================================

def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addFile(str(ASSETS / f"icon_{size}.png"), QSize(size, size))
    return icon


def set_class_icon(widget):
    """Windows: also give the window CLASS our icon. Qt registers its window class with the icon resource of the running
    .exe - here pythonw.exe, which has none Qt uses - so the class icon was Windows' generic application icon. The window
    itself always carries our icon (WM_SETICON), but when the app is too busy to answer the taskbar's WM_GETICON in time
    (typically while it is still starting up), Windows falls back to the class icon: the generic icon "sometimes" seen in
    the taskbar. With the class icon set as well, every fallback shows our icon. Never fatal."""
    if os.name != "nt":
        return False
    done = 0
    try:
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                      wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_size_t]
        user32.SetClassLongPtrW.restype = ctypes.c_size_t
        hwnd = int(widget.winId())                          # creates the native window if it does not exist yet
        for index, metric in ((-14, 11), (-34, 49)):        # GCLP_HICON / SM_CXICON, GCLP_HICONSM / SM_CXSMICON
            size = user32.GetSystemMetrics(metric)
            icon = user32.LoadImageW(None, str(ASSETS / "app.ico"), 1, size, size, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
            if icon:
                user32.SetClassLongPtrW(hwnd, index, icon)
                done += 1
    except Exception:
        pass
    return done == 2


def open_path(path):
    path = Path(path)
    if path.is_dir() or path.is_file():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))


def config_file():
    return paths.APP_DIR / settings.DEFAULT_CONFIG_PATH


def load_cfg():
    """config.toml with the counter file of the ACTIVE count profile (profiles.py) - every read of the counts, every
    reset / edit and the OBS files follow the profile chosen on the Dashboard."""
    cfg, _, warnings = settings.load_config(str(config_file()) if config_file().exists() else None)
    cfg["state"]["path"] = str(paths.APP_DIR / cfg["state"]["path"])          # profiles.json lives next to it
    profiles.apply(cfg, warn=warnings.append)
    return cfg, warnings


# ---- window size and position ([app] remember_window)
WINDOW_FILE = Path("state") / "window.json"           # next to the counts; the release zip never contains it


def window_file():
    return paths.APP_DIR / WINDOW_FILE


def save_window(widget, path):
    """Qt's own saveGeometry (normal size and position, maximised / full-screen state, which screen) -> a small JSON file."""
    try:
        C.atomic_write(path, json.dumps({"version": 1, "geometry": bytes(widget.saveGeometry().toBase64()).decode("ascii")}))
        return True
    except OSError:
        return False


def restore_window(widget, path):
    """Apply a layout saved by save_window, before the window is shown. -> True if one was applied. Qt itself moves a
    window whose screen is gone onto an available screen; keep_visible covers anything still unreachable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        geometry = QByteArray.fromBase64(data["geometry"].encode("ascii"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False                                    # no file yet, or a damaged one: default layout
    if geometry.isEmpty() or not widget.restoreGeometry(geometry):
        return False
    keep_visible(widget)
    return True


def keep_visible(widget, screens=None):
    """If the title bar would not be reachable on any screen (monitor unplugged, resolution lowered), centre the window on
    the primary screen at a size that fits. `screens`: available-area QRects (default: the real screens)."""
    if screens is None:
        screens = [s.availableGeometry() for s in QGuiApplication.screens()]
    if not screens:
        return
    frame = widget.frameGeometry() if widget.isVisible() else widget.geometry()
    title = QRect(frame.left(), frame.top(), frame.width(), 32)
    if any(title.intersected(s).width() >= 120 and title.intersected(s).height() >= 16 for s in screens):
        return
    area = screens[0]
    w, h = min(widget.width(), area.width()), min(widget.height(), area.height())
    widget.resize(w, h)
    widget.move(area.center() - QPoint(w // 2, h // 2))


def read_counts(state_path):
    """(certain, approx) from the counter file, or None. Read-only: unlike load_state it never moves a file."""
    try:
        raw = json.loads(Path(state_path).read_text(encoding="utf-8"))
        certain, approx = raw["certain"], raw["approximate"]
        if isinstance(certain, int) and isinstance(approx, int):
            return certain, max(approx, certain)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def read_types(state_path):
    """The chest-type breakdown of the counter file (counter.type_breakdown), or None. Read-only."""
    try:
        raw = json.loads(Path(state_path).read_text(encoding="utf-8"))
        state = {**C.fresh_state(), **raw}
        cleaned = C._clean_types(raw.get("types"))
        state["types"] = cleaned if cleaned is not None else C.fresh_types()
        return C.type_breakdown(state)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def types_text(breakdown):
    """One compact line: the APPROX total split by chest type (labels only - the totals stay the source of truth)."""
    if not breakdown:
        return ""
    parts = [f"{chest_types.LABELS[k]} {fmt(breakdown[k]['approx'])}" for k in (*chest_types.KNOWN, chest_types.UNKNOWN)
             if k in breakdown and breakdown[k]["approx"]]
    parts += [f"{k} {fmt(v['approx'])}" for k, v in breakdown.items()
              if k not in (*chest_types.KNOWN, chest_types.UNKNOWN, "unclassified") and v["approx"]]
    rest = breakdown.get("unclassified", {}).get("approx", 0)
    if rest:
        parts.append(f"not classified {fmt(rest)}")
    return "   ·   ".join(parts) if parts else "no chests yet"


MATCH_SCREENS = {"LOBBY": "In the lobby", "LOADING": "Loading", "PRE_GAME": "Waiting for the match to start"}
MATCH_STALE_SECONDS = 5                     # the worker reports once a second of video: this long without one means no video
UNKNOWN_VALUE = "—"
OVERVIEW_VIEW, GAME_VIEW, CONSOLE_VIEW = range(3)
# Why a count was corrected. A +1 does not mean the detector failed: Fortnite can count a chest with nothing on screen to detect.
CORRECTION_WHY = {1: (("manual", "Not sure / balance fix"), ("broken_chest", "Broken chest"), ("missed", "A visible chest the counter missed"),
                      ("not_visible", "Fortnite counted it, nothing else to see")),
                  -1: (("manual", "Not sure / balance fix"), ("false_positive", "Counted something that was not a chest"))}
DASHBOARD_VIEWS = (("Overview", "Your counts and the video source"), ("Game", "What match tracking sees right now, and the live preview"),
                   ("Console", "The activity log, warnings and diagnostic recording"))


def match_clock(seconds):
    """"12:34" or "1:02:03", or None when the time is not known: never a made-up 0:00."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 <= seconds < 10 ** 7:
        return None
    minutes, rest = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{rest:02d}" if hours else f"{minutes:02d}:{rest:02d}"


def _match_doubt(match):
    """Why this match cannot be taken at face value, or "" when its whole course has been seen so far."""
    if not match.get("english_confirmed"):
        return "not confirmed yet (no English game text seen)"
    if not match.get("observed_from_start"):
        return "partial: joined after the start"
    if match.get("discontinuity"):
        return "partial: part of it was not seen"
    return ""


def match_line(message):
    """One worker "match" message -> (text, colour) for the Dashboard. It says only what the evidence supports: seeing play is not knowing
    a whole match was seen, and an ending on screen does not make a match complete."""
    if message.get("failed"):
        return "Stopped for this session after an error. Counting is not affected.", theme.REJECT
    if message.get("unavailable"):
        return "Not available for this session. Counting is not affected.", theme.MUTED
    state, match = message.get("state"), message.get("match") or {}
    if state in MATCH_SCREENS:
        text, color = MATCH_SCREENS[state], theme.TEXT
    elif state == "IN_MATCH" and match:
        doubt, clock = _match_doubt(match), match_clock(match.get("active_seconds"))
        lead = "In match" if match.get("english_confirmed") else "Possibly in a match"
        text = lead + (f", {clock}{' seen' if doubt else ''}" if clock else "") + (f"   ·   {doubt}" if doubt else "")
        color = theme.APPROX if doubt else theme.CERTAIN
    elif state == "ELIMINATED":
        doubt = _match_doubt(match) if match else ""
        text = ("Match over" if match.get("ended_by") in ("placed", "victory") else "Spectating or out of the match") + (f"   ·   {doubt}" if doubt else "")
        color = theme.INFO
    else:
        return "Not sure yet", theme.MUTED
    if message.get("picture") in ("black", "frozen"):
        text += "   ·   no picture right now"
    return text, color


def game_status_parts(text, color):
    """The Game view's status (v0.4.0, UX-05): the state on its own, in a calm colour, and what to know about it (partial, not confirmed, no
    picture) as a small note. -> (state, colour, note, note colour). Partial is a normal outcome, so it is never shown as a large warning."""
    state, *notes = text.split("   ·   ")
    note = "   ·   ".join(notes)
    if note:
        note = note[0].upper() + note[1:]
    calm = theme.TEXT if color == theme.APPROX else color
    return state, calm, note, theme.MUTED if note.startswith("No picture") else theme.APPROX


def match_note(match):
    """What the numbers of the current match can be taken to mean."""
    if not match:
        return "No match right now"
    if match.get("english_confirmed") is not True:
        return "Not confirmed as a match yet"
    if match.get("discontinuity"):
        return "Part of this match was not seen"
    if match.get("observed_from_start") is False:
        return "Since counting started"
    return "This match only"


def match_summary(message):
    """The current match on the Overview line, or nothing when it is not known to be a match."""
    match, chests = message.get("match") or {}, message.get("chests")
    if chests is None or match.get("english_confirmed") is not True:
        return ""
    rate = match_analytics.match_rate(chests["certain"], chests["approx"], match.get("active_seconds"))
    return f"   ·   {plural(chests['approx'], 'chest')} this match" + (f"   ·   {rate.approx_per_minute:.2f} per minute" if rate else "")


def last_match_text(last):
    """The final numbers of the match that just ended. Empty for a record too weak to be worth replacing the last real one."""
    if not last or last.get("english_confirmed") is not True:
        return ""
    active = last.get("active_seconds") or 0
    if not last["approx"] and active < match_analytics.MIN_MATCH_RATE_SECONDS:
        return ""
    rate = match_analytics.match_rate(last["certain"], last["approx"], active)
    parts = [f"CERTAIN {fmt(last['certain'])}", f"APPROX {fmt(last['approx'])}"] + ([f"{rate.approx_per_minute:.2f} per minute"] if rate else [])
    return "Last match:   " + "   ·   ".join(parts + [QUALITY_LOOK[last["completion"]][0], match_analytics.ending_text(last)])


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, name=None, tip=None, on_click=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    if tip:
        widget.setToolTip(tip)
    if on_click:
        widget.clicked.connect(on_click)
    widget.setCursor(Qt.PointingHandCursor)
    return widget


def restyle(widget, name):
    """Give a widget another style name (e.g. primary -> danger). Qt only re-reads the style sheet after a re-polish."""
    widget.setObjectName(name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def card(title=None, hint=None):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    if title:
        layout.addWidget(label(title, "cardTitle"))
    if hint:
        layout.addWidget(label(hint, "hint", wrap=True))
    return frame, layout


def page_layout(widget, title, subtitle):
    """A scrollable page with a title. -> the content layout."""
    widget.setObjectName("page")
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("page")
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(30, 24, 30, 24)
    layout.setSpacing(16)
    layout.addWidget(label(title, "pageTitle"))
    if subtitle:
        layout.addWidget(label(subtitle, "pageSub", wrap=True))
    scroll.setWidget(inner)
    outer.addWidget(scroll)
    return layout


def hline():
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {theme.BORDER};")
    return line


def ask(parent, title, text, yes="Yes", no="Cancel", danger=False):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    ok = box.addButton(yes, QMessageBox.AcceptRole)
    box.addButton(no, QMessageBox.RejectRole)
    box.setDefaultButton(ok)
    box.exec()
    return box.clickedButton() is ok


def show_error(parent, text):
    QMessageBox.warning(parent, APP_NAME, text)


# ==================================================================
# activity console formatting
# ==================================================================

VERDICT = {"certain": ("CHEST +1", theme.CERTAIN), "approx": ("CHEST ~+1", theme.APPROX),
           "rejected": ("not counted", theme.REJECT)}
# Livestream URL connection states (StreamSource): colour, Dashboard pill text, text over the preview (None = show video)
STREAM_STATES = {"live": (theme.CERTAIN, "Counting", None),
                 "buffering": (theme.APPROX, "Buffering", "BUFFERING ...\nwaiting for video from the stream"),
                 "ad": (theme.APPROX, "Ad break", "AD BREAK ...\ncounting continues when the game is back"),
                 "incomplete": (theme.APPROX, None, None),
                 "lagging": (theme.APPROX, None, None),
                 "caught_up": (theme.CERTAIN, None, None),
                 "reconnecting": (theme.REJECT, "Reconnecting", "RECONNECTING ...\nthe stream connection was lost"),
                 "offline": (theme.REJECT, "Stream offline", "STREAM OFFLINE\nchecking again automatically"),
                 "no_video": (theme.REJECT, "No video", "NO VIDEO\nthe app is not receiving pictures from this source")}


def _span(text, color, bold=False):
    weight = "font-weight:600;" if bold else ""
    return f'<span style="color:{color};{weight}">{escape(str(text))}</span>'


def _pad(text, width):
    return escape(text) + "&nbsp;" * max(width - len(text), 0)


def log_entries(message):
    """-> [(debug_only, html)] for one worker message."""
    kind = message.get("type")
    clock = message.get("clock") or time.strftime("%H:%M:%S")
    stamp = _span(clock, theme.DIM) + "&nbsp;&nbsp;"
    if kind == "event":
        text, color = VERDICT.get(message.get("verdict"), ("?", theme.MUTED))
        if message.get("generic"):
            text, color = "prompt only", theme.DIM
        why = f" - {message['why']}" if message.get("why") else ""
        totals = ""
        if message.get("certain_text") is not None:
            totals = "&nbsp;" * 3 + _span(f"CERTAIN {message['certain_text']} | APPROX {message['approx_text']}", theme.DIM)
        chest = message.get("chest_label")
        kind_of_chest = f'<span style="color:{theme.CHEST_COLORS.get(chest, theme.MUTED)}">{_pad(chest, 15)}</span>' if chest else ""
        main = (stamp + f'<span style="color:{color};font-weight:600">{_pad(text, 12)}</span>' + kind_of_chest
                + escape(f"{message.get('evidence', '')}{why}") + totals)
        detail = "&nbsp;" * 10 + _span(f"{message.get('event_id', '')} at {message.get('stamp', '')} | {message.get('source', '')}"
                       f" | latency {message.get('latency_s') or 0:.1f}s | {message.get('reason', '')}", theme.DIM)
        return [(bool(message.get("generic")), main), (True, detail)]
    if kind == "status":
        return [(True, stamp + _span(message.get("text", ""), theme.DIM))]
    if kind == "type_update":
        return [(False, stamp + _span(f"Chest type read again: {CHEST_LABELS.get(message.get('chest_type'), 'Unknown chest')} ({message.get('event_id', '')})", theme.DIM))]
    if kind == "stream":
        color = STREAM_STATES.get(message.get("state"), (theme.MUTED,))[0]
        return [(False, stamp + _span(message.get("text", ""), color, bold=message.get("state") != "incomplete"))]
    if kind in ("info", "warn", "error", "line", "stderr"):
        text = str(message.get("text", "")).strip("\n")
        if not text:
            return []
        color = theme.LOG_COLORS.get(kind, theme.MUTED)
        prefix = {"warn": "Warning: ", "error": "Error: "}.get(kind, "")
        debug_only = kind == "stderr"
        lines = text.split("\n")
        out = [(debug_only, stamp + _span(prefix + lines[0], color, bold=kind == "error"))]
        out += [(debug_only, "&nbsp;" * 10 + _span(line, color)) for line in lines[1:] if line.strip()]
        return out
    return []


# ==================================================================
# widgets
# ==================================================================

class CountCard(QFrame):
    def __init__(self, title, subtitle, color):
        super().__init__()
        self.setObjectName("countCard")
        self.color = color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 18, 0)
        layout.setSpacing(16)
        bar = QFrame()
        bar.setFixedWidth(5)
        bar.setStyleSheet(f"background: {color}; border-top-left-radius: 12px; border-bottom-left-radius: 12px;")
        layout.addWidget(bar)
        box = QVBoxLayout()
        box.setContentsMargins(0, 14, 0, 14)
        box.setSpacing(0)
        self._box = box
        self.title = label(title, "countLabel")
        box.addWidget(self.title)
        self.value = label("0", "countValue")
        self.value.setStyleSheet(f"color: {color};")
        box.addWidget(self.value)
        self.sub = label(subtitle, "countSub", wrap=True)
        box.addWidget(self.sub)
        layout.addLayout(box, 1)
        self._flash = QTimer(self)
        self._flash.setSingleShot(True)
        self._flash.timeout.connect(lambda: self.setStyleSheet(""))

    def compact(self):
        """Less padding above and below, where a page needs the height (the Game view)."""
        self._box.setContentsMargins(0, 8, 0, 8)
        return self

    def set_value(self, value, flash=False):
        text = UNKNOWN_VALUE if value is None else fmt(value)
        if text != self.value.text() and flash:
            self.setStyleSheet(f"#countCard {{ border: 1px solid {self.color}; background: {theme.rgba(self.color, 0.08)}; }}")
            self._flash.start(900)
        self.value.setText(text)


class StatTile(QFrame):
    """One compact figure. A value that is not known shows as a dash, never as zero."""

    def __init__(self, title, sub=""):
        super().__init__()
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(label(title, "countLabel"))
        self.value = label(UNKNOWN_VALUE, "statValue")
        layout.addWidget(self.value)
        self.sub = label(sub, "countSub", wrap=True)
        layout.addWidget(self.sub)
        self._layout = layout

    def compact(self):
        self._layout.setContentsMargins(14, 5, 14, 5)
        self._layout.setSpacing(0)
        return self

    def set_value(self, value, sub=None):
        self.value.setText(UNKNOWN_VALUE if value is None else str(value))
        if sub is not None:
            self.sub.setText(sub)


class PreviewPanel(QFrame):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.view = QLabel("Start counting to see the video here")
        self.view.setObjectName("previewBox")
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(320, 180)
        self.view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)     # the picture fits the box: left to itself, it would make the page longer each time
        layout.addWidget(self.view, 1)
        self.caption = label("Preview: what the counter analyses (a few pictures per second).", "hint", wrap=True)
        layout.addWidget(self.caption)
        self.image = None

    def show_frame(self, width, height, data):
        self.image = QImage(data, width, height, 3 * width, QImage.Format_RGB888).copy()
        self._render()

    def clear(self, text="Start counting to see the video here"):
        self.image = None
        self.view.setPixmap(QPixmap())
        self.view.setText(text)

    def _render(self):
        if self.image is None:
            return
        size = self.view.size() - QSize(4, 4)
        self.view.setPixmap(QPixmap.fromImage(self.image).scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()


# ==================================================================
# dialogs
# ==================================================================

class CountsDialog(QDialog):
    """Set the counter (also: start from the chests already opened)."""

    def __init__(self, parent, certain, approx):
        super().__init__(parent)
        self.setWindowTitle("Edit counts")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(label("Set the counter", "cardTitle"))
        layout.addWidget(label("Use this to start from the chests you already opened before using the counter, or to "
                               "correct a mistake. New chests are added on top.", "hint", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.approx = QSpinBox()
        self.certain = QSpinBox()
        for spin, value in ((self.approx, approx), (self.certain, certain)):
            spin.setRange(0, C.MAX_STARTING_COUNT)
            spin.setGroupSeparatorShown(True)
            spin.setValue(value)
            spin.setMinimumWidth(140)
        grid.addWidget(label("Chests opened (APPROX, the total)"), 0, 0)
        grid.addWidget(self.approx, 0, 1)
        grid.addWidget(label("Confirmed chests (CERTAIN)"), 1, 0)
        grid.addWidget(self.certain, 1, 1)
        layout.addLayout(grid)
        layout.addWidget(label("CERTAIN is part of APPROX, so it cannot be higher. Chests opened before the counter ran "
                               "were not seen by it: leave CERTAIN at 0 for those.", "hint", wrap=True))
        self.problem = label("", "hint")
        self.problem.setStyleSheet(f"color: {theme.REJECT};")
        layout.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.approx.valueChanged.connect(self._check)
        self.certain.valueChanged.connect(self._check)

    def _check(self):
        bad = self.certain.value() > self.approx.value()
        self.problem.setText("CERTAIN cannot be higher than APPROX." if bad else "")
        return not bad

    def _accept(self):
        if self._check():
            self.accept()


class VideoDialog(QDialog):
    """Count the chests in a recorded gameplay video (the `video` command). Never touches the live counter."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Analyse a recording")
        self.resize(640, 520)
        self.worker = Worker()
        self.duration = None
        self.span = None                                                # (first, last) second of video to analyse
        self.eta = Eta()
        self.result_dir = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(label("Count the chests in a recorded gameplay video", "cardTitle"))
        layout.addWidget(label("Runs faster than real time. Your live counter and OBS overlay are not changed; the result "
                               "files go to the video_output folder.", "hint", wrap=True))
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText("Choose a video file (.mp4, .mkv, .mov ...)")
        row.addWidget(self.path, 1)
        row.addWidget(button("Browse...", on_click=self._browse))
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.state = label("", "hint")
        layout.addWidget(self.state)
        counts = QHBoxLayout()
        self.certain = CountCard("CERTAIN", "confirmed", theme.CERTAIN)
        self.approx = CountCard("APPROX", "estimated total", theme.APPROX)
        counts.addWidget(self.certain)
        counts.addWidget(self.approx)
        layout.addLayout(counts)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(LOG_LIMIT)
        layout.addWidget(self.log, 1)
        bottom = QHBoxLayout()
        self.open_results = button("Open results folder", on_click=lambda: open_path(self.result_dir))
        self.open_results.setEnabled(False)
        bottom.addWidget(self.open_results)
        bottom.addStretch(1)
        self.go = button("Start", "primary", on_click=self._toggle)
        self.go.setEnabled(False)
        bottom.addWidget(self.go)
        bottom.addWidget(button("Close", on_click=self.close))
        layout.addLayout(bottom)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._pump)
        self.timer.start(60)

    def _browse(self):
        start = str(Path.home() / "Videos")
        name, _ = QFileDialog.getOpenFileName(self, "Choose a gameplay video", start,
                                              "Videos (*.mp4 *.mkv *.mov *.avi *.flv *.ts *.webm);;All files (*)")
        if name:
            self.path.setText(name)
            self.go.setEnabled(True)

    def _toggle(self):
        if self.worker.running():
            self.worker.stop()
            self.go.setEnabled(False)
            self.state.setText("Stopping...")
            return
        self.log.clear()
        self.certain.set_value(0)
        self.approx.set_value(0)
        self.progress.setValue(0)
        self.open_results.setEnabled(False)
        self.eta = Eta()
        try:
            self.worker.start(["video", self.path.text(), "--gui"])
        except OSError as error:
            show_error(self, f"The analysis could not start ({error}).")
            return
        self.go.setText("Stop")
        restyle(self.go, "danger")
        self.state.setText("Starting...")

    def _pump(self):
        for message in self.worker.drain():
            kind = message.get("type")
            if kind == "video_start":
                self.duration = message.get("duration")
                first = message.get("start") or 0.0
                last = message.get("until") or self.duration
                self.span = (first, last) if last else None
                self.state.setText(f"Analysing {message.get('name', '')} ..."
                                   + ("" if self.span else "  (the video's length is unknown: no time estimate)"))
            elif kind == "progress":
                t = message.get("t", 0)
                if self.span and self.span[1] > self.span[0]:
                    done, total = t - self.span[0], self.span[1] - self.span[0]
                    self.progress.setRange(0, 1000)
                    self.progress.setValue(int(1000 * min(done / total, 1.0)))
                    left = describe(self.eta.update(done, total))
                    self.state.setText(f"{clock_text(t)} of {clock_text(self.span[1])} analysed   ·   "
                                       + (left or "measuring speed..."))
                else:
                    self.progress.setRange(0, 0)
                    self.state.setText(f"{clock_text(t)} analysed")
                self.certain.set_value(message.get("certain", 0))
                self.approx.set_value(message.get("approx", 0))
            elif kind == "event":
                if message.get("verdict") in ("certain", "approx"):
                    for debug_only, html in log_entries(message):
                        if not debug_only:
                            self.log.appendHtml(html)
                if message.get("certain") is not None:
                    self.certain.set_value(message["certain"], flash=True)
                    self.approx.set_value(message["approx"], flash=True)
            elif kind == "finished":
                self.progress.setRange(0, 1000)
                self.progress.setValue(1000 if not message.get("stopped_early") else self.progress.value())
                self.certain.set_value(message["certain"])
                self.approx.set_value(message["approx"])
                self.result_dir = message.get("obs_dir")
                self.open_results.setEnabled(bool(self.result_dir))
                early = " (stopped early: only the part already analysed is counted)" if message.get("stopped_early") else ""
                self.state.setText(f"Finished: {message.get('analysed', '')[:-3]} of video in {message.get('minutes', 0)} min{early}. "
                                   "APPROX is the estimated total and already includes CERTAIN.")
            elif kind in ("error", "warn"):
                for _, html in log_entries(message):
                    self.log.appendHtml(html)
                if kind == "error":
                    self.state.setText("Could not analyse this file - see the message below.")
            elif kind == "exit":
                self.go.setText("Start again")
                restyle(self.go, "primary")
                self.go.setEnabled(True)
                self.progress.setRange(0, 1000)

    def closeEvent(self, event):
        if self.worker.running():
            if not ask(self, "Stop the analysis?", "The video is still being analysed. Stop and close?", "Stop and close"):
                event.ignore()
                return
            self.worker.stop()
            deadline = time.monotonic() + 5
            while self.worker.running() and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.05)
            self.worker.kill()
        self.timer.stop()
        super().closeEvent(event)


# ==================================================================
# pages
# ==================================================================

class ReviewDialog(QDialog):
    """Runs `review --gui` over the captures folder: which capture, how much video, time left, then each report."""

    MODES = {"events": "around chest decisions and marks", "marks": "around marks", "session": "whole session"}

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Review captures")
        self.resize(840, 640)
        self.worker = Worker()
        self.eta = Eta()
        self.total = None
        self.failed = None
        self.finished = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        self.title = label("Reviewing captures", "cardTitle")
        layout.addWidget(self.title)
        layout.addWidget(label("Every diagnostic capture is replayed through the current detector and compared with what was "
                               "counted live and with your labels (labels.csv in each capture folder).", "hint", wrap=True))
        self.current = label("Starting...", wrap=True)
        layout.addWidget(self.current)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)                                    # busy until the total is known
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.detail = label("", "hint")
        layout.addWidget(self.detail)
        self.text = QPlainTextEdit()
        self.text.setObjectName("report")
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addWidget(button("Open captures folder", on_click=self._open_folder))
        row.addStretch(1)
        row.addWidget(button("Copy report", on_click=lambda: QApplication.clipboard().setText(self.text.toPlainText())))
        self.stop = button("Stop", "danger", on_click=self._stop)
        row.addWidget(self.stop)
        row.addWidget(button("Close", on_click=self.close))
        layout.addLayout(row)
        try:
            self.worker.start(["review", "--gui"])
        except OSError as error:
            self._fail(f"The review could not start ({error}).")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._pump)
        self.timer.start(100)

    def _open_folder(self):
        cfg, _ = load_cfg()
        open_path(paths.APP_DIR / cfg["capture"]["dir"])

    def _stop(self):
        self.worker.stop()
        self.stop.setEnabled(False)
        self.current.setText("Stopping...")

    def _fail(self, text):
        self.failed = text
        self.title.setText("Review failed")
        self.title.setStyleSheet(f"color: {theme.REJECT};")
        self.current.setText(text)
        self.progress.setRange(0, 1000)
        self.stop.setEnabled(False)

    def _show_progress(self, done):
        if not self.total:
            return
        self.progress.setRange(0, 1000)
        self.progress.setValue(int(1000 * min(done / self.total, 1.0)))
        left = describe(self.eta.update(done, self.total))
        self.detail.setText(f"{clock_text(done)} of {clock_text(self.total)} of recorded video reviewed   ·   "
                            + (left or "measuring speed..."))

    def _pump(self):
        for m in self.worker.drain():
            kind = m.get("type")
            if kind == "review_start":
                self.total = m.get("total_seconds") or 0.0
                if not m.get("captures"):
                    self._fail("No finished captures were found.")
            elif kind == "review_capture":
                mode = self.MODES.get(m.get("mode"), m.get("mode") or "")
                self.current.setText(f"Capture {m['index']} of {m['count']}:  {m['name']}   ·   {mode}   ·   "
                                     f"{clock_text(m.get('seconds', 0))} of video in {m.get('clips', '?')} clip(s)")
                self._show_progress(m.get("done", 0.0))
            elif kind == "review_progress":
                self._show_progress(m.get("done", 0.0))
            elif kind == "review_report":
                self.text.appendPlainText(m.get("text", "").rstrip() + "\n")
            elif kind == "review_finished":
                self.finished = True
                self.title.setText("Review finished")
                self.title.setStyleSheet(f"color: {theme.CERTAIN};")
                self.current.setText(f"{m.get('captures', 0)} capture(s) reviewed in {m.get('minutes', 0)} min. "
                                     "Reports are also saved as review.txt in each capture folder.")
                self.progress.setRange(0, 1000)
                self.progress.setValue(1000)
                self.detail.setText("")
            elif kind == "review_stopped":
                self.finished = True
                self.title.setText("Review stopped")
                self.current.setText("Stopped. The reports above are complete; the rest was not reviewed.")
                self.detail.setText("")
            elif kind == "error":
                self._fail(str(m.get("text", "The review failed.")))
            elif kind == "exit":
                self.stop.setEnabled(False)
                if not self.finished and not self.failed:
                    tail = "\n".join(self.worker.stderr_tail[-6:])
                    self._fail("The review stopped unexpectedly." + (f"\n{tail}" if tail else ""))

    def closeEvent(self, event):
        if self.worker.running():
            self.worker.stop()
            deadline = time.monotonic() + 5
            while self.worker.running() and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.05)
            self.worker.kill()
        self.timer.stop()
        super().closeEvent(event)


class Dashboard(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        layout = page_layout(self, "Dashboard", "Counts the chests in Fortnite video - a livestream, a screen or OBS - "
                                                "and keeps the numbers (also in a text file OBS can show on stream).")
        header = layout.itemAt(0).widget()
        layout.removeWidget(header)
        top = QHBoxLayout()
        top.addWidget(header)
        top.addStretch(1)
        self.pill = label("", "pill")
        top.addWidget(self.pill, 0, Qt.AlignVCenter)
        layout.insertLayout(0, top)

        # error banner
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 10, 10, 10)
        self.banner_text = label("", "bannerText", wrap=True)
        self.banner_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        banner_layout.addWidget(self.banner_text, 1)
        banner_layout.addWidget(button("Dismiss", on_click=self.banner.hide), 0, Qt.AlignTop)
        self.banner.hide()
        layout.addWidget(self.banner)

        # what the last update did: shown once, never in the error colours unless something needs attention
        self.notice = QFrame()
        self.notice.setObjectName("notice")
        notice_layout = QHBoxLayout(self.notice)
        notice_layout.setContentsMargins(14, 10, 10, 10)
        self.notice_text = label("", wrap=True)
        notice_layout.addWidget(self.notice_text, 1)
        notice_layout.addWidget(button("Dismiss", on_click=self.notice.hide), 0, Qt.AlignTop)
        self.notice.hide()
        layout.addWidget(self.notice)

        # a verified update is available (v0.4.0, UX-01): one quiet line, never a dialog, gone for this version with Later
        self.update_notice = QFrame()
        self.update_notice.setObjectName("notice")
        update_row = QHBoxLayout(self.update_notice)
        update_row.setContentsMargins(14, 8, 10, 8)
        self.update_notice_text = label("", wrap=True)
        update_row.addWidget(self.update_notice_text, 1)
        update_row.addWidget(button("What's new", on_click=lambda: win.open_update_dialog()), 0, Qt.AlignVCenter)
        self.update_later = button("Later", on_click=lambda: win.dismiss_update_notice())
        update_row.addWidget(self.update_later, 0, Qt.AlignVCenter)
        self.update_notice.hide()
        layout.addWidget(self.update_notice)

        # three views of one session (v0.3.0). The status pill, banner and notice above stay visible in all of them.
        segments = QHBoxLayout()
        segments.setSpacing(4)
        self.view_buttons = QButtonGroup(self)
        self.views = QStackedWidget()
        pages = []
        for index, (name, tip) in enumerate(DASHBOARD_VIEWS):
            view_button = button(name, "segment", tip=tip)
            view_button.setCheckable(True)
            self.view_buttons.addButton(view_button, index)
            segments.addWidget(view_button)
            page = QWidget()
            page.setObjectName("page")
            page_box = QVBoxLayout(page)
            page_box.setContentsMargins(0, 4, 0, 0)
            page_box.setSpacing(14)
            self.views.addWidget(page)
            pages.append(page_box)
        overview, game, console = pages
        segments.addStretch(1)
        layout.addLayout(segments)
        layout.addWidget(hline())
        layout.addWidget(self.views, 1)
        self.view_buttons.button(OVERVIEW_VIEW).setChecked(True)
        self.view_buttons.idClicked.connect(self.show_view)
        self._unread_warnings = 0

        # count profile (v0.2.2): whose chests these are. One profile counts at a time.
        prow = QHBoxLayout()
        prow.setSpacing(8)
        prow.addWidget(label("Profile"))
        self.profile = QComboBox()
        self.profile.setMinimumWidth(220)
        self.profile.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.profile.setToolTip("Each profile keeps its own counts and its own video source (for example one profile per "
                                "streamer). One profile counts at a time; OBS always shows the selected profile.")
        self.profile.activated.connect(win.switch_profile)
        prow.addWidget(self.profile, 1)
        self.profile_new = button("New profile...", tip="A new profile with its own counts, starting at 0",
                                  on_click=win.new_profile)
        self.profile_rename = button("Rename...", tip="Change the name of the selected profile (its counts stay)",
                                     on_click=win.rename_profile)
        self.profile_delete = button("Delete...", tip="Remove the selected profile (its counts are kept in a backup "
                                                      "file)", on_click=win.delete_profile)
        for widget in (self.profile_new, self.profile_rename, self.profile_delete):
            prow.addWidget(widget)
        overview.addLayout(prow)

        # the two numbers
        counts = QHBoxLayout()
        counts.setSpacing(14)
        self.certain = CountCard("CERTAIN", "Strongest evidence only. Can stay low on a small HUD", theme.CERTAIN)
        self.approx = CountCard("APPROX", "Best estimate of chests opened. Already includes CERTAIN", theme.APPROX)
        counts.addWidget(self.certain, 1)
        counts.addWidget(self.approx, 1)
        actions = QVBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(button("Edit counts...", tip="Start from the chests you already opened, or correct the counter",
                                 on_click=win.edit_counts))
        actions.addWidget(button("Reset...", tip="Set both counts to 0", on_click=win.reset_counts))
        adjust = QHBoxLayout()
        adjust.setSpacing(6)
        self.minus = button("−1", tip="Take one chest off APPROX", on_click=lambda: win.correct_chest(-1))
        self.plus = button("+1", tip="Add one chest to APPROX. CERTAIN does not change, because the counter did not confirm it.", on_click=lambda: win.correct_chest(1))
        adjust.addWidget(self.minus)
        adjust.addWidget(self.plus)
        actions.addLayout(adjust)
        actions.addStretch(1)
        counts.addLayout(actions)
        overview.addLayout(counts)
        self.correction_row = QWidget()                       # only while corrections stand on this counter
        correction_layout = QHBoxLayout(self.correction_row)
        correction_layout.setContentsMargins(0, 0, 0, 0)
        correction_layout.addWidget(label("Corrections:", "hint"))
        self.correction_text = label("", "hint")
        self.correction_text.setStyleSheet(f"color: {theme.TEXT};")
        correction_layout.addWidget(self.correction_text)
        correction_layout.addStretch(1)
        correction_layout.addWidget(label("Why?", "hint"))
        self.correction_reason = QComboBox()
        self.correction_reason.setToolTip("Optional. Only \"a visible chest the counter missed\" and \"counted something that was not a chest\" say anything about the detector.")
        self.correction_reason.activated.connect(win.correction_reason_chosen)
        correction_layout.addWidget(self.correction_reason)
        self.correction_undo = button("Undo", "link", tip="Undo the last correction. It stays in the history as undone.", on_click=win.undo_correction)
        correction_layout.addWidget(self.correction_undo)
        self.correction_row.hide()
        overview.addWidget(self.correction_row)
        types = QHBoxLayout()                                # v0.2.2: read-only chest-type split of the APPROX total
        types.addWidget(label("Chest types:", "hint"), 0, Qt.AlignTop)
        self.types = label("", "hint", wrap=True)
        self.types.setToolTip("How the counted chests split by type (APPROX, the total). Read from each chest's pop-up "
                              "line: CHEST, RARE CHEST or SPRITE CHEST - 'unknown type' when the line could not be read. "
                              "'Not classified' = chests counted before v0.2.2, or set with Edit counts. "
                              "OBS still shows only the two totals.")
        types.addWidget(self.types, 1)
        overview.addLayout(types)
        self.match_row = QWidget()                           # v0.3.0: read-only, and only while match tracking is on
        match_layout = QHBoxLayout(self.match_row)
        match_layout.setContentsMargins(0, 0, 0, 0)
        match_layout.addWidget(label("Match (experimental):", "hint"), 0, Qt.AlignTop)
        self.match = label("", "hint", wrap=True)
        self.match.setToolTip("What match tracking sees right now. It only reports: it never changes your counts or what OBS shows. "
                              "\"Partial\" means part of the match was not seen, so it will not count as a complete match.")
        match_layout.addWidget(self.match, 1)
        self.match_row.hide()
        overview.addWidget(self.match_row)
        viewers = QHBoxLayout()
        viewers.addWidget(label("Viewers see:", "hint"), 0, Qt.AlignTop)
        self.viewers = label("", "hint", wrap=True)
        self.viewers.setStyleSheet(f"color: {theme.TEXT};")
        viewers.addWidget(self.viewers, 1)
        viewers.addWidget(button("Change what viewers see", "link", on_click=lambda: win.show_page(win.overlay)))
        overview.addLayout(viewers)
        self.obs_line = label("", "hint", wrap=True)          # OBS WebSocket output status (only while it is on)
        self.obs_line.hide()
        overview.addWidget(self.obs_line)

        # source + start
        box, box_layout = card()
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(label("Video source"))
        self.source = QComboBox()
        self.source.setMinimumWidth(220)
        self.source.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.source.setMinimumContentsLength(24)
        self.source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self.source, 1)
        self.refresh = button("Refresh", tip="Look for video devices and screens again", on_click=win.refresh_sources)
        row.addWidget(self.refresh)
        self.start = button("Start counting", "primary", on_click=win.toggle_counting)
        self.start.setMinimumWidth(160)
        row.addWidget(self.start)
        box_layout.addLayout(row)
        self.url_row = QWidget()                            # only for "Livestream URL"
        url_layout = QVBoxLayout(self.url_row)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(4)
        self.url = QLineEdit()
        self.url.setPlaceholderText("Paste the live link, e.g.  https://www.twitch.tv/channel  or  "
                                    "https://www.youtube.com/watch?v=...")
        url_layout.addWidget(self.url)
        stab = QHBoxLayout()
        stab.addWidget(label("Stream stability"))
        self.stability = QComboBox()
        for key, name, _ in settings.STREAM_STABILITY_CHOICES:
            self.stability.addItem(name, key)
        stab.addWidget(self.stability, 1)
        url_layout.addLayout(stab)
        self.stability_hint = label("", "hint", wrap=True)
        url_layout.addWidget(self.stability_hint)
        self.stability.currentIndexChanged.connect(lambda _: self.stability_hint.setText(
            next(text for key, _, text in settings.STREAM_STABILITY_CHOICES if key == self.stability.currentData())
            + " A bigger buffer cannot bring back video the platform never delivered (outages, ad breaks)."))
        self.url_note = label("Counts from the public stream as viewers get it, a few seconds behind, at 720p - no OBS "
                              "or browser needed. Twitch and YouTube; the stream must be live and public. Video can "
                              "arrive in bursts or pause to buffer. If the connection drops, the app reconnects by itself, "
                              "keeps your counts and tells you which part could not be seen.", "hint", wrap=True)
        url_layout.addWidget(self.url_note)
        self.url_row.hide()
        box_layout.addWidget(self.url_row)
        self.source.currentIndexChanged.connect(lambda _: self.url_row.setVisible(
            (self.source.currentData() or {}).get("source") == "stream"))
        self.source.currentIndexChanged.connect(lambda _: win.update_source_hint())
        self.source_hint = label("", "hint", wrap=True)
        box_layout.addWidget(self.source_hint)
        box_layout.addWidget(hline())
        row = QHBoxLayout()
        self.metrics = label("Not counting.", "metrics", wrap=True)
        row.addWidget(self.metrics, 1)
        self.show_mini = button("Live preview", "toggle", tip="Show or hide the video the counter is analysing. Counting carries on either way.")
        self.show_mini.setCheckable(True)
        row.addWidget(self.show_mini)
        self.analyse = button("Analyse a recording...", tip="Count the chests in a video file (does not change your counter)",
                              on_click=win.analyse_video)
        row.addWidget(self.analyse)
        box_layout.addLayout(row)
        overview.addWidget(box)
        self.mini_preview = PreviewPanel()
        self.mini_preview.caption.hide()
        self.mini_preview.view.setMinimumSize(240, 120)
        overview.addWidget(self.mini_preview, 100)
        overview.addStretch(1)
        self._build_game(win, game)
        self._build_console(win, console)

    def _build_game(self, win, game):
        # Top: what match tracking sees beside the live preview, so the picture no longer takes a row of its own (the maintainer's layout).
        top = QHBoxLayout()
        top.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(8)
        box, box_layout = card()
        box_layout.setContentsMargins(18, 10, 18, 10)          # the Game view needs its height for the numbers and the correction row
        box_layout.setSpacing(4)
        box_layout.addWidget(label("Match status (experimental)", "cardTitle"))
        self.game_status = label("", "gameStatus", wrap=True)             # on its own line, so it does not wrap beside the title (UX-05)
        box_layout.addWidget(self.game_status)
        self.game_doubt = label("", "pill")                  # why this match is partial or unconfirmed: small, beside the facts (UX-05)
        self.game_doubt.hide()
        box_layout.addWidget(self.game_doubt, 0, Qt.AlignLeft)
        box.setToolTip("Followed from the screen once a second. It only reports: it never changes your counts or what OBS shows.")
        self.game_hint = label("", "hint", wrap=True)
        box_layout.addWidget(self.game_hint)
        row = QHBoxLayout()
        self.game_settings = button("Open Settings", "link", on_click=lambda: win.show_page(win.settings_page))
        row.addWidget(self.game_settings)
        row.addStretch(1)
        box_layout.addLayout(row)
        left.addWidget(box)
        tiles = QGridLayout()
        tiles.setSpacing(8)
        self.game_active = StatTile("ACTIVE PLAY", "Alive on the map")
        self.game_seen = StatTile("SEEN SO FAR", "This match, on screen")
        self.game_unclear = StatTile("UNCLEAR", "No picture, or not the game")
        self.game_start = StatTile("START SEEN", "From before the bus")
        self.game_language = StatTile("LANGUAGE", "From text on screen")
        for index, tile in enumerate((self.game_active, self.game_seen, self.game_unclear, self.game_start, self.game_language)):
            tiles.addWidget(tile.compact(), index // 3, index % 3)
        left.addLayout(tiles)
        left.addStretch(1)
        top.addLayout(left, 3)
        right = QVBoxLayout()                                 # the toggle stays put; with the picture hidden this column shrinks to it
        right.setSpacing(6)
        self.show_preview = button("Live preview", "toggle", tip="The video the counter is analysing")
        self.show_preview.setCheckable(True)
        right.addWidget(self.show_preview, 0, Qt.AlignRight)
        self.preview = PreviewPanel()
        self.preview.view.setMinimumSize(240, 135)
        right.addWidget(self.preview, 1)
        top.addLayout(right, 2)
        self._game_top = top
        game.addLayout(top)

        numbers = QHBoxLayout()
        numbers.setSpacing(12)
        self.game_certain = CountCard("MATCH CERTAIN", "", theme.CERTAIN)
        self.game_approx = CountCard("MATCH APPROX", "", theme.APPROX)
        self.game_certain.setToolTip("Only the strongest evidence. Can stay low on a small HUD or blurry video.")
        self.game_approx.setToolTip("Best estimate of chests opened in this match. Already includes CERTAIN.")
        self.game_rate = CountCard("DETECTED CHESTS / MIN", "", theme.APPROX)
        self._match_shown = None                              # (match number, certain, approx): a highlight means this match's count went up
        for tile in (self.game_certain, self.game_approx, self.game_rate):
            numbers.addWidget(tile.compact(), 1)
        game.addLayout(numbers)
        manual = QHBoxLayout()                                # v0.3.0 M9H: corrections made for this match, through the same path as Overview's
        fix = label("Fix this match:", "hint")
        fix.setToolTip("A chest the counter missed, a broken chest, or something it should not have counted, in the match on screen (between matches, "
                       "the one that just ended). Your total changes too.")
        manual.addWidget(fix)
        self.game_minus = button("−1", tip="Take one chest off this match and off APPROX", on_click=lambda: win.correct_match_chest(-1))
        self.game_plus = button("+1", tip="Add a chest to this match and to APPROX, a broken chest say. It stays a manual chest: never CERTAIN, never a detected type.",
                                on_click=lambda: win.correct_match_chest(1))
        self.game_undo = button("Undo", "link", tip="Undo your last correction. It stays in the history as undone.", on_click=win.undo_correction)
        self.game_reason = QComboBox()                        # what a +1 is for, saved with it as a fixed id
        for key, text in CORRECTION_WHY[1]:
            self.game_reason.addItem(text, key)
        self.game_reason.setToolTip("What the +1 is for. Choose Broken chest only when you know one was broken: they are counted apart in Analytics. "
                                    "Only \"a visible chest the counter missed\" says the counter failed.")
        self.game_reason.setCurrentIndex(max(self.game_reason.findData("manual"), 0))      # a broken chest only when you say so: these records feed later statistics
        self.game_reason.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)       # the longest reason would push the page wider than the window
        self.game_reason.setMinimumContentsLength(20)
        for widget in (self.game_minus, self.game_plus, self.game_reason, self.game_undo):
            manual.addWidget(widget)
        manual.addStretch(1)
        game.addLayout(manual)
        self.game_target = None                               # the match the buttons act on: the open one, else the last one of this run
        self.game_manual_by_match = {}                        # match number -> [+1s, -1s] standing, this run
        self._game_last, self._game_last_match = ({}, None), None
        self.game_last = label("", "hint", wrap=True)
        self.game_last.hide()
        game.addWidget(self.game_last)
        game.addStretch(1)
        self.show_preview.toggled.connect(self._preview_toggled)
        self.show_mini.toggled.connect(self._preview_toggled)
        self.source.currentIndexChanged.connect(lambda _: self._panels())
        self._show_match_numbers({}, None)

    def _build_console(self, win, console):
        box, box_layout = card()
        row = QHBoxLayout()
        row.addWidget(label("Diagnostic recording"))
        self.rec_mode = QComboBox()
        for text, mode in RECORDING_CHOICES:
            self.rec_mode.addItem(text, mode)
        self.rec_mode.setToolTip("Keeps the video the counter analysed so a missed chest can be replayed and checked. "
                                 "Can be changed while counting; the counts are not affected.")
        row.addWidget(self.rec_mode, 1)
        self.mark = button("Mark moment   Ctrl+Alt+M", on_click=win.mark_moment)
        row.addWidget(self.mark)
        box_layout.addLayout(row)
        row = QHBoxLayout()
        self.rec_status = label("", "hint", wrap=True)
        row.addWidget(self.rec_status, 1)
        self.console_counts = label(console_counts_text(0, 0), "metrics")
        self.console_counts.setTextFormat(Qt.RichText)
        self.console_counts.setToolTip("Your current counts. APPROX already includes CERTAIN.")
        row.addWidget(self.console_counts, 0, Qt.AlignTop | Qt.AlignRight)
        box_layout.addLayout(row)
        console.addWidget(box)

        row = QHBoxLayout()
        row.addWidget(label("Activity", "cardTitle"))
        row.addStretch(1)
        self.detail = QComboBox()
        self.detail.addItem("Normal detail", "normal")
        self.detail.addItem("Debug detail", "debug")
        self.detail.setToolTip("Debug adds every candidate, the full reason for each decision and status lines")
        row.addWidget(self.detail)
        self.clear = button("Clear", on_click=win.clear_log)
        row.addWidget(self.clear)
        self.open_logs = button("Logs folder", tip="Session logs (send these when reporting a problem)",
                                on_click=win.open_logs)
        row.addWidget(self.open_logs)
        console.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(LOG_LIMIT)
        self.log.setPlaceholderText("Chests appear here as they are counted: green = certain, yellow = estimated only, "
                                    "red = looked like a chest but was not counted.")
        self.log.setMinimumHeight(220)
        console.addWidget(self.log, 1)
        self.detail.currentIndexChanged.connect(lambda _: win.render_log())

    def _panels(self):
        on = self.show_preview.isChecked()
        counting = self.win.mode in ("connecting", "counting", "stopping")
        link_help_showing = (self.source.currentData() or {}).get("source") == "stream" and not counting       # needed before starting, and it is tall
        self.preview.setVisible(on)
        self._game_top.setStretch(1, 2 if on else 0)
        self.mini_preview.setVisible(on and not link_help_showing)
        self.win.preview_visibility_changed()

    def set_preview_on(self, on):
        """One setting behind both buttons."""
        for toggle in (self.show_preview, self.show_mini):
            toggle.blockSignals(True)
            toggle.setChecked(on)
            toggle.blockSignals(False)
        self._panels()

    def _preview_toggled(self, on):
        self.set_preview_on(on)
        self.win.remember_preview(on)

    def show_view(self, index):
        """Only changes what is on screen: counting, recognition and history do not know about it."""
        self.views.setCurrentIndex(index)
        self.view_buttons.button(index).setChecked(True)
        if index == CONSOLE_VIEW:
            self._unread_warnings = 0
            self._label_console()
        self.win.preview_visibility_changed()

    def note_warning(self):
        """The log is out of sight on the other views, so its tab says when something needs reading."""
        if self.views.currentIndex() != CONSOLE_VIEW:
            self._unread_warnings += 1
            self._label_console()

    def _label_console(self):
        self.view_buttons.button(CONSOLE_VIEW).setText(f"Console ({self._unread_warnings})" if self._unread_warnings else "Console")

    def show_game(self, message, text, color):
        match = message.get("match") or {}
        state, calm, note, note_color = game_status_parts(text, color)
        self.game_status.setText(state)
        self.game_status.setStyleSheet(f"color: {calm};")
        self.game_doubt.setText(note)
        self.game_doubt.setStyleSheet(theme.pill_style(note_color))
        self.game_doubt.setVisible(bool(note))
        self.game_hint.setText("")                             # the same words are the card's tooltip: the line is kept for what needs reading
        self.game_hint.hide()
        self.game_settings.hide()
        self.game_active.set_value(match_clock(match.get("active_seconds")))
        self.game_seen.set_value(match_clock(match.get("observed_seconds")))
        self.game_unclear.set_value(match_clock(match.get("uncertain_seconds")))
        self.game_start.set_value({True: "Yes", False: "No"}.get(match.get("observed_from_start")))
        self.game_language.set_value({True: "English", False: "Not confirmed"}.get(match.get("english_confirmed")))
        last = message.get("last_match")
        self.game_target = match.get("match_number") or (last or {}).get("match_number")
        self._game_last, self._game_last_match = (match, message.get("chests")), last
        self._show_match_numbers(match, message.get("chests"))
        self._show_last_match(last)

    def refresh_game_manual(self):
        """After a correction: show it at once rather than at the next sample."""
        self._show_match_numbers(*self._game_last)
        self._show_last_match(self._game_last_match)

    def _show_match_numbers(self, match, chests):
        """This match only, from its own chests. Nothing is shown until it is known to be a match: a zero would say more than is known."""
        known = match.get("english_confirmed") is True and chests is not None
        added, removed = self.game_manual_by_match.get(match.get("match_number"), (0, 0))
        if known:
            include = bool(load_cfg()[0]["app"]["analytics_include_manual"])
            detected = chests
            chests = {"certain": detected["certain"], "approx": max(detected["approx"] + added - removed, detected["certain"])}
            rated = {"certain": detected["certain"], "approx": max(detected["approx"] - removed + (added if include else 0), detected["certain"])}
        note = match_note(match) + (f"  ·  incl. {manual_text(added, removed)}" if known and (added or removed) else "")
        now = (match.get("match_number"), chests["certain"], chests["approx"]) if known else None
        before = self._match_shown if now and self._match_shown and self._match_shown[0] == now[0] else None
        self._match_shown = now
        self.game_certain.set_value(chests["certain"] if known else None, flash=bool(before) and chests["certain"] > before[1])
        self.game_approx.set_value(chests["approx"] if known else None, flash=bool(before) and chests["approx"] > before[2])
        self.game_approx.sub.setText(note)
        self.game_certain.sub.setText(match_note(match))                  # manual chests never touch CERTAIN
        rate = match_analytics.match_rate(rated["certain"], rated["approx"], match.get("active_seconds")) if known else None
        self.game_rate.title.setText("CHESTS / MIN WITH YOUR +1s" if known and include else "DETECTED CHESTS / MIN")
        counting = self.win.mode == "counting" and self.game_target is not None
        self.game_plus.setEnabled(counting)
        self.game_minus.setEnabled(counting and (not known or chests["approx"] > chests["certain"]))

        self.show_game_rate(f"{rate.approx_per_minute:.2f}" if rate else None, "APPROX per minute of play" if rate else "Needs a minute of play" if known else "")

    def show_game_rate(self, text, hint):
        self.game_rate.value.setText(UNKNOWN_VALUE if text is None else text)
        self.game_rate.sub.setText(hint)

    def _show_last_match(self, last):
        added, removed = self.game_manual_by_match.get((last or {}).get("match_number"), (0, 0))
        if last and (added or removed):
            last = {**last, "approx": max(last["approx"] + added - removed, last["certain"])}
        text = last_match_text(last) + (f"   ·   incl. {manual_text(added, removed)}" if last_match_text(last) and (added or removed) else "")
        if text:                                             # a weak record does not replace the last real one
            self.game_last.setText(text)
            self.game_last.show()

    def show_game_idle(self, text, hint, offer_settings):
        self.game_status.setText(text)
        self.game_status.setStyleSheet(f"color: {theme.MUTED};")
        self.game_doubt.hide()
        self.game_hint.setText(hint)
        self.game_hint.setVisible(bool(hint))
        self.game_settings.setVisible(offer_settings)
        for tile in (self.game_active, self.game_seen, self.game_unclear, self.game_start, self.game_language):
            tile.set_value(None)
        self.game_target, self._game_last, self._game_last_match = None, ({}, None), None     # no match known: the buttons act on nothing
        self._show_match_numbers({}, None)

    def set_pill(self, text, color):
        self.pill.setText(f"●  {text}")
        self.pill.setStyleSheet(theme.pill_style(color))

    def show_banner(self, text):
        self.banner_text.setText(text)
        self.banner.show()

    def show_notice(self, text, color):
        self.notice_text.setText(text)
        self.notice_text.setStyleSheet(f"color: {color};")
        self.notice.show()


class OverlayPage(QWidget):
    """Configure Counter.bat, as a page: what OBS shows (always the same file) and its wording."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        layout = page_layout(self, "Overlay", "What your viewers see. The counter writes ONE text file; OBS shows it with a "
                                              "Text source. Fonts, colours and size are set in OBS.")
        box, box_layout = card("What OBS shows")
        self.modes = QButtonGroup(self)
        self.mode_buttons = {}
        for i, mode in enumerate(("stacked", "inline", "approx", "certain")):
            radio = QRadioButton()
            self.modes.addButton(radio, i)
            self.mode_buttons[mode] = radio
            box_layout.addWidget(radio)
            radio.toggled.connect(self._changed)
        layout.addWidget(box)

        box, box_layout = card("Wording", "Put # where the number goes, e.g.  Chests opened: #   or   Chest Hunt: #/500")
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        self.certain_label = label("Confirmed chests (CERTAIN)")
        self.certain_text = QLineEdit()
        self.approx_label = label("Estimated total (APPROX)")
        self.approx_text = QLineEdit()
        self.line_label = label("One line")
        self.line_text = QLineEdit()
        self.line_text.setToolTip("#C = confirmed number, #A = estimated total, e.g.  #C confirmed - #A total")
        for row, (lab, edit) in enumerate(((self.certain_label, self.certain_text), (self.approx_label, self.approx_text),
                                           (self.line_label, self.line_text))):
            form.addWidget(lab, row, 0)
            form.addWidget(edit, row, 1)
            edit.textChanged.connect(self._changed)
        form.setColumnStretch(1, 1)
        box_layout.addLayout(form)
        self.line_hint = label("For one line: #C = confirmed number, #A = estimated total.", "hint")
        box_layout.addWidget(self.line_hint)
        self.thousands = QCheckBox("Thousands separator (1,234 instead of 1234)")
        self.thousands.toggled.connect(self._changed)
        box_layout.addWidget(self.thousands)
        row = QHBoxLayout()
        row.addWidget(button("Original wording", "link", on_click=self._defaults))
        row.addStretch(1)
        box_layout.addLayout(row)
        layout.addWidget(box)

        box, box_layout = card("Preview", "Exactly what the text file contains (shown on black, like a stream overlay).")
        self.preview = label("", "overlayBox")
        self.preview.setTextFormat(Qt.PlainText)
        box_layout.addWidget(self.preview)
        layout.addWidget(box)

        box, box_layout = card("OBS setup", 'In OBS: add a "Text (GDI+)" source, tick "Read from file" and choose this file. '
                                            "It never changes, whatever you pick above.")
        row = QHBoxLayout()
        self.obs_path = QLineEdit()
        self.obs_path.setReadOnly(True)
        row.addWidget(self.obs_path, 1)
        row.addWidget(button("Copy path", on_click=self._copy_path))
        row.addWidget(button("Open folder", on_click=lambda: open_path(Path(self.obs_path.text()).parent)))
        box_layout.addLayout(row)
        layout.addWidget(box)

        row = QHBoxLayout()
        self.saved = label("", "hint")
        row.addWidget(self.saved, 1)
        row.addWidget(button("Undo changes", on_click=self.load))
        row.addWidget(button("Apply", "primary", on_click=self.apply))
        layout.addLayout(row)

        box, box_layout = card("OBS WebSocket (optional)",
                               "Instead of OBS reading the text file (it looks about once a second), the app can put the "
                               "same text straight into a Text source in OBS: every change shows at once and no file path "
                               "is needed. The text file is still written either way. Changes here apply immediately.")
        self.ws_enabled = QCheckBox("Update a Text source in OBS directly (OBS WebSocket)")
        self.ws_enabled.toggled.connect(self._ws_toggled)
        box_layout.addWidget(self.ws_enabled)
        self.ws_box = QWidget()
        grid = QGridLayout(self.ws_box)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.ws_host = QLineEdit()
        self.ws_host.setToolTip("127.0.0.1 = OBS runs on this PC. For OBS on another PC: that PC's IPv4 address.")
        self.ws_port = QSpinBox()
        self.ws_port.setRange(1, 65535)
        self.ws_password = QLineEdit()
        self.ws_password.setEchoMode(QLineEdit.Password)
        self.ws_source = QComboBox()
        self.ws_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.ws_source.activated.connect(self._ws_source_picked)
        grid.addWidget(label("OBS on"), 0, 0)
        grid.addWidget(self.ws_host, 0, 1)
        grid.addWidget(label("Port"), 0, 2)
        grid.addWidget(self.ws_port, 0, 3)
        grid.addWidget(label("Password"), 1, 0)
        grid.addWidget(self.ws_password, 1, 1, 1, 3)
        self.ws_forget = button("Forget password", "link", on_click=self._ws_forget)
        grid.addWidget(self.ws_forget, 1, 4)
        grid.addWidget(label("Text source"), 2, 0)
        grid.addWidget(self.ws_source, 2, 1, 1, 3)
        self.ws_refresh = button("Refresh", tip="List OBS's Text sources again", on_click=self._ws_refresh)
        grid.addWidget(self.ws_refresh, 2, 4)
        grid.setColumnStretch(1, 1)
        box_layout.addWidget(self.ws_box)
        self.ws_status = label("", "hint", wrap=True)
        box_layout.addWidget(self.ws_status)
        row = QHBoxLayout()
        row.addWidget(label('In OBS: Tools > WebSocket Server Settings > tick "Enable WebSocket server". '
                            '"Show Connect Info" shows the password. The password is kept in Windows Credential '
                            "Manager, never in a file.", "hint", wrap=True), 1)
        self.ws_direct = button("Use direct updates", tip='Untick "Read from file" on this source, so the app updates it',
                                on_click=lambda: self.win.obs_link.use_direct_updates())
        self.ws_direct.hide()
        row.addWidget(self.ws_direct, 0, Qt.AlignTop)
        self.ws_connect = button("Connect", "primary", on_click=self._ws_connect)
        row.addWidget(self.ws_connect, 0, Qt.AlignTop)
        box_layout.addLayout(row)
        layout.addWidget(box)
        layout.addStretch(1)
        self._loading = False

    def load(self):
        self._loading = True
        cfg, _ = load_cfg()
        self.display = cfg["display"]
        self.obs_path.setText(str((paths.APP_DIR / cfg["state"]["obs_dir"] / "chest_counter.txt").resolve()))
        self.mode_buttons[C.display_mode(self.display)].setChecked(True)
        self.certain_text.setText(C.hash_from_text(self.display["certain_text"]))
        self.approx_text.setText(C.hash_from_text(self.display["approx_text"]))
        self.line_text.setText(C.markers_from_line(self.display["combined_status_format"]))
        self.thousands.setChecked(self.display["use_thousands_separator"])
        ws = cfg["obs_websocket"]
        self.ws_enabled.blockSignals(True)
        self.ws_enabled.setChecked(ws["enabled"])
        self.ws_enabled.blockSignals(False)
        self.ws_box.setEnabled(ws["enabled"])
        self.ws_connect.setEnabled(ws["enabled"])
        self.ws_host.setText(ws["host"])
        self.ws_port.setValue(ws["port"])
        self.ws_password.clear()
        self._ws_password_hint()
        self._loading = False
        self.saved.setText("")
        self._changed()
        self.show_obs_status(self.win.obs_link.status()[1])

    # ---- OBS WebSocket card
    def _ws_password_hint(self):
        saved = obs_credentials.has_password()
        self.ws_password.setPlaceholderText("Saved - type a new one to replace it" if saved else
                                            "From OBS: Show Connect Info (leave empty if OBS asks for none)")
        self.ws_forget.setVisible(saved)

    def _ws_save(self, values):
        try:
            C.update_config_file(config_file(), "obs_websocket", values)
            return True
        except (C.UserError, OSError) as error:
            show_error(self, str(error))
            return False

    def _ws_toggled(self, on):
        if self._loading:
            return
        if self._ws_save({"enabled": on}):
            self.ws_box.setEnabled(on)
            self.ws_connect.setEnabled(on)
            self.win.apply_obs_settings()

    def _ws_connect(self):
        host = self.ws_host.text().strip()
        if not host or any(c.isspace() for c in host):
            show_error(self, 'Enter the PC that runs OBS: 127.0.0.1 for this PC, or that PC\'s IPv4 address (for example '
                             '192.168.1.50).')
            return
        typed = self.ws_password.text()
        if typed:
            try:
                obs_credentials.save_password(typed)
            except (OSError, ValueError) as error:
                show_error(self, f"The password could not be saved in Windows Credential Manager ({error}).")
                return
            self.ws_password.clear()
            self._ws_password_hint()
        if self._ws_save({"host": host, "port": self.ws_port.value()}):
            self.win.apply_obs_settings(reconnect=True)

    def _ws_forget(self):
        try:
            obs_credentials.forget_password()
        except OSError as error:
            show_error(self, f"The password could not be removed ({error}).")
            return
        self._ws_password_hint()
        self.win.apply_obs_settings(reconnect=True)

    def _ws_refresh(self):
        state = self.win.obs_link.status()[1]["state"]
        if state in ("live", "pick", "missing", "reads_file"):
            self.win.obs_link.refresh_sources()
        else:
            self.win.apply_obs_settings(reconnect=True)

    def _ws_source_picked(self, index):
        data = self.ws_source.itemData(index)
        if not data:
            return
        if self._ws_save({"source": data["name"], "source_uuid": data["uuid"]}):
            self.win.apply_obs_settings()

    def show_obs_status(self, status):
        name, color = OBS_STATES.get(status["state"], (status["state"], theme.MUTED))
        details = status.get("message", "")
        if status.get("obs") and status["state"] not in ("off", "connecting"):
            details += f"   ({status['obs']})"
        self.ws_status.setText(f"●  {name}" + (f" - {details}" if details else ""))
        self.ws_status.setStyleSheet(f"color: {color};")
        self.ws_direct.setVisible(status["state"] == "reads_file")
        self.ws_source.blockSignals(True)
        self.ws_source.clear()
        found = status.get("sources") or []
        current = status.get("source") or load_cfg()[0]["obs_websocket"]["source"]
        if not found:
            self.ws_source.addItem(current or "(connect to list OBS's Text sources)", None)
        else:
            if not any(s["name"] == current for s in found):
                self.ws_source.addItem("Pick a Text source ..." if not current else f"{current}   (not in OBS)", None)
            for s in found:
                kind = "FreeType 2" if s["kind"] == "text_ft2_source" else "GDI+"
                self.ws_source.addItem(f"{s['name']}   (Text {kind})", s)
                if s["name"] == current:
                    self.ws_source.setCurrentIndex(self.ws_source.count() - 1)
        self.ws_source.blockSignals(False)

    def _mode(self):
        return next(m for m, b in self.mode_buttons.items() if b.isChecked())

    def changes(self):
        mode = self._mode()
        texts = {"use_thousands_separator": self.thousands.isChecked()}
        if mode == "inline":
            if self.line_text.text().strip():
                texts["combined_status_format"] = C.line_from_markers(self.line_text.text())
        else:
            if mode in ("certain", "stacked") and self.certain_text.text().strip():
                texts["certain_text"] = C.text_from_hash(self.certain_text.text())
            if mode in ("approx", "stacked") and self.approx_text.text().strip():
                texts["approx_text"] = C.text_from_hash(self.approx_text.text())
        return {**C.MODE_SETTINGS[mode], **texts}

    def _state(self):
        certain, approx = self.win.counts
        return {"certain": certain, "approximate": approx}

    def _changed(self):
        if self._loading:
            return
        mode = self._mode()
        self.certain_label.setVisible(mode in ("certain", "stacked"))
        self.certain_text.setVisible(mode in ("certain", "stacked"))
        self.approx_label.setVisible(mode in ("approx", "stacked"))
        self.approx_text.setVisible(mode in ("approx", "stacked"))
        for widget in (self.line_label, self.line_text, self.line_hint):
            widget.setVisible(mode == "inline")
        preview = {**self.display, **self.changes()}
        self.preview.setText(C.overlay_text(preview, self._state()))
        state = self._state()
        for m, radio in self.mode_buttons.items():
            example = C.overlay_text({**self.display, **C.MODE_SETTINGS[m]}, state).replace("\n", "  /  ")
            radio.setText(f"{C.MODE_DESCRIPTIONS[m][0].upper()}{C.MODE_DESCRIPTIONS[m][1:]}      e.g.  {example}")
        pending = any(self.display.get(k) != v for k, v in self.changes().items())
        self.saved.setText("Not applied yet." if pending else "")

    def _defaults(self):
        d = settings.DEFAULTS["display"]
        self.certain_text.setText(C.hash_from_text(d["certain_text"]))
        self.approx_text.setText(C.hash_from_text(d["approx_text"]))
        self.line_text.setText(C.markers_from_line(d["combined_status_format"]))

    def _copy_path(self):
        QApplication.clipboard().setText(self.obs_path.text())
        self.saved.setText("Path copied - paste it into the OBS Text source.")

    def apply(self):
        changes = self.changes()
        try:
            C.update_config_file(config_file(), "display", changes)
        except (C.UserError, OSError) as error:
            show_error(self, str(error))
            return
        if not self.win.worker.running():
            self.win.write_obs_files()
        self.load()
        self.saved.setText("Applied. " + ("The counter updates the OBS text within a second."
                                          if self.win.worker.running() else "The OBS text file was updated."))
        self.win.refresh_viewers()


class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        layout = page_layout(self, "Settings", "Changes are saved in config.toml next to the app and are used the next time "
                                               "you press Start counting.")
        box, box_layout = card("Fortnite language", "The language your Fortnite is set to - the counter reads the word in the "
                                                    "chest pop-up (CHEST / BAÚ). \"Both\" checks the two words all the time: "
                                                    "only useful for mixed footage. One language avoids a small risk of false "
                                                    "alarms and a little work, but does not find more chests (no difference on "
                                                    "our English test videos). Automatic language detection will come once the "
                                                    "app recognises matches.")
        self.language = QComboBox()
        for text, langs in settings.LANGUAGE_CHOICES:
            self.language.addItem(text, langs)
        box_layout.addWidget(self.language)
        layout.addWidget(box)

        box, box_layout = card("Pictures analysed per second",
                               "How many pictures of your gameplay the counter checks every second. A chest pop-up is "
                               "on screen only briefly, so fewer pictures save work on this PC but can miss chests. "
                               "OBS and your stream are not affected either way.")
        self.fps = QComboBox()
        self.fps.currentIndexChanged.connect(self._fps_changed)
        box_layout.addWidget(self.fps)
        self.fps_hint = label("", "hint", wrap=True)
        box_layout.addWidget(self.fps_hint)
        layout.addWidget(box)

        box, box_layout = card("Session logs", "Logs are small text files in the logs folder. They are what you send when "
                                               "reporting a problem.")
        self.logging = QCheckBox("Keep a log of every counting session")
        self.snapshots = QCheckBox("Also save a small picture of every chest pop-up (to report missed or wrong chests)")
        box_layout.addWidget(self.logging)
        box_layout.addWidget(self.snapshots)
        self.logging.toggled.connect(self.snapshots.setEnabled)
        layout.addWidget(box)

        box, box_layout = card("Diagnostic recording (advanced)",
                               "Keeps exactly what the counter analyses, so a missed or wrong chest can be replayed and "
                               "checked later - and every future version can be tested on it. Turn it on and off in the "
                               "Dashboard's Console view, also while counting; press Ctrl+Alt+M while you play when the counter misses a chest.")
        self.lossless = QCheckBox("Lossless: the replay sees exactly what the counter saw (about twice the disk space)")
        box_layout.addWidget(self.lossless)
        row = QHBoxLayout()
        row.addWidget(button("Open captures folder", on_click=self._open_captures))
        row.addWidget(button("Review captures...", tip="Replay every capture through the current detector and compare it "
                                                       "with what was counted live and with your labels",
                             on_click=lambda: ReviewDialog(self).exec()))
        row.addStretch(1)
        box_layout.addLayout(row)
        layout.addWidget(box)

        box, box_layout = card("Match tracking (experimental)",
                               "Follows your matches while counting, for match statistics. English games only for now. It never changes "
                               "your counts or what OBS shows. Your chest history for Analytics (per hour, per day) is kept whenever your "
                               "counts are saved, with match tracking on or off.")
        self.match_on = QCheckBox("Track matches")
        box_layout.addWidget(self.match_on)
        row = QHBoxLayout()
        row.addWidget(label("Save progress every"))
        self.heartbeat = QComboBox()
        for seconds, text in settings.HEARTBEAT_CHOICES:
            self.heartbeat.addItem(text, seconds)
        row.addWidget(self.heartbeat, 1)
        box_layout.addLayout(row)
        box_layout.addWidget(label("How often the history saves where counting has got to. Matches are still followed once a second whatever you "
                                   "choose. A longer interval writes less to the disk, but after a crash more of the last moments count as uncertain.",
                                   "hint", wrap=True))
        self._match_mode = "off"
        layout.addWidget(box)

        box, box_layout = card("Window")
        self.remember_window = QCheckBox("Remember window size and position (the app reopens the way you closed it)")
        box_layout.addWidget(self.remember_window)
        layout.addWidget(box)

        box, box_layout = card("Updates", "Nothing is downloaded or installed unless you choose to. Your counts, profiles and settings are kept.")
        self.update_auto = QCheckBox("Check for updates automatically when the app opens")
        box_layout.addWidget(self.update_auto)
        row = QHBoxLayout()
        row.addWidget(label("Download speed"))
        self.update_bandwidth = QComboBox()
        for text, value in (("Adaptive   (recommended)", "adaptive"), ("Unlimited", "unlimited"), ("Custom limit", "custom")):
            self.update_bandwidth.addItem(text, value)
        self.update_bandwidth.currentIndexChanged.connect(self._bandwidth_changed)
        row.addWidget(self.update_bandwidth, 1)
        self.update_limit = QSpinBox()
        row.addWidget(self.update_limit)
        self.update_unit = QComboBox()
        self.update_unit.addItem("KB/s", 1)
        self.update_unit.addItem("MB/s", 1000)
        self.update_unit.currentIndexChanged.connect(self._limit_unit_changed)
        row.addWidget(self.update_unit)
        box_layout.addLayout(row)
        self.update_hint = label("", "hint", wrap=True)
        box_layout.addWidget(self.update_hint)
        row = QHBoxLayout()
        self.check_button = button("Check for updates", on_click=win.check_for_updates)
        row.addWidget(self.check_button)
        self.update_status = label("", "hint", wrap=True)
        row.addWidget(self.update_status, 1)
        box_layout.addLayout(row)
        layout.addWidget(box)

        box, box_layout = card("Advanced", "Everything else (for example which evidence counts) is in config.toml. "
                                           "Edit it only if you know why; a typo shows a warning and uses the default.")
        row = QHBoxLayout()
        row.addWidget(button("Open config.toml", on_click=self._open_config))
        row.addWidget(button("Open program folder", on_click=lambda: open_path(paths.APP_DIR)))
        row.addStretch(1)
        box_layout.addLayout(row)
        layout.addWidget(box)

        row = QHBoxLayout()
        self.saved = label("", "hint")
        row.addWidget(self.saved, 1)
        row.addWidget(button("Save", "primary", on_click=self.save))
        layout.addLayout(row)
        layout.addStretch(1)

    def load(self):
        cfg, _ = load_cfg()
        self.language.setCurrentIndex(settings.language_choice(cfg["detector"]["languages"]))
        fps = cfg["detector"]["process_fps"]
        self.fps.blockSignals(True)
        self.fps.clear()
        for value, name, _ in settings.FPS_PRESETS:
            self.fps.addItem(f"{value} per second   ({name})", value)
        if settings.fps_choice(fps) is None:
            self.fps.addItem(f"{fps} per second   (custom, from config.toml)", fps)
            self.fps.setCurrentIndex(self.fps.count() - 1)
        else:
            self.fps.setCurrentIndex(settings.fps_choice(fps))
        self.fps.blockSignals(False)
        self._fps_changed()
        self.logging.setChecked(cfg["logging"]["enabled"])
        self.snapshots.setChecked(cfg["logging"]["save_snapshots"])
        self.snapshots.setEnabled(cfg["logging"]["enabled"])
        self.lossless.setChecked(cfg["capture"]["quality"] == "lossless")
        self._match_mode = cfg["match"]["mode"]
        self.match_on.setChecked(self._match_mode == "on")
        self.heartbeat.setCurrentIndex(max(self.heartbeat.findData(cfg["match"]["heartbeat_seconds"]), 0))
        self.remember_window.setChecked(cfg["app"]["remember_window"])
        update = cfg["update"]
        self.update_auto.setChecked(update["check_automatically"])
        self.update_bandwidth.setCurrentIndex(max(self.update_bandwidth.findData(update["download_bandwidth"]), 0))
        limit = update["custom_limit_kb_per_second"]
        in_mb = limit >= 1000 and limit % 1000 == 0
        self.update_unit.setCurrentIndex(1 if in_mb else 0)
        self._limit_unit_changed()
        self.update_limit.setValue(limit // 1000 if in_mb else limit)
        self._bandwidth_changed()
        self.saved.setText("")

    def _bandwidth_changed(self, _index=None):
        mode = self.update_bandwidth.currentData()
        self.update_limit.setVisible(mode == "custom")
        self.update_unit.setVisible(mode == "custom")
        self.update_hint.setText({"adaptive": "About 1 MB/s while the app is counting, and no limit otherwise. It follows whether you are counting; "
                                              "it does not measure your connection.",
                                  "unlimited": "Never limited, even while counting.",
                                  "custom": "Always limited to this speed."}.get(mode, ""))

    def _limit_unit_changed(self, _index=None):
        if self.update_unit.currentData() == 1000:
            self.update_limit.setRange(1, settings.MAX_CUSTOM_LIMIT_KB // 1000)
        else:
            self.update_limit.setRange(settings.MIN_CUSTOM_LIMIT_KB, settings.MAX_CUSTOM_LIMIT_KB)

    def _fps_changed(self, _index=None):
        index = settings.fps_choice(self.fps.currentData())
        self.fps_hint.setText(settings.FPS_PRESETS[index][2] if index is not None else
                              "A value set in config.toml. 15 per second is what the counter was tested with.")

    def save(self):
        langs = self.language.currentData()
        try:
            C.update_config_file(config_file(), "detector", {"languages": langs, "process_fps": self.fps.currentData()})
            C.update_config_file(config_file(), "logging", {"enabled": self.logging.isChecked(),
                                                            "save_snapshots": self.snapshots.isChecked()})
            C.update_config_file(config_file(), "capture", {"quality": "lossless" if self.lossless.isChecked() else "standard"})
            # "shadow" is a developer setting in config.toml: leaving the box unticked must not quietly replace it
            mode = "on" if self.match_on.isChecked() else "shadow" if self._match_mode == "shadow" else "off"
            C.update_config_file(config_file(), "match", {"mode": mode, "heartbeat_seconds": self.heartbeat.currentData()})
            self._match_mode = mode
            C.update_config_file(config_file(), "app", {"remember_window": self.remember_window.isChecked()})
            C.update_config_file(config_file(), "update", {"check_automatically": self.update_auto.isChecked(),
                                                           "download_bandwidth": self.update_bandwidth.currentData(),
                                                           "custom_limit_kb_per_second": self.update_limit.value() * self.update_unit.currentData()})
            if not self.remember_window.isChecked():
                window_file().unlink(missing_ok=True)   # off = back to the default layout, also if switched on again later
        except (C.UserError, OSError) as error:
            show_error(self, str(error))
            return
        self.saved.setText("Saved." + (" Stop and start counting to use the new settings."
                                       if self.win.worker.running() else ""))
        self.win.update_game_idle()

    def _open_captures(self):
        cfg, _ = load_cfg()
        folder = paths.APP_DIR / cfg["capture"]["dir"]
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def _open_config(self):
        path = config_file()
        if not path.exists():
            try:
                C.update_config_file(path, "live", {})          # create it from config.example.toml, comments included
            except (C.UserError, OSError) as error:
                show_error(self, str(error))
                return
        open_path(path)


QUALITY_LOOK = {"complete": ("Complete", theme.CERTAIN), "partial": ("Partial", theme.APPROX), "unconfirmed": ("Unconfirmed", theme.MUTED)}


def console_counts_text(certain, approx):
    return f'{_span("CERTAIN " + fmt(certain), theme.CERTAIN, bold=True)}&nbsp;&nbsp;&nbsp;{_span("APPROX " + fmt(approx), theme.APPROX, bold=True)}'


def rate_tile(tile, rate, label_text, missing):
    """APPROX first, because it is the fuller count. CERTAIN stays beside it, never added to it."""
    tile.value.setText(UNKNOWN_VALUE if rate is None else f"{rate.approx_per_minute:.2f}")
    tile.sub.setText(missing if rate is None else f"APPROX per minute  ·  {rate.certain_per_minute:.2f} CERTAIN  ·  {label_text(rate)}")


def manual_text(added, removed):
    """"+2 manual", "−1 manual", "±0 manual" or "": your corrections inside a match's APPROX count, never passed off as detected chests."""
    net = added - removed
    return f"{'+' if net > 0 else '−' if net < 0 else '±'}{abs(net)} manual" if added or removed else ""


def manual_part(added, removed, broken=0):
    return f" ({manual_text(added, removed)}" + (f", {fmt(broken)} broken" if broken else "") + ")" if added or removed else ""


def rate_hint_text(include_manual):
    return ("Chests per minute are APPROX chests divided by your time actively playing. The main figure uses complete matches only, meaning their start "
            "and their end were both seen. It counts the chests the app detected by itself, minus any you took off with −1 in the Game view" +
            (", plus the +1s you made in the Game view." if include_manual else "; your +1s are left out unless you tick the box below.") +
            " This is not your Fortnite total.")


def rate_cell(match):
    if match.rate is None:
        return UNKNOWN_VALUE
    return f"{match.rate.approx_per_minute:.2f}" + ("" if match.quality == "complete" else " seen")


def plural(count, word):
    return f"{fmt(count)} {word}{'' if count == 1 else 'es' if word.endswith('ch') else 's'}"


def analytics_notes(summary):
    """Plain sentences for whatever a reader needs to know before trusting the numbers."""
    notes = []
    if summary.unfinished:
        notes.append(f"{plural(summary.unfinished, 'match')} still in progress: left out of the match count, match time and chests per minute until it ends.")
    if summary.excluded:
        notes.append(f"{plural(summary.excluded, 'match')} marked as not a match, left out of every statistic.")
    if summary.manual_added or summary.manual_removed:
        notes.append(f"Manual corrections: +{fmt(summary.manual_added)}, −{fmt(summary.manual_removed)}. Those made in the Game view belong to their match and are in its "
                     "APPROX count; those made on Overview change only your totals.")
    if summary.matches_left_out_of_rates:
        notes.append(f"{plural(summary.matches_left_out_of_rates, 'match')} left out of chests per minute: some of their chests were not recorded, or their play time is unknown.")
    if summary.missing_approx or summary.missing_certain:
        notes.append(f"History is missing {fmt(summary.missing_approx)} chests that your totals include ({fmt(summary.missing_certain)} CERTAIN).")
    if summary.damaged_rows:
        notes.append(f"{plural(summary.damaged_rows, 'damaged row')} skipped.")
    if summary.newer_rows:
        notes.append(f"{plural(summary.newer_rows, 'row')} from a newer version skipped.")
    return "   ".join(notes)


ANALYTICS_VIEWS = (("Performance", "How fast you progress: chests per hour of real life, and per minute of play"),
                   ("Days & weeks", "Your chests day by day and week by week"),
                   ("Personal Bests", "Your best match, hour, day, week and session"),
                   ("History", "Every recorded match and session"))
PERFORMANCE_VIEW, DAYS_VIEW, BESTS_VIEW, HISTORY_VIEW = range(4)
HISTORY_MATCHES = 100                      # the History tab lists this many matches, newest first
AUTO_REFRESH_MS = 5000                     # after a match ends, so the detector's last chests of it are saved first
BEST_TITLES = {"match_chests": "MOST CHESTS IN A MATCH", "match_rate": "BEST CHESTS PER MINUTE", "hour": "BEST HOUR", "day": "BEST DAY",
               "week": "BEST WEEK", "session": "MOST CHESTS IN A SESSION", "session_rate": "BEST SESSION PACE (PER HOUR)",
               "longest_session": "LONGEST SESSION", "match_broken": "MOST BROKEN CHESTS IN A MATCH"}
BEST_NEEDS = {"match_chests": "A Complete match with chests", "match_rate": "A Complete match with 5 minutes of play",
              "hour": "60 minutes of counting in a row", "day": "A day with chests", "week": "A week with chests", "session": "A session with chests",
              "session_rate": "A session of an hour or more", "longest_session": "A session", "match_broken": "A broken chest you add in the Game view"}


def scroll_tab():
    """A tab that scrolls as one page. -> (the tab widget, its content layout)."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("page")
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(0, 8, 6, 8)
    layout.setSpacing(12)
    area.setWidget(inner)
    return area, layout


def tile_row(*tiles):
    row = QHBoxLayout()
    row.setSpacing(12)
    for tile in tiles:
        row.addWidget(tile, 1)
    return row


def tile_grid(tiles, columns):
    grid = QGridLayout()
    grid.setSpacing(10)
    for index, tile in enumerate(tiles):
        grid.addWidget(tile, index // columns, index % columns)
    for column in range(columns):
        grid.setColumnStretch(column, 1)
    return grid


def minutes_text(seconds):
    """"1h 02m", "18m" or "45s": the History list needs no seconds once there are minutes."""
    if seconds is None:
        return None
    seconds = int(seconds)
    return f"{seconds // 3600}h {seconds // 60 % 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m" if seconds >= 60 else f"{seconds}s"


def day_text(day):
    return f"{day:%a} {day.day} {day:%b}"


def clock_of(moment):
    return timeline.local(moment).strftime("%H:%M")


def when_text(moment):
    """A UTC moment as the PC's local day and time: "Mon 9 Nov, 20:03"."""
    return f"{day_text(timeline.local(moment).date())}, {clock_of(moment)}"


def average_text(value):
    return None if value is None else f"{value:.1f}"


def counted_text(days):
    counted = sum(1 for day in days if day.monitored)
    return f"{counted} of {len(days)} days counted"


class BestCard(QFrame):
    """One personal best with its evidence."""

    def __init__(self, key):
        super().__init__()
        self.key = key
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(label(BEST_TITLES[key], "countLabel"))
        self.value = label(UNKNOWN_VALUE, "statValue")
        layout.addWidget(self.value)
        self.when = label("", "countSub", wrap=True)
        layout.addWidget(self.when)
        self.detail = label("", "countSub", wrap=True)
        layout.addWidget(self.detail)

    def show_best(self, best):
        if best is None:
            self.value.setText(UNKNOWN_VALUE)
            self.when.setText(f"Needs: {BEST_NEEDS[self.key][0].lower()}{BEST_NEEDS[self.key][1:]}")
            self.detail.setText("")
            return
        duration = match_analytics.duration_text
        value = best.value
        self.value.setText(duration(value) if self.key == "longest_session" else f"{value:.2f}" if self.key == "match_rate"
                           else f"{value:.1f}" if self.key == "session_rate" else fmt(value))
        if self.key in ("day",):
            when = day_text(best.start)
        elif self.key == "week":
            when = f"Week of {best.start.day} {best.start:%b %Y}"
        elif best.end is not None:
            when = f"{when_text(best.start)} to {clock_of(best.end)}" + (f"  ·  {duration(best.seconds)}" if self.key != "longest_session" else "")
        elif best.start is not None:
            when = when_text(best.start) + (f"  ·  {duration(best.seconds)}" if duration(best.seconds) else "")
        else:
            when = ""
        self.when.setText(when)
        parts = []
        if best.certain is not None and self.key in ("match_chests", "hour", "day", "week", "session"):
            parts.append(f"{fmt(best.certain)} CERTAIN")
        elif best.certain is not None and self.key == "match_rate":
            parts.append(f"{best.certain:.2f} CERTAIN")
        if best.manual_added or best.manual_removed:
            parts.append(f"incl. {manual_text(best.manual_added, best.manual_removed)}")
        if best.quality:
            parts.append(QUALITY_LOOK[best.quality][0])
        if best.cut_short:
            parts.append("at least: part of it was not saved")
        self.detail.setText("  ·  ".join(parts))


class AnalyticsPage(QWidget):
    """What history shows, in four tabs. Read-only, and worked out away from this window's thread so a huge history cannot freeze it."""

    COLUMNS = ("Started", "Duration", "CERTAIN", "APPROX", "Per min", "Quality", "Ending", "")
    SESSION_COLUMNS = ("Started", "Session time", "Counting", "Chests", "Per hour", "Your +1/−1")

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 16)
        layout.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(label("Analytics", "pageTitle"))
        top.addStretch(1)
        self.profile_line = label("", "hint")
        top.addWidget(self.profile_line, 0, Qt.AlignVCenter)
        self.refresh_button = button("Refresh", tip="Read the history again", on_click=self.refresh)
        top.addWidget(self.refresh_button, 0, Qt.AlignVCenter)
        layout.addLayout(top)
        layout.addWidget(label("From your saved history. Your official totals stay on the Dashboard.", "pageSub", wrap=True))
        self.status = label("", "hint", wrap=True)
        self.status.hide()
        layout.addWidget(self.status)
        self.empty, empty_layout = card("Nothing recorded yet")
        self.empty_hint = label("", "hint", wrap=True)
        empty_layout.addWidget(self.empty_hint)
        erow = QHBoxLayout()
        self.empty_settings = button("Open Settings", "link", on_click=lambda: win.show_page(win.settings_page))
        erow.addWidget(self.empty_settings)
        erow.addStretch(1)
        empty_layout.addLayout(erow)
        self.empty.hide()
        layout.addWidget(self.empty)

        segments = QHBoxLayout()
        segments.setSpacing(4)
        self.view_buttons = QButtonGroup(self)
        for index, (name, tip) in enumerate(ANALYTICS_VIEWS):
            view_button = button(name.replace("&", "&&"), "segment", tip=tip)         # a single & would mark a keyboard shortcut
            view_button.setCheckable(True)
            self.view_buttons.addButton(view_button, index)
            segments.addWidget(view_button)
        segments.addStretch(1)
        layout.addLayout(segments)
        layout.addWidget(hline())
        self.views = QStackedWidget()
        layout.addWidget(self.views, 1)
        self.view_buttons.button(PERFORMANCE_VIEW).setChecked(True)
        self.view_buttons.idClicked.connect(self.show_view)

        self._build_performance()
        self._build_days()
        self._build_bests()
        self._build_history()

        self._analytics = None
        self._newest = None                                   # the newest match listed, so only a genuinely new one moves the list
        self._generation = 0
        self._done = queue.SimpleQueue()
        self._thread = None
        self._collector = QTimer(self)
        self._collector.timeout.connect(self._collect)
        self._auto_refresh = QTimer(self)
        self._auto_refresh.setSingleShot(True)
        self._auto_refresh.timeout.connect(self._refresh_if_open)

    # ------------------------------------------------------------------ building
    def _build_performance(self):
        tab, layout = scroll_tab()
        self.views.addWidget(tab)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.period_buttons = QButtonGroup(self)
        for index, (key, text) in enumerate(progression.PERIODS):
            period = button(text, "toggle")
            period.setCheckable(True)
            self.period_buttons.addButton(period, index)
            row.addWidget(period)
        row.addStretch(1)
        self.period_buttons.button(len(progression.PERIODS) - 1).setChecked(True)      # All time
        self.period_buttons.idClicked.connect(lambda _: self._show_period())
        layout.addLayout(row)

        self.hour_rate = CountCard("CHESTS PER HOUR", "", theme.APPROX)
        self.hour_rate.setToolTip("Your chests divided by your session time: the whole time from starting to stopping, with queues, the lobby and short "
                                  "breaks in it. Sessions are counting runs less than 30 minutes apart. It is your real pace, not chests per minute times 60.")
        self.complete_rate = CountCard("AVERAGE DETECTED CHESTS / MIN", "", theme.APPROX)
        self.complete_rate.setToolTip("Chests per minute of active play in complete matches: how fast you loot while playing.")
        headline = QHBoxLayout()
        headline.setSpacing(12)
        headline.addWidget(self.hour_rate, 1)
        headline.addWidget(self.complete_rate, 1)
        layout.addLayout(headline)

        self.approx = StatTile("CHESTS")
        self.approx.setToolTip("Chests the app detected, plus your +1s and minus your −1s. Chests seen while spectating someone else after you were "
                               "out of a recognised match are left out. Reset, Edit counts and a starting count are not chests.")
        self.session_time = StatTile("SESSION TIME")
        self.confirmed = StatTile("ACTIVE PLAY")
        self.confirmed.setToolTip("Alive on the bus or the map, in recognised Complete and Partial matches.")
        self.matches = StatTile("MATCHES")
        layout.addLayout(tile_row(self.approx, self.session_time, self.confirmed, self.matches))
        layout.addWidget(label("Chests over time", "cardTitle"))
        self.buildup = charts.BuildUpChart()
        self.buildup.setToolTip("Your chests adding up. Shaded: the app was counting. A flat line outside the shading is time nobody watched.")
        layout.addWidget(self.buildup)

        self.session = StatTile("TIME COUNTING")
        self.session.setToolTip("Time the app was counting. Session time minus this is time between runs that was not watched.")
        self.between = StatTile("BETWEEN MATCHES")
        self.between.setToolTip("Time counting minus active play: the lobby, queues, the waiting island, after your elimination and breaks.")
        self.observed = StatTile("MATCH TIME SEEN", "On screen, complete and partial matches")
        self.certain = StatTile("CERTAIN")
        self.per_match = StatTile("PER COMPLETE MATCH")
        self.observed_rate = StatTile("INCLUDING PARTIAL MATCHES")
        details = [self.session, self.between, self.observed, self.certain, self.per_match, self.observed_rate]
        for tile in details:
            tile.compact()
        layout.addLayout(tile_grid(details, 3))

        box, box_layout = card("Where your chests came from", "Your +1s and −1s are your reports, not detections. Only \"missed\" and \"not a "
                                                                "chest\" say anything about the detector.")
        self.detected = StatTile("DETECTED")
        self.broken = StatTile("BROKEN (YOURS)")
        self.broken.setToolTip("Chests you added with +1 as broken chests. You reported them: the app did not detect them.")
        self.missed = StatTile("MISSED (YOURS)")
        self.missed.setToolTip("Visible chests you said the counter missed.")
        self.other_added = StatTile("OTHER +1s")
        self.other_added.setToolTip("+1s with no reason or \"Fortnite counted it, nothing to see\".")
        self.removed = StatTile("YOUR −1s")
        sources = [self.detected, self.broken, self.missed, self.other_added, self.removed]
        for tile in sources:
            tile.compact()
        box_layout.addLayout(tile_grid(sources, 3))
        layout.addWidget(box)

        self.rate_hint = label(rate_hint_text(bool(load_cfg()[0]["app"]["analytics_include_manual"])), "hint", wrap=True)
        layout.addWidget(self.rate_hint)
        self.include_manual = QCheckBox("Count my +1s from the Game view in chests per minute and per match")
        self.include_manual.setToolTip("A +1 made for a match is a chest the detector did not see, a broken chest say. Off: the rates stay what the detector measured. "
                                       "A -1 always counts, because it takes off a chest that should not have been counted. Chests per hour and per day "
                                       "always include them, like your total.")
        self.include_manual.setChecked(bool(load_cfg()[0]["app"]["analytics_include_manual"]))
        self.include_manual.toggled.connect(self._include_manual_toggled)
        layout.addWidget(self.include_manual)
        self.notes = label("", "hint", wrap=True)
        layout.addWidget(self.notes)
        layout.addStretch(1)

    def _build_days(self):
        tab, layout = scroll_tab()
        self.views.addWidget(tab)
        self.today = StatTile("TODAY")
        self.yesterday = StatTile("YESTERDAY")
        self.this_week = StatTile("THIS WEEK")
        self.last7 = StatTile("LAST 7 DAYS")
        self.last30 = StatTile("LAST 30 DAYS")
        layout.addLayout(tile_grid([self.today, self.yesterday, self.this_week, self.last7, self.last30], 5))
        layout.addWidget(label("Last 30 days", "cardTitle"))
        self.day_chart = charts.BarChart()
        layout.addWidget(self.day_chart)
        layout.addWidget(label("Bars: chests.   A short line: counted, none found.   A ring: not counted that day, so nothing is known.", "hint", wrap=True))
        self.per_monitored = StatTile("PER DAY COUNTED")
        self.per_monitored.setToolTip("Your chests on the days the app was counting, divided by those days. A counted day with no chest counts as a zero.")
        self.per_active = StatTile("PER DAY WITH CHESTS")
        self.per_active.setToolTip("Your chests divided by the days on which you got some.")
        self.per_calendar = StatTile("PER CALENDAR DAY")
        self.per_calendar.setToolTip("Your chests divided by every day since your first recorded day, counted or not. The honest pace for planning, "
                                     "but days that were not counted are not known to be zero.")
        self.per_week = StatTile("PER WEEK")
        self.per_week.setToolTip("The per-calendar-day average times seven, over completed weeks.")
        self.best_day = StatTile("BEST DAY")
        self.best_week = StatTile("BEST WEEK")
        averages = [self.per_monitored, self.per_active, self.per_calendar, self.per_week, self.best_day, self.best_week]
        for tile in averages:
            tile.compact()
        layout.addLayout(tile_grid(averages, 3))
        layout.addWidget(label("Last 12 weeks", "cardTitle"))
        self.week_chart = charts.BarChart()
        layout.addWidget(self.week_chart)
        self.days_note = label("Averages use completed days and weeks: today and this week are still going.", "hint", wrap=True)
        layout.addWidget(self.days_note)
        layout.addStretch(1)

    def _build_bests(self):
        tab, layout = scroll_tab()
        self.views.addWidget(tab)
        layout.addWidget(label("Your best results, worked out again from your history every time, so excluding a match or undoing a correction "
                               "updates them. Match bests use Complete matches only.", "hint", wrap=True))
        self.best_cards = {key: BestCard(key) for key, _ in records.BESTS}
        layout.addLayout(tile_grid(list(self.best_cards.values()), 2))
        layout.addStretch(1)

    def _build_history(self):
        tab = QWidget()
        tab.setObjectName("page")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        self.views.addWidget(tab)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.history_buttons = QButtonGroup(self)
        for index, text in enumerate(("Matches", "Sessions")):
            choice = button(text, "toggle")
            choice.setCheckable(True)
            self.history_buttons.addButton(choice, index)
            row.addWidget(choice)
        self.history_buttons.button(0).setChecked(True)
        row.addSpacing(10)
        self.recent_title = label("Recent matches, newest first", "hint")
        row.addWidget(self.recent_title)
        row.addStretch(1)
        layout.addLayout(row)
        self.history_views = QStackedWidget()
        layout.addWidget(self.history_views, 1)
        self.history_buttons.idClicked.connect(self._history_choice)

        self.table = self._table(self.COLUMNS)
        self.table.horizontalHeaderItem(4).setToolTip("Detected APPROX chests per minute of active play in that match. \"seen\" means only part of the match was seen. A dash means there is not enough to go on.")
        self.table.viewport().installEventFilter(self)
        self.history_views.addWidget(self.table)
        self.sessions_table = self._table(self.SESSION_COLUMNS)
        self.sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.sessions_table.horizontalHeader().setStretchLastSection(True)
        self.history_views.addWidget(self.sessions_table)

    def _history_choice(self, index):
        self.history_views.setCurrentIndex(index)
        self.recent_title.setText("Sessions: counting runs less than 30 minutes apart, newest first" if index else "Recent matches, newest first")

    @staticmethod
    def _table(columns):
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)     # sized by _fit_columns
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setMinimumHeight(170)
        table.setStyleSheet("QHeaderView::section { padding: 6px 4px; } QTableWidget::item { padding: 4px 4px; }")   # fits 920 x 640 (UX-08)
        return table

    def show_view(self, index):
        """Only changes what is on screen."""
        self.views.setCurrentIndex(index)
        self.view_buttons.button(index).setChecked(True)

    @property
    def period_key(self):
        return progression.PERIODS[max(self.period_buttons.checkedId(), 0)][0]

    # ------------------------------------------------------------------ reading
    def refresh(self):
        cfg, _ = load_cfg()
        profile = cfg["profile"]
        self.profile_line.setText(f"Profile: {profile['name']}")
        self.status.setText("Reading your history...")
        self.status.show()
        self._generation += 1
        folder = paths.APP_DIR / profiles.history_folder(profile["state_base"], profile["id"])
        counting = self.win.mode in ("counting", "stopping")
        self._thread = threading.Thread(target=self._read, args=(self._generation, folder, self.include_manual.isChecked(), counting), daemon=True, name="analytics")
        self._thread.start()
        self._collector.start(40)

    def match_ended(self):
        """A match just closed. If this page is open, read the history again shortly, once the detector's last chests are saved."""
        if self.win.pages.currentWidget() is self:
            self._auto_refresh.start(AUTO_REFRESH_MS)

    def _refresh_if_open(self):
        if self.win.pages.currentWidget() is self:
            self.refresh()

    def _include_manual_toggled(self, on):
        try:
            C.update_config_file(config_file(), "app", {"analytics_include_manual": bool(on)})
        except (C.UserError, OSError) as error:
            show_error(self, f"The setting could not be saved ({error}).")
        self.refresh()

    def _read(self, generation, folder, include_manual, counting):
        try:
            self._done.put((generation, records.load(folder, counting_now=counting, include_manual=include_manual)))
        except Exception as error:
            self._done.put((generation, error))

    def _collect(self):
        while True:
            try:
                generation, result = self._done.get_nowait()
            except queue.Empty:
                return
            if generation != self._generation:                # an older request: a newer one, or another profile, replaced it
                continue
            self._collector.stop()
            if isinstance(result, Exception):
                self.status.setText(f"The history could not be read ({result}). Your counts are not affected.")
                self.status.show()
            elif isinstance(result, match_analytics.Summary):  # match statistics alone
                self.status.hide()
                self.status.setText("")
                self.show_summary(result)
            else:
                self.status.hide()
                self.status.setText("")
                self.show_analytics(result)

    # ------------------------------------------------------------------ showing
    def show_analytics(self, a):
        self._analytics = a
        self.show_summary(a.summary, matches=a.summary.all_matches[:HISTORY_MATCHES])
        self._show_period()
        self._show_days(a.snapshot, a.bests)
        for key, card_widget in self.best_cards.items():
            card_widget.show_best(a.bests.get(key))
        self._fill_sessions(a.snapshot)

    def _has_data(self):
        a = self._analytics
        return a is not None and bool(a.snapshot.runs or a.snapshot.events or not a.summary.empty)

    def show_summary(self, s, matches=None):
        """The match statistics, the empty state, the notes and the match list."""
        empty = s.empty and not self._has_data()
        self.empty.setVisible(empty)
        self.recent_title.setVisible(not empty)
        self.table.setVisible(not empty)
        if empty:
            tracking = load_cfg()[0]["match"]["mode"] == "on"
            self.empty_hint.setText("Count a game and your chests, sessions and matches appear here." if tracking else
                                    "Your chests per hour and per day are recorded whenever you count. Turn on match tracking in Settings to "
                                    "see your matches and chests per minute too.")
            self.empty_settings.setVisible(not tracking)
        self._show_match_tiles(s)
        self.notes.setText(analytics_notes(s))
        self.notes.setVisible(bool(self.notes.text()))
        self._fill_table(s.recent if matches is None else matches)

    def _show_match_tiles(self, s):
        duration = match_analytics.duration_text
        self.matches.set_value(fmt(s.matches), f"{fmt(s.complete)} complete · {fmt(s.partial)} partial · {fmt(s.unconfirmed)} unconfirmed")
        self.observed.set_value(duration(s.observed_seconds))
        per = s.per_complete_match
        self.per_match.set_value(f"{per.approx:.1f}" if per else None, f"APPROX  ·  {per.certain:.1f} CERTAIN  ·  {plural(per.matches, 'match')}" if per else "No complete matches yet")
        rate_tile(self.complete_rate, s.complete_rate, lambda r: f"{plural(r.matches, 'complete match')}, {duration(r.minutes * 60)} of active play",
                  f"Not enough complete matches: needs {match_analytics.MIN_COMPLETE_RATE_SECONDS // 60} minutes of active play across them")
        rate_tile(self.observed_rate, s.observed_rate, lambda r: f"over {duration(r.minutes * 60)} of active play, complete and partial matches",
                  f"Needs at least {match_analytics.MIN_OBSERVED_RATE_SECONDS // 60} minutes of active play")
        self.rate_hint.setText(rate_hint_text(s.include_manual))
        self.complete_rate.title.setText("AVERAGE CHESTS / MIN WITH YOUR +1s" if s.include_manual else "AVERAGE DETECTED CHESTS / MIN")

    def _show_period(self):
        a = self._analytics
        if a is None:
            return
        key = self.period_key
        p = a.periods[key]
        self._show_match_tiles(a.summary if key == "all" else p.match_summary)
        duration = match_analytics.duration_text
        t = p.totals
        watched = p.counting_seconds > 0 or t.recorded or t.detected or t.manual_added or t.manual_removed
        least = "at least " if p.cut_short else ""
        rate = p.per_hour
        self.hour_rate.value.setText(UNKNOWN_VALUE if rate is None else f"{rate:.1f}")
        self.hour_rate.sub.setText(f"{fmt(p.in_sessions)} chests in {duration(p.session_seconds)} of sessions, breaks included" if rate is not None else
                                   f"Needs {progression.MIN_HOURLY_SECONDS // 60} minutes of session time in this period" if watched else "Not counted in this period")
        if not watched:
            for tile in (self.approx, self.certain, self.session_time, self.session, self.confirmed, self.between, self.detected, self.broken,
                         self.missed, self.other_added, self.removed):
                tile.set_value(None, "")
        else:
            extra = [f"{fmt(t.detected)} detected"] + ([f"{manual_text(t.manual_added, t.manual_removed)}"] if t.manual_added or t.manual_removed else [])
            if p.spectating_left_out:
                extra.append(f"{fmt(p.spectating_left_out)} spectated left out")
            self.approx.set_value(fmt(t.recorded), "  ·  ".join(extra))
            self.certain.set_value(fmt(t.certain), "Detected with the strongest evidence")
            self.session_time.set_value(duration(p.session_seconds), f"{plural(p.sessions, 'session')}, breaks included")
            self.session.set_value(least + duration(p.counting_seconds) if p.counting_seconds else duration(0),
                                   f"{duration(p.gap_seconds)} between runs not watched" if p.gap_seconds >= 1 else "In or out of matches")
            if p.active_seconds is None:
                self.confirmed.set_value(None, "No recognised match in this period")
                self.between.set_value(None, "Needs recognised matches")
            else:
                low = p.active_is_lower_bound
                self.confirmed.set_value(("at least " if low else "") + duration(p.active_seconds),
                                         "Some play was not recognised" if low else "Alive on the bus or the map")
                self.between.set_value(("at most " if low else "") + duration(p.between_matches_seconds), "Lobby, queues, island, breaks")
            self._show_sources(p)
        self._show_buildup(a.snapshot, p)

    def _show_sources(self, p):
        t, hours = p.totals, p.counting_seconds / 3600
        events = [e for e in self._analytics.snapshot.events if p.start <= e.at < p.end and e.manual]
        added = [e for e in events if e.delta > 0]

        def share(count):
            parts = [f"{100 * count / t.recorded:.0f}% of your chests"] if t.recorded > 0 else []
            if hours >= 0.5:
                parts.append(f"{count / hours:.1f} per hour counting")
            return "  ·  ".join(parts)

        broken = sum(e.reason == match_history.BROKEN_CHEST for e in added)
        missed = sum(e.reason == match_history.MISSED for e in added)
        self.detected.set_value(fmt(t.detected), share(t.detected))
        self.broken.set_value(fmt(broken), share(broken))
        self.missed.set_value(fmt(missed), share(missed))
        self.other_added.set_value(fmt(len(added) - broken - missed), share(len(added) - broken - missed))
        removed = [e for e in events if e.delta < 0]
        wrong = sum(e.reason == match_history.FALSE_POSITIVE for e in removed)
        self.removed.set_value(fmt(len(removed)), f"{fmt(wrong)} said not a chest" if removed else "")

    def _show_buildup(self, snapshot, p):
        start, end = p.start, min(p.end, snapshot.now)
        span = max(timeline.seconds_between(start, end), 1)
        total, points = 0, []
        for event in snapshot.events:
            if start <= event.at < p.end:
                total += event.delta
                points.append((timeline.seconds_between(start, event.at), total))
        counted = [(timeline.seconds_between(start, a), timeline.seconds_between(start, b))
                   for a, b in timeline.clip(timeline.merged((run.start, run.end) for run in snapshot.runs), start, end)]
        first = day_text(timeline.local(start).date()) if p.key != "today" else "Midnight"
        self.buildup.set_series(points, counted, span, (first, "Now"))

    def _show_days(self, snap, bests):
        def day_tile(tile, day, missing):
            if day is None or not (day.monitored or day.totals.recorded):
                tile.set_value(None, missing)
            else:
                tile.set_value(fmt(day.totals.recorded), f"Counted {match_analytics.duration_text(day.counted_seconds)}" if day.monitored else "Your corrections only")

        day_tile(self.today, snap.day(0), "Not counted yet today")
        day_tile(self.yesterday, snap.day(-1), "Not counted")
        week = snap.this_week()
        week_days = week.days if week else []
        self.this_week.set_value(fmt(week.recorded) if week and (week.monitored or week.recorded) else None,
                                 counted_text(week_days) if week_days else "Not counted this week")
        for tile, count in ((self.last7, 7), (self.last30, 30)):
            days = snap.last_days(count)
            seen = [day for day in days if day.monitored or day.totals.recorded]
            tile.set_value(fmt(sum(day.totals.recorded for day in days)) if seen else None,
                           (counted_text(days) + ("" if len(days) == count else f", since {day_text(days[0].day)}")) if seen else "Not counted")
        a = snap.day_averages()
        self.per_monitored.set_value(average_text(a.per_monitored), f"Over {plural(a.monitored, 'day')} counted" if a.monitored else "After your first full day")
        self.per_active.set_value(average_text(a.per_active), f"Over {plural(a.active, 'day')} with chests" if a.active else "After your first full day")
        self.per_calendar.set_value(average_text(a.per_calendar), f"Over {plural(a.calendar, 'day')}, {fmt(a.not_counted)} not counted" if a.calendar else "After your first full day")
        w = snap.week_averages()
        self.per_week.set_value(average_text(w.per_calendar), f"Over {plural(w.calendar, 'week')}" if w.calendar else "After your first full week")
        best = bests.get("day")
        self.best_day.set_value(fmt(best.value) if best else None, day_text(best.start) if best else "A day with chests")
        best = bests.get("week")
        self.best_week.set_value(fmt(best.value) if best else None, f"Week of {best.start.day} {best.start:%b}" if best else "A week with chests")
        self.day_chart.set_bars([charts.Bar(str(day.day.day), day.totals.recorded, day.status, self._day_tip(day)) for day in snap.last_days(30)])
        weeks = snap.weeks()[-12:]
        self.week_chart.set_bars([charts.Bar(f"{w.start.day} {w.start:%b}", w.recorded,
                                             charts.CHESTS if w.active else charts.ZERO if w.monitored else charts.NOT_COUNTED,
                                             f"Week of {day_text(w.start)}: {fmt(w.recorded)} chests, {counted_text(w.days)}") for w in weeks])

    @staticmethod
    def _day_tip(day):
        if day.status == charts.NOT_COUNTED:
            return f"{day_text(day.day)}: not counted"
        return f"{day_text(day.day)}: {fmt(day.totals.recorded)} chests, counted {match_analytics.duration_text(day.counted_seconds)}"

    def _fill_sessions(self, snap):
        duration = match_analytics.duration_text
        rows = snap.session_rows()
        self.sessions_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            s, t = item.session, item.totals
            cells = (when_text(s.start), ("at least " if s.cut_short else "") + duration(s.span_seconds) + (" (now)" if s.in_progress else ""),
                     duration(s.counted_seconds), fmt(t.recorded), UNKNOWN_VALUE if item.per_hour is None else f"{item.per_hour:.1f}",
                     manual_text(t.manual_added, t.manual_removed) or UNKNOWN_VALUE)
            for column, text in enumerate(cells):
                self.sessions_table.setItem(row, column, QTableWidgetItem(text))

    def _fill_table(self, matches):
        newest = (matches[0].run_id, matches[0].match_number) if matches else None
        bar = self.table.verticalScrollBar()
        position = bar.value()
        for row in range(self.table.rowCount()):                # replaced buttons wait to be deleted: they must not stay on screen until then
            old = self.table.cellWidget(row, len(self.COLUMNS) - 1)
            if old is not None:
                old.hide()
        self.table.setRowCount(len(matches))
        for row, match in enumerate(matches):
            seen = minutes_text(match.duration_seconds)
            more = "+" if match.chests_may_be_missing else ""
            net = match.manual_added - match.manual_removed
            mine = f" ({'+' if net > 0 else '−' if net < 0 else '±'}{abs(net)})" if match.manual_added or match.manual_removed else ""
            quality, color = ("Not a match", theme.DIM) if match.excluded else QUALITY_LOOK[match.quality]
            cells = (match.started_at.strftime("%b %d, %H:%M") if match.started_at else UNKNOWN_VALUE,
                     UNKNOWN_VALUE if seen is None else seen if match.duration_is_full else f"{seen} seen",
                     f"{fmt(match.certain)}{more}", f"{fmt(match.approx)}{more}{mine}", rate_cell(match), quality, match.ending)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column == 3 and mine:
                    item.setToolTip(f"Includes your corrections:{manual_part(match.manual_added, match.manual_removed, match.broken_chests)}")
                if column == 5:
                    item.setForeground(QColor(color))
                    if match.interrupted:
                        item.setToolTip("The app closed unexpectedly during this match: only what was saved is shown")
                self.table.setItem(row, column, item)
            action = button("Restore" if match.excluded else "Not a match", "link",
                            tip="Put this match back in your statistics" if match.excluded else "Leave this out of your statistics. Nothing is deleted, and you can restore it.",
                            on_click=lambda _checked=False, m=match: self.set_not_a_match(m, not m.excluded))
            self.table.setCellWidget(row, len(self.COLUMNS) - 1, action)
        self._fit_columns()
        if self._newest is not None and newest != self._newest:
            self.table.scrollToTop()                            # a new match: show it (UX-06)
        else:
            bar.setValue(position)                              # a refresh, a correction or a setting: stay where the reader was
        self._newest = newest

    def _fit_columns(self):
        """Every column as wide as its widest text and the buttons fully visible, with spare room shared out. Qt's Stretch mode squeezes columns
        to nothing in a narrow window, and its own sizing ignores buttons. If the window is too narrow for all of it, the table scrolls sideways."""
        table, header, last = self.table, self.table.horizontalHeader(), len(self.COLUMNS) - 1
        needed = [max(header.sectionSizeHint(column), table.sizeHintForColumn(column)) + 4 for column in range(last)]
        needed.append(max([table.cellWidget(row, last).sizeHint().width() for row in range(table.rowCount()) if table.cellWidget(row, last)] + [0]) + 24)     # a button's size hint comes before its style sheet padding
        spare = max(table.viewport().width() - sum(needed), 0) // last
        for column, width in enumerate(needed):
            table.setColumnWidth(column, width + (spare if column < last else 0))

    def eventFilter(self, watched, event):
        if watched is self.table.viewport() and event.type() == QEvent.Resize:
            self._fit_columns()
        return super().eventFilter(watched, event)

    def set_not_a_match(self, match, flag):
        """A new correction row: the match itself, its chests and your totals are not touched, and it can always be restored."""
        cfg, _ = load_cfg()
        profile = cfg["profile"]
        try:
            match_history.correct_match(paths.APP_DIR / profiles.history_folder(profile["state_base"], profile["id"]), match.run_id, match.match_number, flag)
        except OSError as error:
            show_error(self, f"The correction could not be saved ({error}).")
            return
        self.refresh()


class HelpPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        layout = page_layout(self, "Help & diagnostics", None)
        box, box_layout = card("Start counting in a minute")
        steps = [
            "Someone's live stream:  Video source  >  Livestream URL, paste the link (Twitch or YouTube), Start counting.",
            "A stream, video or game on a screen:  play it FULLSCREEN, pick that Screen as the video source, Start counting.",
            "Your own stream with OBS:  make a scene with only your gameplay, click Start Virtual Camera in OBS, pick "
            "\"OBS Virtual Camera\" here, Start counting.",
            "Show the numbers on stream:  in OBS add a Text (GDI+) source with \"Read from file\" pointing to the file shown "
            "on the Overlay page.",
            "Second PC, capture card or a recorded video? The guide explains every setup.",
        ]
        for step in steps:
            box_layout.addWidget(label(step, wrap=True))
        row = QHBoxLayout()
        row.addWidget(button("Open the full guide", on_click=self._guide))
        row.addStretch(1)
        box_layout.addLayout(row)
        layout.addWidget(box)

        box, box_layout = card("Diagnostics", "A short report about this PC's video devices, OBS Virtual Camera and the "
                                              "program files. It contains no account or personal data.")
        row = QHBoxLayout()
        self.run = button("Run diagnostics", "primary", on_click=self._run)
        row.addWidget(self.run)
        self.copy = button("Copy report", on_click=self._copy)
        self.copy.setEnabled(False)
        row.addWidget(self.copy)
        row.addWidget(button("Open logs folder", on_click=win.open_logs))
        row.addStretch(1)
        box_layout.addLayout(row)
        self.report = QPlainTextEdit()
        self.report.setObjectName("report")
        self.report.setReadOnly(True)
        self.report.setMinimumHeight(260)
        self.report.setPlaceholderText("The report appears here.")
        box_layout.addWidget(self.report)
        layout.addWidget(box)

        box, box_layout = card("Updates", "Nothing is downloaded or installed unless you choose to. Your counts, profiles and settings are kept.")
        self.update_line = label("", "hint", wrap=True)
        box_layout.addWidget(self.update_line)
        row = QHBoxLayout()
        self.update_check = button("Check for updates", on_click=lambda: win.check_for_updates())
        row.addWidget(self.update_check)
        self.update_open = button("Open the update", "primary", on_click=lambda: win.open_update_dialog())
        self.update_open.hide()
        row.addWidget(self.update_open)
        row.addWidget(button("Update settings", "link", on_click=lambda: win.show_page(win.settings_page)))
        row.addStretch(1)
        box_layout.addLayout(row)
        layout.addWidget(box)

        box, box_layout = card("About")
        box_layout.addWidget(label(f"{APP_NAME} v{__version__} ({RELEASE_CHANNEL}). {TAGLINE}.", wrap=True))
        box_layout.addWidget(label("Free and open source (MIT licence). Independent and unofficial: not affiliated with, "
                                   "endorsed by or approved by Epic Games. It only analyses the video picture: it never "
                                   "connects to or changes the game and shows nothing that is not already on screen. "
                                   "Fair play and compatibility: see the full guide.", "hint", wrap=True))
        row = QHBoxLayout()
        row.addWidget(button("Project page", "link", on_click=lambda: QDesktopServices.openUrl(QUrl(REPO_URL))))
        row.addStretch(1)
        box_layout.addLayout(row)
        layout.addWidget(box)
        layout.addStretch(1)
        self._thread = None
        self._result = None
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._check)

    def show_updates(self, m):
        """The Updates card (v0.4.0, UX-01): this version, the last check, and the update when there is one."""
        lines = [f"You have v{__version__}."]
        if not m.packaged:
            lines.append(UM.NOT_PACKAGED)
        elif m.state == UM.CHECKING:
            lines.append("Checking for updates...")
        elif m.state in (UM.AVAILABLE, UM.PREPARING, UM.READY, UM.INSTALLING):
            lines.append(m.indicator_text() + ".")
        elif m.last_check is not None:
            when, _, message = m.last_check
            lines.append(f"Last checked at {when:%H:%M}: {message}")
        else:
            lines.append("Not checked since the app opened.")
        self.update_line.setText(" ".join(lines))
        self.update_check.setEnabled(not m.busy())
        self.update_open.setVisible(m.state in (UM.AVAILABLE, UM.PREPARING, UM.READY))

    def _guide(self):
        guide = paths.APP_DIR / "README.html"
        if guide.exists():
            open_path(guide)
        else:
            QDesktopServices.openUrl(QUrl(REPO_URL + "#readme"))

    def _run(self):
        self.run.setEnabled(False)
        self.report.setPlainText("Running diagnostics (a few seconds)...")

        def work():
            try:
                self._result = run_command(["diagnostics"], timeout=90)[1]
            except Exception as error:
                self._result = f"Diagnostics could not run: {error}"

        self._result = None
        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self._poll.start(200)

    def _check(self):
        if self._result is None:
            return
        self._poll.stop()
        self.report.setPlainText(self._result.strip())
        self.run.setEnabled(True)
        self.copy.setEnabled(True)

    def _copy(self):
        QApplication.clipboard().setText(self.report.toPlainText())
        self.copy.setText("Copied")
        QTimer.singleShot(1500, lambda: self.copy.setText("Copy report"))


# ==================================================================
# main window
# ==================================================================

class NotesView(QTextBrowser):
    """Release notes as Markdown (v0.4.0, UX-02). They come from outside the app, so raw HTML is switched off, nothing is ever fetched (an
    image named in the notes stays empty), and a link opens only if it is one of this project's own GitHub pages."""

    FEATURES = QTextDocument.MarkdownFeature.MarkdownDialectGitHub | QTextDocument.MarkdownFeature.MarkdownNoHTML

    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._follow)
        self.source_text = None

    def show_markdown(self, text):
        if text != self.source_text:
            self.source_text = text
            self.document().setMarkdown(text, self.FEATURES)

    def loadResource(self, kind, url):
        return None

    def _follow(self, url):
        if release_notes.link_allowed(url.toString()):
            QDesktopServices.openUrl(url)


class UpdateDialog(QDialog):
    """Not modal: counting and the rest of the app stay usable while an update is prepared, and closing this only hides it."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(f"{APP_NAME} update")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        self.title = label("", "cardTitle", wrap=True)
        layout.addWidget(self.title)
        self.body = label("", "hint", wrap=True)
        layout.addWidget(self.body)
        self.notes = NotesView()                         # Markdown with raw HTML off: release notes come from outside the app
        self.notes.setMinimumHeight(190)
        layout.addWidget(self.notes)
        self.more = button("", "link", on_click=self._toggle_notes)  # highlights first, the whole text one click away (UX-03)
        layout.addWidget(self.more, 0, Qt.AlignLeft)
        self._full_notes = False
        self.stage = label("", wrap=True)
        layout.addWidget(self.stage)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.detail = label("", "hint", wrap=True)
        layout.addWidget(self.detail)
        self.problem = label("", wrap=True)
        self.problem.setStyleSheet(f"color: {theme.REJECT};")
        layout.addWidget(self.problem)
        layout.addStretch(1)
        row = QHBoxLayout()
        self.page = button("View on GitHub", "link", on_click=self._open_page)
        row.addWidget(self.page)
        row.addStretch(1)
        self.later = button("Later", on_click=self.hide)
        row.addWidget(self.later)
        self.cancel_button = button("Cancel", on_click=self._cancel)
        row.addWidget(self.cancel_button)
        self.primary = button("", "primary", on_click=self._primary)
        row.addWidget(self.primary)
        layout.addLayout(row)

    def _open_page(self):
        update = self.win.updates.update
        if update is not None and update.release.page_url:
            QDesktopServices.openUrl(QUrl(update.release.page_url))

    def _cancel(self):
        self.win.updates.cancel()
        self.refresh()

    def _toggle_notes(self):
        self._full_notes = not self._full_notes
        self.refresh()

    def _primary(self):
        if self.win.updates.state == UM.AVAILABLE:
            self.win.download_update()
        elif self.win.updates.state == UM.READY:
            self.win.restart_and_install()

    def refresh(self):
        m = self.win.updates
        version, state = m.version_text(), m.state
        counting = bool(m.is_counting())
        self.title.setText({UM.AVAILABLE: f"Version v{version} is available", UM.PREPARING: f"Preparing version v{version}",
                            UM.READY: f"Version v{version} is ready to install", UM.INSTALLING: f"Installing version v{version}"}.get(state, ""))
        self.body.setText({UM.AVAILABLE: "Your counts, profiles and settings are kept. You can keep counting while it downloads.",
                           UM.PREPARING: "You can keep counting and close this window. This continues in the background.",
                           UM.READY: "The app will close, install the update and reopen by itself. Your counts, profiles and settings are kept."
                                     + (" Counting will stop first and your counts will be saved." if counting else ""),
                           UM.INSTALLING: m.installing_text}.get(state, ""))
        release = m.update.release if m.update is not None else None
        show_notes = state in (UM.AVAILABLE, UM.READY) and release is not None
        self.notes.setVisible(show_notes)
        short, more = release_notes.highlights(release.notes if release is not None else "")
        if show_notes:
            self.notes.show_markdown(release.notes if self._full_notes and more else short)
        self.more.setVisible(show_notes and more)
        self.more.setText("Show only the highlights" if self._full_notes else "Show all the notes")
        preparing = state == UM.PREPARING
        downloading = preparing and m.status.stage == "downloading" and m.status.total > 0
        self.stage.setVisible(preparing)
        self.stage.setText(m.stage_text() if preparing else "")
        self.progress.setVisible(preparing or state == UM.INSTALLING)
        self.progress.setRange(0, 100 if downloading else 0)             # a moving bar for steps with no meaningful percentage
        if downloading:
            self.progress.setValue(UM.percent(m.status))
        self.detail.setVisible(preparing)
        self.detail.setText(UM.progress_text(m.status) if preparing else "")
        self.problem.setVisible(bool(m.error or m.notice))
        self.problem.setText(m.error or m.notice)
        self.problem.setStyleSheet(f"color: {theme.REJECT if m.error else theme.MUTED};")
        self.page.setVisible(state in (UM.AVAILABLE, UM.READY) and release is not None and bool(release.page_url))
        self.later.setVisible(state in (UM.AVAILABLE, UM.READY))
        self.cancel_button.setVisible(preparing)
        self.cancel_button.setEnabled(not m.cancelling)
        self.primary.setVisible(state in (UM.AVAILABLE, UM.READY, UM.INSTALLING))
        self.primary.setEnabled(state in (UM.AVAILABLE, UM.READY))
        self.primary.setText({UM.AVAILABLE: "Try again" if m.error else "Download && Install", UM.READY: "Restart && Install"}.get(state, "Please wait..."))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1120, 800)
        self.setMinimumSize(920, 640)
        self.window_file = None                 # set by restore_layout() for the real app window only (not tests / self-test)
        self.worker = Worker()
        self.updates = UM.UpdateManager(is_counting=lambda: self.worker.running())
        self.update_dialog = None
        self._update_notice_dismissed = None     # the version whose Dashboard notice was put away with Later
        self._update_ticks = 0
        self._install_pending = False           # counting is being stopped so that an update can be installed
        self._result_watch_until = None         # started by the updater: wait for its verdict before saying anything
        self.mode = "stopped"
        self.counts = (0, 0)
        self.entries = deque(maxlen=LOG_LIMIT)
        self.connected = None
        self.started_at = None
        self.last_status = None
        self.error_seen = False
        self.quit_when_stopped = False
        self.recording = None                   # the worker's current capture ("capture" message), None = not recording
        self.stream_state = None                # Livestream URL connection state ("stream" messages), None = not a stream
        self.match_seen_at = None               # when the last match status arrived, while one is being reported
        self.last_closed_match = None           # the number of the match that closed last in this session, so Analytics hears of a new one
        self.session_match_mode = "off"         # [match] mode when counting started: a change only applies to the next session
        self.last_correction = None             # the newest correction still standing, which Undo and "Why?" act on
        self.correction_memory = {1: "manual", -1: "manual"}      # the reason last chosen for each direction
        self.marks_this_session = 0
        self.hotkey = None
        self.sources = []
        self._source_scan = None
        self._state_mtime = None
        try:
            self.preview_reader = PreviewReader(block_name(uuid.uuid4().hex[:12]))
        except Exception:
            self.preview_reader = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.slow = QTimer(self)
        self.slow.timeout.connect(self._tick_slow)
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._tick_preview)
        self._mark_flash = QTimer(self)                     # the "Marked" confirmation stays visible a few seconds
        self._mark_flash.setSingleShot(True)
        self._mark_flash.timeout.connect(self.update_recording_ui)
        self.obs_link = TextOutputLink().start()            # optional OBS WebSocket output; off unless configured
        self._obs_version = -1
        self._obs_logged = None                             # last OBS WebSocket state written to the activity log

        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._sidebar())
        self.pages = QStackedWidget()
        self.dashboard = Dashboard(self)
        self.analytics = AnalyticsPage(self)
        self.overlay = OverlayPage(self)
        self.settings_page = SettingsPage(self)
        self.help = HelpPage(self)
        for page in (self.dashboard, self.analytics, self.overlay, self.settings_page, self.help):
            self.pages.addWidget(page)
        outer.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        self.dashboard.set_preview_on(load_cfg()[0]["app"]["show_preview"])
        self.fill_profiles()
        self.set_mode("stopped")
        self.read_state(force=True)
        if not C.counter_is_running(paths.APP_DIR / load_cfg()[0]["state"]["path"]):
            self.write_obs_files(quiet=True)          # a fresh unzip/update carries zero placeholders
        self.apply_obs_settings()
        self.overlay.load()
        self.settings_page.load()
        rec = self.dashboard.rec_mode
        rec.setCurrentIndex(max(rec.findData(load_cfg()[0]["capture"]["mode"]), 0))
        rec.currentIndexChanged.connect(lambda _: self.recording_changed())
        self.update_recording_ui()
        self.refresh_viewers()
        self.refresh_sources()
        cfg, warnings = load_cfg()
        for warning in warnings:
            self.add_log({"type": "warn", "text": warning})

        self.timer.start(50)
        self.slow.start(1000)

    # ---- layout
    def _sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(214)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 18, 0, 14)
        layout.setSpacing(6)
        brand = QHBoxLayout()
        brand.setContentsMargins(18, 0, 12, 10)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSETS / "icon_64.png")).scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Chest Counter", "brandName"))
        names.addWidget(label("Fortnite Visual", "brandSub"))
        brand.addLayout(names, 1)
        layout.addLayout(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for name in ("Dashboard", "Analytics", "Overlay", "Settings", "Help & diagnostics"):
            QListWidgetItem(name, self.nav)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._page_changed)
        layout.addWidget(self.nav, 1)
        self.update_link = button("", "link", on_click=self.open_update_dialog)
        self.update_link.hide()
        layout.addWidget(self.update_link)
        version = label(f"v{__version__} · {RELEASE_CHANNEL}", "version")
        version.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(version)
        return side

    def go_to(self, index):
        self.nav.setCurrentRow(index)

    def show_page(self, page):
        self.go_to(self.pages.indexOf(page))

    def _page_changed(self, index):
        self.pages.setCurrentIndex(index)
        page = self.pages.widget(index)
        if page is self.overlay:
            self.overlay.load()
        elif page is self.settings_page:
            self.settings_page.load()
        elif page is self.analytics:
            self.analytics.refresh()
        self.preview_visibility_changed()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "dashboard"):
            self.preview_visibility_changed()               # minimised: nothing is on screen to draw

    # ---- sources
    def refresh_sources(self):
        if self._source_scan is not None and self._source_scan.is_alive():
            return
        self.dashboard.refresh.setEnabled(False)
        self.dashboard.source_hint.setText("Looking for video devices...")
        self._scan_result = None

        def scan():
            from fortnite_chest_counter.input import video_sources as sources
            devices, monitors, windows = [], [], []
            try:
                devices = [n for n, k in sources.list_video_devices() if k in ("video", "none")]
            except Exception:
                pass
            try:
                monitors = sources.list_monitors()
            except Exception:
                pass
            try:
                windows = sources.list_obs_windows()
            except Exception:
                pass
            self._scan_result = (devices, monitors, windows)

        self._source_scan = threading.Thread(target=scan, daemon=True)
        self._source_scan.start()

    def _fill_sources(self, devices, monitors, windows=()):
        live = self.profile_live()
        # Most used first (v0.2.2): a livestream link and a screen need no setup; OBS for streamers' own scene; then the
        # less tested inputs. (The order is only presentation: every entry stays fully supported.)
        items = [("Livestream URL   (Twitch / YouTube - paste the link)", {"source": "stream"})]
        for i, (_, _, w, h) in enumerate(monitors, 1):
            items.append((f"Screen {i}   ·   {w} x {h}", {"source": "desktop", "monitor": i}))
        items.append(("OBS Virtual Camera", {"source": "obs-camera"}))
        if not self.dashboard.url.text():
            self.dashboard.url.setText(live["url"])
            stab = self.dashboard.stability
            stab.setCurrentIndex(max(stab.findData(live["stream_stability"]), 0))
            stab.currentIndexChanged.emit(stab.currentIndex())        # fill the explanation
        names = [n for n in devices if n != "OBS Virtual Camera"]
        if live["source"] == "device" and live["device"] not in names and live["device"] != "OBS Virtual Camera":
            names.append(live["device"])
        for name in names:
            missing = "" if name in devices else "   (not found right now)"
            items.append((f"Capture device:  {name}{missing}   · less tested", {"source": "device", "device": name}))
        titles = [title for title, _ in windows]
        for title, minimized in windows:
            items.append((f"OBS projector:  {title}" + ("   (minimized - restore it)" if minimized else "") + "   · less tested",
                          {"source": "window", "window": title}))
        if live["source"] == "window" and live["window"] and live["window"] not in titles:
            items.append((f"OBS projector:  {live['window']}   (not open right now)   · less tested",
                          {"source": "window", "window": live["window"]}))
        dev_video = os.environ.get("FCC_DEV_VIDEO")
        if dev_video:
            items.append((f"Test video (real time):  {Path(dev_video).name}", {"source": "file", "video": dev_video}))
        current = self.dashboard.source.currentData()
        self.dashboard.source.blockSignals(True)
        self.dashboard.source.clear()
        for text, data in items:
            self.dashboard.source.addItem(text, data)
        wanted = current or {"source": live["source"], "device": live["device"], "monitor": live["monitor"],
                             "window": live["window"]}
        index = 0
        for i, (_, data) in enumerate(items):
            if data["source"] == wanted.get("source") and all(data[k] == wanted.get(k) for k in data if k != "source"):
                index = i
                break
        self.dashboard.source.setCurrentIndex(index)
        self.dashboard.source.blockSignals(False)
        self.dashboard.url_row.setVisible((self.dashboard.source.currentData() or {}).get("source") == "stream")
        self._obs_camera_found = "OBS Virtual Camera" in devices
        self._projectors_found = bool(windows)
        self.update_source_hint()
        self.dashboard.refresh.setEnabled(True)

    def update_source_hint(self):
        """One short line for the selected source: what it needs (and, for the less tested ones, that they are)."""
        kind = (self.dashboard.source.currentData() or {}).get("source")
        found = getattr(self, "_obs_camera_found", True)
        text = {
            "stream": "",
            "desktop": "Counts what is on that screen: play the stream (or the game) FULLSCREEN there. A small player inside "
                       "a web page is too small to read.",
            "obs-camera": "For your own OBS scene with the gameplay: click Start Virtual Camera in OBS." if found else
                          "OBS Virtual Camera was not found: open OBS Studio (28 or newer), click Start Virtual Camera, then "
                          "Refresh.",
            "device": "Reads the device directly. Less tested: not yet with a physical capture card. Most cards work with one "
                      "program at a time - if OBS uses it, pick OBS Virtual Camera instead.",
            "window": "Reads an OBS projector window (keep it open, not minimized). Less tested: not yet with a real OBS "
                      "projector.",
        }.get(kind, "")
        if kind == "obs-camera" and not getattr(self, "_projectors_found", True):
            text += (" Virtual Camera busy, or the capture card used by OBS? In OBS right-click your gameplay source > "
                     "Windowed Projector (Source), then click Refresh.")
        self.dashboard.source_hint.setText(text)
        self.dashboard.source_hint.setVisible(bool(text))

    def select_source(self, wanted):
        """Select the source list entry that matches `wanted` (a [live]-style dict). -> True if one was found."""
        box = self.dashboard.source
        for i in range(box.count()):
            data = box.itemData(i) or {}
            if data.get("source") == wanted.get("source") and all(data[k] == wanted.get(k) for k in data if k != "source"):
                box.setCurrentIndex(i)
                return True
        return False

    # ---- count profiles (profiles.py): one counts at a time, each with its own counts and video source
    def profile_live(self):
        """config.toml [live] with the active profile's remembered source on top."""
        cfg, _ = load_cfg()
        live = dict(cfg["live"])
        try:
            reg = profiles.load(cfg["profile"]["state_base"])
            remembered = profiles.active(reg).get("source") or {}
        except (OSError, profiles.ProfileError):
            remembered = {}
        if remembered.get("source"):
            live.update(remembered)
        return live

    def profile_base(self):
        return load_cfg()[0]["profile"]["state_base"]

    def fill_profiles(self):
        base = self.profile_base()
        reg = profiles.load(base)
        box = self.dashboard.profile
        box.blockSignals(True)
        box.clear()
        for p in reg["profiles"]:
            box.addItem(p["name"], p["id"])
        box.setCurrentIndex(max(box.findData(reg["active"]), 0))
        box.blockSignals(False)
        self.dashboard.profile_delete.setEnabled(reg["active"] != profiles.DEFAULT_ID and not self.worker.running())
        name = profiles.active(reg)["name"]
        self.setWindowTitle(APP_NAME if len(reg["profiles"]) == 1 else f"{APP_NAME}  -  {name}")
        return reg

    def _profile_busy(self):
        """A counter (this window's or a console one) is writing the active profile's counts right now."""
        if self.worker.running():
            return True
        return C.counter_is_running(load_cfg()[0]["state"]["path"])

    def switch_profile(self, index):
        wanted = self.dashboard.profile.itemData(index)
        cfg, _ = load_cfg()
        if wanted is None or wanted == cfg["profile"]["id"]:
            return
        if self._profile_busy():
            show_error(self, "Stop counting before switching to another profile.")
            self.fill_profiles()
            return
        try:
            profiles.set_active(cfg["profile"]["state_base"], wanted)
        except (OSError, profiles.ProfileError) as error:
            show_error(self, f"Could not switch the profile: {error}")
            self.fill_profiles()
            return
        self.profile_changed()

    def profile_changed(self):
        """After a switch / new profile: its counts, its OBS text, its video source."""
        reg = self.fill_profiles()
        self.read_state(force=True)
        self.write_obs_files(quiet=True)              # OBS shows the selected profile
        live = self.profile_live()
        self.select_source({"source": live["source"], "device": live["device"], "monitor": live["monitor"],
                            "window": live["window"]})
        self.dashboard.url.setText(live["url"])
        stab = self.dashboard.stability
        stab.setCurrentIndex(max(stab.findData(live["stream_stability"]), 0))
        self.dashboard.url_row.setVisible((self.dashboard.source.currentData() or {}).get("source") == "stream")
        self.add_log({"type": "info", "text": f"Profile: {profiles.active(reg)['name']}  -  CERTAIN {fmt(self.counts[0])}"
                                              f" / APPROX {fmt(self.counts[1])}. OBS now shows this profile."})

    def new_profile(self):
        if self._profile_busy():
            show_error(self, "Stop counting before making a new profile.")
            return
        name, ok = QInputDialog.getText(self, "New profile", "Name of the new profile (for example the streamer's name).\n"
                                                             "It starts at 0 and keeps its own counts and video source:")
        if not ok:
            return
        try:
            profiles.create(self.profile_base(), name)
        except (OSError, profiles.ProfileError) as error:
            show_error(self, str(error))
            return
        self.profile_changed()

    def rename_profile(self):
        cfg, _ = load_cfg()
        current = cfg["profile"]
        name, ok = QInputDialog.getText(self, "Rename profile", "New name (the counts stay the same):",
                                        QLineEdit.Normal, current["name"])
        if not ok or name.strip() == current["name"]:
            return
        try:
            profiles.rename(current["state_base"], current["id"], name)
        except (OSError, profiles.ProfileError) as error:
            show_error(self, str(error))
            return
        self.fill_profiles()

    def delete_profile(self):
        cfg, _ = load_cfg()
        current = cfg["profile"]
        if current["id"] == profiles.DEFAULT_ID or self._profile_busy():
            return
        if not ask(self, "Delete profile?", f'Delete the profile "{current["name"]}" (CERTAIN {fmt(self.counts[0])} / '
                                            f'APPROX {fmt(self.counts[1])})?\n\nIt disappears from the list. Its counts '
                                            f"are kept in a backup file in state\\profiles\\deleted.", "Delete", danger=True):
            return
        try:
            profiles.delete(current["state_base"], current["id"])
        except (OSError, profiles.ProfileError) as error:
            show_error(self, str(error))
            return
        self.profile_changed()

    # ---- counting
    def toggle_counting(self):
        if self.worker.running():
            self.stop_counting()
        else:
            self.start_counting()

    def start_counting(self):
        data = self.dashboard.source.currentData()
        if not data or self.worker.running() or self._install_pending or self.updates.state == UM.INSTALLING:
            return
        cfg, _ = load_cfg()
        argv = ["live", "--gui", "--profile", cfg["profile"]["id"]]
        if self.preview_reader is not None:
            argv += ["--preview", self.preview_reader.name]
        if data["source"] == "file":                                 # developers: FCC_DEV_VIDEO (+ FCC_DEV_VIDEO_START)
            argv += ["--source", "file", "--video", data["video"]]
            if os.environ.get("FCC_DEV_VIDEO_START"):
                argv += ["--start", os.environ["FCC_DEV_VIDEO_START"]]
        else:
            values = {"source": data["source"]}
            if data["source"] == "device":
                values["device"] = data["device"]
            if data["source"] == "desktop":
                values["monitor"] = data["monitor"]
            if data["source"] == "window":
                values["window"] = data["window"]
            if data["source"] == "stream":
                url = self.dashboard.url.text().strip()
                if not url.lower().startswith(("http://", "https://")) or any(c.isspace() for c in url):
                    show_error(self, "Paste the full link of the live stream, for example\n"
                                     "https://www.twitch.tv/channel  or  https://www.youtube.com/watch?v=...")
                    return
                values["url"] = url
                values["stream_stability"] = self.dashboard.stability.currentData()
            try:
                C.update_config_file(config_file(), "live", values)   # the console version starts the same way
                profiles.remember_source(cfg["profile"]["state_base"], cfg["profile"]["id"], values)
            except (C.UserError, OSError, profiles.ProfileError) as error:
                show_error(self, f"Could not save the video source choice: {error}")
                return
        self.dashboard.banner.hide()
        self.error_seen = False
        self.connected = None
        self.last_status = None
        self.session_match_mode = cfg["match"]["mode"]
        self.last_closed_match = None           # match numbers start again in every session
        try:
            self.worker.start(argv)
        except OSError as error:
            show_error(self, f"The counter could not start ({error}). Extract the whole zip again and keep every file "
                             "and folder together.")
            return
        whose = f" (profile {cfg['profile']['name']})" if self.dashboard.profile.count() > 1 else ""
        self.add_log({"type": "info", "text": f"Starting{whose}: {self.dashboard.source.currentText().split('   ')[0]} ..."})
        self.set_mode("connecting")

    def stop_counting(self):
        if self.worker.running():
            self.set_mode("stopping")
            self.worker.stop()
            QTimer.singleShot(30000, self._stop_timeout)   # a diagnostic recording may need a few seconds to finish

    def _stop_timeout(self):
        if self.mode == "stopping" and self.worker.running():
            self.worker.kill()          # counts are saved after every chest; this only skips the final summary

    def set_mode(self, mode):
        self.mode = mode
        d = self.dashboard
        text, color = {"stopped": ("Not counting", theme.MUTED), "connecting": ("Connecting", theme.INFO),
                       "counting": ("Counting", theme.CERTAIN), "stopping": ("Stopping", theme.APPROX),
                       "error": ("Not counting", theme.REJECT)}[mode]
        d.set_pill(text, color)
        running = mode in ("connecting", "counting", "stopping")
        d.start.setText({"connecting": "Cancel", "counting": "Stop counting", "stopping": "Stopping..."}.get(mode, "Start counting"))
        restyle(d.start, "danger" if mode in ("connecting", "counting") else "primary")
        d.start.setEnabled(mode != "stopping")
        d.source.setEnabled(not running)
        for widget in (d.profile, d.profile_new, d.profile_rename):
            widget.setEnabled(not running)
        d.profile_delete.setEnabled(not running and d.profile.currentData() != profiles.DEFAULT_ID)
        d.url.setEnabled(not running)
        d.stability.setEnabled(not running)
        d.refresh.setEnabled(not running)
        d.analyse.setEnabled(not running)
        d.stability_hint.setVisible(not running)
        d.url_note.setVisible(not running)
        if mode == "connecting":
            self.marks_this_session = 0
            d.game_manual_by_match.clear()                    # match numbers start again with each run
            d.game_target = None
        if not running:
            self.recording = None
        self.update_recording_ui()
        if mode == "counting":
            self.started_at = time.monotonic()
        if not running:
            self.started_at = None
            self.stream_state = None
            self.match_seen_at = None
            d.match.setText("")
            d.match_row.hide()
            d.game_last.setText("")
            d.game_last.hide()
            d.metrics.setText("Not counting.")
        self.update_game_idle()
        self.update_correction_buttons()
        if not running:
            for panel in (d.preview, d.mini_preview):
                panel.view.setStyleSheet("")
                panel.clear()
        d._panels()

    def _tick(self):
        if self._source_scan is not None and self._scan_result is not None:
            devices, monitors, windows = self._scan_result
            self._scan_result = None
            self._source_scan = None
            self._fill_sources(devices, monitors, windows)
        for message in self.worker.drain():
            self.handle(message)
        version, status = self.obs_link.status()
        if version != self._obs_version:
            self._obs_version = version
            self.obs_status_changed(status)
        self._update_ticks += 1
        if self._update_ticks % 4 == 0 and self.updates.poll():
            self.update_changed()

    # ---- updates (update_manager.py holds the state; checking and preparing run on their own threads)
    def after_start(self, installing=False):
        """Called once the window is up. Not from the constructor, so the self-test can never touch the network."""
        try:
            update_install.clear_orphaned_journal()
            if installing:                             # the updater started this copy to prove itself: its verdict comes later
                self._result_watch_until = time.monotonic() + RESULT_WATCH_SECONDS
                return
            self.show_update_result()
            if load_cfg()[0]["update"]["check_automatically"]:
                QTimer.singleShot(AUTO_CHECK_DELAY_MS, self.auto_check)
        except Exception as error:                     # updates must never stop the app from opening
            self.add_log({"type": "warn", "text": f"Could not check the last update ({type(error).__name__}: {error})."})

    def auto_check(self):
        if self.updates.check(manual=False):
            self.update_changed()

    def check_for_updates(self):
        self.updates.check(manual=True)
        self.update_changed()

    def show_update_result(self):
        """What the last installation did, once. -> True if there was a result."""
        result = update_install.last_result()
        if result is None:
            if self._result_watch_until is None and update_install.transaction_left_open():
                self.dashboard.show_notice("An update did not finish. Close the app and open it again from its .exe. If this message comes back, "
                                           "extract the latest zip over the program folder. Your counts are safe.", theme.REJECT)
            return False
        self._result_watch_until = None
        notice = UM.describe_result(result, __version__)
        update_install.acknowledge_result()
        if notice:
            level, text = notice
            self.dashboard.show_notice(text, {"success": theme.CERTAIN, "rolled_back": theme.APPROX}.get(level, theme.REJECT))
            self.add_log({"type": "info" if level == "success" else "warn", "text": text})
        QTimer.singleShot(8000, update_install.cleanup_finished)
        return True

    def update_changed(self):
        m = self.updates
        text = m.indicator_text()
        self.update_link.setText(text)
        self.update_link.setVisible(bool(text))
        self.settings_page.update_status.setText(m.check_message)
        report = m.take_report()                     # an automatic check: one quiet line, so it is never silent (UX-01)
        if report is not None:
            level, line = release_notes.check_report(*report, __version__)
            self.add_log({"type": level, "text": line})
        self.help.show_updates(m)
        self.show_update_notice()
        self.settings_page.check_button.setEnabled(not m.busy())
        self.dashboard.start.setEnabled(m.state != UM.INSTALLING and self.mode != "stopping")
        if self.update_dialog is not None:
            self.update_dialog.refresh()
        if m.take_open_request():
            self.open_update_dialog()
        if m.take_install_started():
            self.close()                               # the installer is waiting for this window to go

    def show_update_notice(self):
        m, d = self.updates, self.dashboard
        version = m.version_text()
        visible = m.state in (UM.AVAILABLE, UM.READY) and bool(version) and version != self._update_notice_dismissed
        if visible:
            d.update_notice_text.setText(f"Version v{version} is available. Your counts, profiles and settings are kept." if m.state == UM.AVAILABLE
                                         else f"Version v{version} is ready to install.")
        d.update_notice.setVisible(visible)

    def dismiss_update_notice(self):
        self._update_notice_dismissed = self.updates.version_text()
        self.dashboard.update_notice.hide()

    def open_update_dialog(self):
        if self.update_dialog is None:
            self.update_dialog = UpdateDialog(self)
        self.update_dialog.refresh()
        self.update_dialog.show()
        self.update_dialog.raise_()

    def download_update(self):
        if self.updates.start_preparing(UM.bandwidth_policy(load_cfg()[0]["update"])):
            self.update_changed()

    def _install_blocker(self):
        """Something that must finish first, so nothing still runs from the program folder when the installer starts."""
        if QApplication.activeModalWidget() is not None:
            return "Close the other open window first, then try again."
        if self.help._thread is not None and self.help._thread.is_alive():
            return "Wait for the diagnostics to finish, then try again."
        return None

    def restart_and_install(self):
        m = self.updates
        if m.state != UM.READY or self._install_pending:
            return
        blocker = self._install_blocker()
        if blocker:
            m.refuse_install(blocker)
            self.update_changed()
            return
        if not self.worker.running():
            self._launch_installer()
            return
        if not ask(self, "Stop counting and install?", f"Counting will stop and your counts will be saved. The app will then close, install v{m.version_text()} "
                                                       "and reopen by itself.", "Stop counting and install"):
            return
        self._install_pending = True
        m.begin_stopping()
        self.stop_counting()
        QTimer.singleShot(INSTALL_STOP_DEADLINE_MS, self._install_stop_deadline)
        self.update_changed()

    def _install_stop_deadline(self):
        if self._install_pending:
            self._refuse_install_after_stop()

    def _refuse_install_after_stop(self):
        self._install_pending = False
        self.updates.refuse_install("Counting did not stop cleanly, so the update was not installed. Your counts are safe.")
        self.set_mode("error" if self.error_seen else self.mode if self.worker.running() else "stopped")
        self.update_changed()

    def _launch_installer(self):
        cfg, _ = load_cfg()
        state_folder = Path(cfg["profile"]["state_base"]).parent
        try:
            state_dir = state_folder.resolve().relative_to(paths.APP_DIR.resolve()).as_posix()
        except ValueError:
            state_dir = str(state_folder)                  # kept outside the program folder by config.toml
        data_paths = [state_folder, *(paths.APP_DIR / cfg[section][key] for section, key in (("state", "obs_dir"), ("logging", "dir"), ("capture", "dir")))]
        self.updates.install(state_dir, data_paths)
        self.update_changed()

    # ---- OBS WebSocket output (obs/link.py runs it in its own thread; this only configures and shows it)
    def apply_obs_settings(self, reconnect=False):
        cfg, _ = load_cfg()
        ws = cfg["obs_websocket"]
        overlay = (paths.APP_DIR / cfg["state"]["obs_dir"] / "chest_counter.txt").resolve()
        password = obs_credentials.load_password() if ws["enabled"] else ""
        self.obs_link.configure(ws["enabled"], ws["host"], ws["port"], password, ws["source"], ws["source_uuid"], overlay)
        if reconnect:
            self.obs_link.reconnect()

    def obs_status_changed(self, status):
        self.overlay.show_obs_status(status)
        line = self.dashboard.obs_line
        if status["state"] == "off":
            line.hide()
        else:
            name, color = OBS_STATES.get(status["state"], (status["state"], theme.MUTED))
            line.setText(f"OBS WebSocket: {status['message'] if status['state'] == 'live' else name}")
            line.setStyleSheet(f"color: {color};")
            line.show()
        previous = self._obs_logged
        if status["state"] != previous and status["state"] != "connecting":
            self._obs_logged = status["state"]
            if status["state"] != "off" or previous is not None:
                self.add_log({"type": "warn" if OBS_STATES.get(status["state"], ("", ""))[1] == theme.REJECT else "info",
                              "text": f"OBS WebSocket: {status['message']}"})
        # follow a rename in OBS / remember the source's OBS id (so a later rename is followed too)
        if status["state"] in ("live", "reads_file") and status.get("source"):
            ws = load_cfg()[0]["obs_websocket"]
            if (ws["source"], ws["source_uuid"]) != (status["source"], status.get("uuid", "")):
                try:
                    C.update_config_file(config_file(), "obs_websocket", {"source": status["source"],
                                                                          "source_uuid": status.get("uuid", "")})
                except (C.UserError, OSError):
                    pass

    def handle(self, message):
        kind = message.get("type")
        self.add_log(message)
        if kind == "connected":
            self.connected = message
            self.set_mode("counting")
            self.add_log({"type": "info", "text": "Counting. Chests are saved the moment they are counted."
                          + ("" if message.get("persist", True) else " (Saving is turned off in config.toml.)")})
        elif kind in ("counts", "event", "status", "progress"):
            if message.get("certain") is not None and message.get("approx") is not None:
                self.set_counts(message["certain"], message["approx"], flash=kind == "event")
            if kind == "status":
                self.last_status = message
            if kind == "counts" and message.get("overlay") is not None:
                self.dashboard.viewers.setText(message["overlay"].replace("\n", "   /   "))
        elif kind == "types":
            self.dashboard.types.setText(types_text(message.get("breakdown")))
        elif kind == "stream":
            self.show_stream_state(message.get("state"))
        elif kind == "match":
            self.show_match(message)
        elif kind == "correction":
            self.correction_done(message)
        elif kind == "error":
            self.error_seen = True
            self.dashboard.show_banner(str(message.get("text", "")))
        elif kind == "mark":
            self.marks_this_session += 1
            kept = (" - the video before and after it is kept" if message.get("recorded") else
                    " - noted in the session log only (no recording was running)")
            self.add_log({"type": "info", "text": f"Marked {message.get('stamp', '')}{kept}."})
            self.dashboard.rec_status.setText(f"\u2713  Marked {message.get('stamp', '')}{kept}.")
            self.dashboard.rec_status.setStyleSheet(f"color: {theme.CERTAIN};")
            self._mark_flash.start(4000)
        elif kind == "capture":
            if message.get("state") == "recording":
                self.recording = message
                rec = self.dashboard.rec_mode                   # show what the worker really records
                index = rec.findData(message.get("mode"))
                if index >= 0 and index != rec.currentIndex():
                    rec.blockSignals(True)
                    rec.setCurrentIndex(index)
                    rec.blockSignals(False)
                self.add_log({"type": "info", "text": f"Diagnostic recording on ({RECORDING_TEXT.get(message.get('mode'), '')})"
                              f": {message.get('folder', '')}"})
            elif message.get("state") == "off":
                self.recording = None
                if message.get("mode") not in (None, "off"):            # asked for a recording, but it could not start
                    rec = self.dashboard.rec_mode
                    rec.blockSignals(True)
                    rec.setCurrentIndex(rec.findData("off"))
                    rec.blockSignals(False)
                    self.add_log({"type": "warn", "text": "The diagnostic recording could not start (see the warning above); "
                                                          "counting continues. Choose a recording mode again to retry."})
                else:
                    self.add_log({"type": "info", "text": "Diagnostic recording off."})
            elif message.get("state") == "saved":
                if self.recording and self.recording.get("folder") == message.get("folder"):
                    self.recording = None
                self.add_log({"type": "info", "text": f"Diagnostic recording saved: {message.get('clips', 0)} clip(s), "
                              f"{message.get('video_mb', 0)} MB, {message.get('events', 0)} decisions, "
                              f"{message.get('marks', 0)} marks -> {message.get('folder', '')}"})
            self.update_recording_ui()
        elif kind == "stopped":
            minutes = (message.get("seconds") or 0) / 60
            self.add_log({"type": "line", "text": f"Stopped ({message.get('stop_reason', '')}). Analysed "
                          f"{message.get('frames_processed', 0):,} frames in {minutes:.1f} min, "
                          f"{message.get('frames_dropped', 0):,} skipped."})
        elif kind == "exit":
            code = message.get("code")
            if code not in (0, None) and not self.error_seen:
                tail = "\n".join(self.worker.stderr_tail[-6:])
                self.dashboard.show_banner("The counter stopped unexpectedly. Your counts are safe (they are saved after "
                                           "every chest). If it keeps happening, run Help & diagnostics and send the report "
                                           "and the logs folder." + (f"\n\n{tail}" if tail else ""))
                self.error_seen = True
            self.set_mode("error" if self.error_seen else "stopped")
            self.read_state(force=True)
            if self.pages.currentWidget() is self.analytics:
                self.analytics.refresh()                # this session's matches have just been saved
            if self._install_pending:
                if code in (0, None):                  # stopped and saved normally
                    self._install_pending = False
                    self._launch_installer()
                else:
                    self._refuse_install_after_stop()
            if self.quit_when_stopped:
                self.close()

    def show_match(self, message):
        """The Dashboard's match line. Read-only: it changes nothing but its own text."""
        if self.mode not in ("connecting", "counting", "stopping"):
            return
        text, color = match_line(message)
        d = self.dashboard
        d.match.setText(text + match_summary(message))
        d.match.setStyleSheet(f"color: {color};")
        d.match_row.show()
        d.show_game(message, text, color)
        closed = (message.get("last_match") or {}).get("match_number")
        if closed is not None and closed != self.last_closed_match:     # a match just ended: Analytics shows it without a Refresh (UX-07)
            self.last_closed_match = closed
            self.analytics.match_ended()
        self.match_seen_at = None if message.get("failed") or message.get("unavailable") else time.monotonic()

    def _check_match_video(self):
        """The worker reports once a second of video, so silence means no video is arriving."""
        if self.match_seen_at is not None and time.monotonic() - self.match_seen_at >= MATCH_STALE_SECONDS:
            self.dashboard.game_doubt.hide()
            for line in (self.dashboard.match, self.dashboard.game_status):
                line.setText("No video right now")
                line.setStyleSheet(f"color: {theme.MUTED};")
            self.dashboard.show_game_rate(None, "No video right now")      # the counts stay: they were real, but the rate is no longer current

    def update_game_idle(self):
        """What the Game view says while no match status is coming in."""
        d = self.dashboard
        if not d.match_row.isHidden():
            return
        running = self.mode in ("connecting", "counting", "stopping")
        mode = self.session_match_mode if running else load_cfg()[0]["match"]["mode"]
        if mode == "on":
            d.show_game_idle("Waiting for the first picture" if running else "Not counting", "Match status appears here while counting.", False)
        elif running:
            d.show_game_idle("Match tracking is off for this session", "It can be turned on in Settings, for the next time you start counting.", True)
        else:
            d.show_game_idle("Match tracking is off", "Turn it on in Settings to follow your matches here and build a match history. "
                                                      "It never changes your counts or what OBS shows.", True)

    def show_stream_state(self, state):
        """Livestream URL: the Dashboard pill and the preview say when the stream is not delivering video."""
        if state not in STREAM_STATES or STREAM_STATES[state][1] is None:
            return                                      # "incomplete" is a log line only
        color, pill, overlay = STREAM_STATES[state]
        self.stream_state = state
        if state == "no_video":
            self.last_status = None                     # the last rate is no longer true
        if self.mode == "counting":
            self.dashboard.set_pill(pill, color)
        for preview in (self.dashboard.preview, self.dashboard.mini_preview):
            if overlay:
                preview.clear(overlay)
                preview.view.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 600;")
            else:
                preview.view.setStyleSheet("")

    def set_counts(self, certain, approx, flash=False):
        changed = (certain, approx) != self.counts
        self.counts = (certain, approx)
        self.dashboard.certain.set_value(certain, flash=flash and changed)
        self.dashboard.approx.set_value(approx, flash=flash and changed)
        self.dashboard.console_counts.setText(console_counts_text(certain, approx))
        self.update_correction_buttons()
        if changed:
            self.refresh_viewers()

    def refresh_viewers(self):
        cfg, _ = load_cfg()
        text = C.overlay_text(cfg["display"], {"certain": self.counts[0], "approximate": self.counts[1]})
        self.dashboard.viewers.setText(text.replace("\n", "   /   "))

    def read_state(self, force=False):
        cfg, _ = load_cfg()
        path = paths.APP_DIR / cfg["state"]["path"]
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = None
        if not force and mtime == self._state_mtime:
            return
        self._state_mtime = mtime
        counts = read_counts(path)
        self.set_counts(*(counts or (0, 0)))
        self.dashboard.types.setText(types_text(read_types(path) or C.type_breakdown(C.fresh_state())))
        self.refresh_corrections()

    def write_obs_files(self, quiet=False):
        """The OBS text files from the saved counter (e.g. after an update replaced them with zero placeholders)."""
        try:
            cfg, _ = load_cfg()
            C.preflight(cfg, needs_video=False)
            session = C.CounterSession(cfg)
            session.write_obs()
        except (C.UserError, OSError) as error:
            if not quiet:
                show_error(self, str(error))

    def _tick_slow(self):
        if self._result_watch_until is not None:
            if time.monotonic() > self._result_watch_until:
                self._result_watch_until = None
            else:
                self.show_update_result()
        self._check_match_video()
        if not self.worker.running():
            self.read_state()
        elif self.mode == "counting" and self.started_at is not None:
            elapsed = int(time.monotonic() - self.started_at)
            parts = [("\u25cf REC   " if self.recording else "")
                     + f"Counting for {elapsed // 3600}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}"]
            c = self.connected or {}
            if c.get("resolution"):
                parts.append(f"video {c['resolution'][0]} x {c['resolution'][1]}"
                             + (f" @ {c['input_fps']:g} fps" if c.get("input_fps") else ""))
            s = self.last_status
            if self.stream_state == "no_video":
                parts.append("no new video")
            elif s:
                parts.append(f"analysing {s['fps']:.1f} pictures/s")
                if s.get("backlog_s") is not None:
                    parts.append(f"backlog {s['backlog_s']:.0f} s")
                parts.append(f"{s['ms_per_frame']:.0f} ms each")
                if s.get("dropped"):
                    parts.append(f"{fmt(s['dropped'])} skipped")
            self.dashboard.metrics.setText("   ·   ".join(parts))

    # ---- activity log
    def add_log(self, message):
        if message.get("type") in ("warn", "error"):
            self.dashboard.note_warning()
        for debug_only, html in log_entries(message):
            self.entries.append((debug_only, html))
            if not debug_only or self.verbosity() == "debug":
                self.dashboard.log.appendHtml(html)

    def verbosity(self):
        return self.dashboard.detail.currentData()

    def render_log(self):
        log = self.dashboard.log
        log.clear()
        debug = self.verbosity() == "debug"
        for debug_only, html in self.entries:
            if debug or not debug_only:
                log.appendHtml(html)

    def clear_log(self):
        self.entries.clear()
        self.dashboard.log.clear()

    def open_logs(self):
        cfg, _ = load_cfg()
        folder = paths.APP_DIR / cfg["logging"]["dir"]
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    # ---- preview
    def active_preview(self):
        """The one preview on screen right now, or None. One reader and one timer feed it, so two can never run at once."""
        d = self.dashboard
        if not d.show_preview.isChecked() or self.isMinimized() or self.pages.currentWidget() is not d:
            return None
        return {OVERVIEW_VIEW: d.mini_preview, GAME_VIEW: d.preview}.get(d.views.currentIndex())

    def remember_preview(self, on):
        try:
            C.update_config_file(config_file(), "app", {"show_preview": on})
        except (C.UserError, OSError):
            pass                                            # only a convenience: the preview itself has already changed

    def preview_visibility_changed(self):
        wanted = self.preview_reader is not None and self.active_preview() is not None and self.mode in ("connecting", "counting")
        if self.preview_reader is not None:
            self.preview_reader.set_wanted(wanted)
        if wanted:
            self.preview_timer.start(1000 // 8)
        else:
            self.preview_timer.stop()

    def _tick_preview(self):
        if self.stream_state in ("buffering", "ad", "reconnecting", "offline", "no_video"):
            return                                      # keep the status text instead of the last (stale) picture
        panel = self.active_preview()
        frame = self.preview_reader.read() if panel is not None else None
        if frame is not None:
            _, width, height, data = frame
            panel.show_frame(width, height, data)

    # ---- counter actions
    def _cfg_for_actions(self):
        cfg, _ = load_cfg()
        for section, key in (("state", "path"), ("state", "obs_dir"), ("logging", "dir")):
            cfg[section][key] = str(paths.APP_DIR / cfg[section][key])
        return cfg

    def edit_counts(self):
        dialog = CountsDialog(self, *self.counts)
        if dialog.exec() != QDialog.Accepted:
            return
        self._set(dialog.certain.value(), dialog.approx.value(), "set_count")

    def reset_counts(self):
        whose = "" if self.dashboard.profile.count() <= 1 else f' of the profile "{self.dashboard.profile.currentText()}"'
        if ask(self, "Reset the counter?", f"Set both counts{whose} to 0? This cannot be undone.", "Reset to 0", danger=True):
            self._set(0, 0, "reset")

    def _set(self, certain, approx, action):
        try:
            session = C.set_counts(self._cfg_for_actions(), certain, approx, action)
        except (C.UserError, OSError) as error:
            show_error(self, str(error))
            return
        self.set_counts(session.state["certain"], session.state["approximate"], flash=True)
        self.refresh_corrections()
        what = "reset to 0" if action == "reset" else f"set to CERTAIN {fmt(certain)} / APPROX {fmt(approx)}"
        self.add_log({"type": "info", "text": f"Counter {what}."
                      + (" The running counter picks it up within a second." if self.worker.running() else "")})

    # ---- chest corrections: +1 and -1 on APPROX. A +1 is not a claim that the detector failed.
    def correct_chest(self, delta):
        self._send_correction({"id": uuid.uuid4().hex, "delta": delta, "reason": self.correction_memory[delta]})

    def correct_match_chest(self, delta):
        """The Game view's +1 and -1: the same correction as Overview's, also saved with the match it was made for. Only while counting, since
        only the running session knows the match."""
        target = self.dashboard.game_target
        if self.mode != "counting" or target is None:
            return
        reason = self.dashboard.game_reason.currentData() if delta > 0 else self.correction_memory[delta]
        self._send_correction({"id": uuid.uuid4().hex, "delta": delta, "reason": reason, "match_number": target})

    def undo_correction(self):
        if self.last_correction is not None:
            self._send_correction({"id": uuid.uuid4().hex, "undoes": self.last_correction["id"]})

    def _send_correction(self, request):
        """While counting, the worker makes the change, so only one program ever writes the counter file."""
        if self.worker.running():
            if not self.worker.send("correct " + json.dumps(request)):
                self.add_log({"type": "warn", "text": "The correction could not be sent: the counter is stopping. Try again once it has stopped."})
            return
        try:
            session, result = C.apply_chest_correction(self._cfg_for_actions(), request)
        except (C.UserError, OSError) as error:
            show_error(self, str(error))
            return
        self.set_counts(session.state["certain"], session.state["approximate"], flash=True)
        self.dashboard.types.setText(types_text(C.type_breakdown(session.state)))
        self.correction_done(result)

    def correction_done(self, result):
        if result.get("status") == "refused":
            self.add_log({"type": "warn", "text": f"Correction not applied: {result.get('message', '')}"})
        elif result.get("status") == "applied":
            what = "undone" if result.get("undoes") else "applied"
            number = result.get("match_number")
            self.add_log({"type": "info", "text": f"Manual correction {what}: APPROX {result.get('delta', 0):+d}" + (f", match {number}." if number else ".")})
            if number is not None:
                tally = self.dashboard.game_manual_by_match.setdefault(number, [0, 0])
                original = -result["delta"] if result.get("undoes") else result["delta"]          # undoing a +1 takes back that +1
                tally[0 if original > 0 else 1] += -1 if result.get("undoes") else 1
                self.dashboard.refresh_game_manual()
        self.refresh_corrections()

    def _history_folder(self):
        profile = load_cfg()[0]["profile"]
        return paths.APP_DIR / profiles.history_folder(profile["state_base"], profile["id"])

    def refresh_corrections(self):
        """The line under the counts: what the detector counted, what you changed, and the total."""
        d = self.dashboard
        try:
            state = json.loads((paths.APP_DIR / load_cfg()[0]["state"]["path"]).read_text(encoding="utf-8"))
            totals = match_history.correction_totals(match_history.read_chest_corrections(self._history_folder()), C.counter_token(state))
            approx = state["approximate"]
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            totals, approx = {"standing": [], "net": 0}, 0
        standing = totals["standing"]
        self.last_correction = standing[-1] if standing else None
        d.correction_row.setVisible(bool(standing))
        if not standing:
            return
        d.correction_text.setText(f"Detector {fmt(approx - totals['net'])}   ·   Manual {totals['net']:+d}   ·   Total {fmt(approx)}")
        last = self.last_correction
        box = d.correction_reason
        box.blockSignals(True)
        box.clear()
        for key, text in CORRECTION_WHY[last["delta"]]:
            box.addItem(text, key)
        box.setCurrentIndex(max(box.findData(last.get("reason")), 0))
        box.blockSignals(False)

    def correction_reason_chosen(self, _index=None):
        last = self.last_correction
        if last is None:
            return
        reason = self.dashboard.correction_reason.currentData()
        self.correction_memory[last["delta"]] = reason
        try:
            match_history.set_correction_reason(self._history_folder(), last["id"], reason)
        except OSError as error:
            show_error(self, f"The reason could not be saved ({error}).")
            return
        self.refresh_corrections()

    def update_correction_buttons(self):
        d = self.dashboard
        ready = self.mode != "stopping"
        room = self.counts[1] > self.counts[0]
        d.plus.setEnabled(ready)
        d.minus.setEnabled(ready and room)
        d.minus.setToolTip("Take one chest off APPROX" if room else "APPROX cannot go below CERTAIN. If a CERTAIN chest was wrong, use Edit counts.")

    def mark_available(self):
        return self.mode == "counting" and self.recording is not None

    def mark_moment(self):
        """Mark button / Ctrl+Alt+M: keep the video around this moment. Only while a recording is running - without one
        there is no video to keep, and the app says so instead of pretending."""
        if self.mark_available():
            return self.worker.send("mark")
        why = ("start counting first" if self.mode != "counting" else
               "diagnostic recording is off - choose 'Only around my marks' on the Dashboard (it keeps the 30 s before "
               "each mark)")
        self.add_log({"type": "warn", "text": f"Mark not saved: {why}."})
        self.dashboard.rec_status.setText(f"Mark not saved: {why}.")
        self.dashboard.rec_status.setStyleSheet(f"color: {theme.WARN};")
        self._mark_flash.start(5000)
        return False

    def recording_changed(self):
        """The Diagnostic recording choice: saved for next time and, while counting, applied at once (counts continue)."""
        mode = self.dashboard.rec_mode.currentData()
        try:
            C.update_config_file(config_file(), "capture", {"mode": mode})
        except (C.UserError, OSError) as error:
            show_error(self, f"Could not save the recording choice: {error}")
        if self.worker.running():
            self.worker.send(f"capture {mode}")
        self.update_recording_ui()

    def update_recording_ui(self):
        d = self.dashboard
        d.mark.setEnabled(self.mark_available())
        d.mark.setToolTip("Keep the video around this moment (the counter missed a chest or got one wrong). Also "
                          "Ctrl+Alt+M while you play." if self.mark_available() else
                          "Available while counting with a diagnostic recording running: choose a recording mode on the "
                          "left ('Only around my marks' is the smallest).")
        if self._mark_flash.isActive():
            return
        d.rec_status.setStyleSheet("")
        mode = d.rec_mode.currentData()
        if self.recording is not None:
            d.rec_status.setText(f"\u25cf  Recording {RECORDING_TEXT.get(self.recording.get('mode'), '')}   \u00b7   "
                                 f"{self.marks_this_session} mark(s) this session   \u00b7   press Ctrl+Alt+M right after a "
                                 "missed chest")
            d.rec_status.setStyleSheet(f"color: {theme.REJECT};")
        elif self.mode == "counting" and mode != "off":
            d.rec_status.setText("Starting the recording...")
        elif self.mode == "counting":
            d.rec_status.setText("Not recording. Marks need a recording: 'Only around my marks' keeps just the 30 seconds "
                                 "before and 10 after each mark.")
        elif mode != "off":
            d.rec_status.setText(f"Starts with counting: keeps {RECORDING_TEXT[mode]} (captures folder).")
        else:
            d.rec_status.setText("Off. Turn it on to replay missed chests later; you can also do it while counting.")

    def register_hotkey(self):
        """Ctrl+Alt+M anywhere (also while Fortnite has the focus) = Mark moment."""
        try:
            ok = ctypes.windll.user32.RegisterHotKey(int(self.winId()), HOTKEY_ID, 0x0002 | 0x0001 | 0x4000, ord("M"))
        except Exception:
            ok = False
        self.hotkey = bool(ok)
        if not ok:
            self.dashboard.mark.setToolTip("The counter missed a chest or got one wrong? Mark it. (Ctrl+Alt+M is used by "
                                           "another program, so only this button works.)")

    def nativeEvent(self, event_type, message):
        try:
            if event_type == b"windows_generic_MSG" or event_type == "windows_generic_MSG":
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:                  # WM_HOTKEY
                    self.mark_moment()
                    return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    def showEvent(self, event):
        super().showEvent(event)
        if self.hotkey is None:
            self.register_hotkey()

    def analyse_video(self):
        if self.worker.running():
            return
        VideoDialog(self).exec()

    # ---- window layout
    def restore_layout(self):
        """Called once by main() before the window is shown: reopen where the user left it ([app] remember_window)."""
        self.window_file = window_file()
        cfg, _ = load_cfg()
        return cfg["app"]["remember_window"] and restore_window(self, self.window_file)

    def save_layout(self):
        """On closing: keep the size, position and maximised state for next time (only while the setting is on)."""
        if self.window_file is None or not self.isVisible():
            return False
        cfg, _ = load_cfg()
        return cfg["app"]["remember_window"] and save_window(self, self.window_file)

    # ---- closing
    def closeEvent(self, event):
        if self.worker.running():
            if not self.quit_when_stopped:
                if not ask(self, "Stop counting?", "The counter is running. Stop counting and close the app?\n\n"
                                                   "Your counts are saved and kept for next time.", "Stop and close"):
                    event.ignore()
                    return
                self.quit_when_stopped = True
                self.save_layout()               # before hiding: a hidden window has no position to save
                self.stop_counting()
                self.hide()
            event.ignore()                       # closes for real when the worker has finished (see handle 'exit')
            return
        self.save_layout()
        if self.update_dialog is not None:
            self.update_dialog.hide()
        if self.preview_reader is not None:
            self.preview_reader.close()
        self.obs_link.stop(timeout=0.5)
        super().closeEvent(event)
        QApplication.quit()


# ==================================================================
# start-up
# ==================================================================

def _crash_hook(window_ref):
    def hook(kind, value, tb):
        where = None
        try:
            folder = paths.APP_DIR / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            where = folder / f"crash_app_{datetime.now():%Y%m%d_%H%M%S}.txt"
            where.write_text(f"{APP_NAME} v{__version__} (app window)\n\n" + "".join(traceback.format_exception(kind, value, tb)),
                             encoding="utf-8")
        except OSError:
            pass
        try:
            QMessageBox.critical(window_ref(), APP_NAME,
                                 f"Something unexpected went wrong in the app window ({kind.__name__}: {value}).\n\n"
                                 "Counting is not affected: it runs separately and saves after every chest."
                                 + (f"\n\nDetails were saved to:\n{where}" if where else ""))
        except Exception:
            pass
    return hook


def _single_instance():
    """One app window per program folder. -> a handle to keep, or None if another window is already open."""
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k.CreateMutexW(None, False, paths.app_mutex_name())
        if handle and ctypes.get_last_error() == 183:
            return None
        return handle or True
    except Exception:
        return True


def _palette():
    palette = QPalette()
    for role, color in ((QPalette.Window, theme.BG), (QPalette.WindowText, theme.TEXT), (QPalette.Base, theme.SURFACE_2),
                        (QPalette.AlternateBase, theme.SURFACE), (QPalette.Text, theme.TEXT), (QPalette.Button, theme.SURFACE_2),
                        (QPalette.ButtonText, theme.TEXT), (QPalette.Highlight, theme.ACCENT), (QPalette.HighlightedText, "#ffffff"),
                        (QPalette.ToolTipBase, theme.SURFACE_3), (QPalette.ToolTipText, theme.TEXT),
                        (QPalette.PlaceholderText, theme.DIM), (QPalette.Link, theme.ACCENT)):
        palette.setColor(role, QColor(color))
    return palette


def self_test(app, report_path):
    """`--self-test REPORT.json`: build the real window without ever showing it, wait for the device scan, save a
    screenshot next to the report and exit. Proves the whole start chain (launcher -> pythonw -> Qt -> window) works on a
    PC without anything appearing on screen."""
    report_path = Path(report_path)
    result = {"ok": False, "version": __version__, "python": sys.version.split()[0], "executable": sys.executable,
              "app_dir": str(paths.APP_DIR), "packaged": paths.PACKAGED, "update_health": True}
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        result.update(pyside=PySide6.__version__, qt=qVersion(), platform=app.platformName())
        window = MainWindow()
        result["class_icon"] = set_class_icon(window)
        window.setAttribute(Qt.WA_DontShowOnScreen, True)
        window.show()
        deadline = time.monotonic() + 20
        while window.dashboard.source.count() == 0 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
        for _ in range(10):
            app.processEvents()
            time.sleep(0.02)
        result["sources"] = [window.dashboard.source.itemText(i) for i in range(window.dashboard.source.count())]
        result["screenshot"] = str(report_path.with_suffix(".png"))
        result["ok"] = bool(window.grab().save(result["screenshot"])) and bool(result["sources"]) and result["class_icon"]
        window.preview_reader and window.preview_reader.close()
    except Exception:
        result["error"] = traceback.format_exc()
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


def main(argv=None):
    paths.setup_environment()                     # run from the program folder; bundled ffmpeg first
    paths.HIDE_CHILD_CONSOLES = True
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)    # own taskbar icon/group
    except Exception:
        pass
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(theme.STYLE)
    if len(args) == 2 and args[0] == "--self-test":
        return self_test(app, args[1])
    lock = _single_instance()
    if lock is None:
        QMessageBox.information(None, APP_NAME, f"{APP_NAME} is already open.\n\nLook for it in the taskbar.")
        return 0
    window = MainWindow()
    set_class_icon(window)
    sys.excepthook = _crash_hook(lambda: window)
    window.restore_layout()
    window.show()
    installing = len(args) == 3 and args[0] == "--update-health"
    if installing:                                             # started by the updater: report only once the app is really up
        from fortnite_chest_counter.update import health
        QTimer.singleShot(UPDATE_HEALTH_DELAY_MS, lambda: health.write_report(args[1], args[2]))
    window.after_start(installing)
    return app.exec()
