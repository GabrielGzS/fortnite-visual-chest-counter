"""Tonal surfaces and expressive shapes for the Windows counter."""

import ctypes
import sys
from pathlib import Path

ASSET_DIR = Path(__file__).with_name("assets").as_posix()


def animations_enabled():
    enabled = ctypes.c_int(1)
    if sys.platform == "win32":
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
    return bool(enabled.value)


BG = "#1c1814"
SIDEBAR = "#211c17"
SURFACE = "#2b241e"
SURFACE_2 = "#352c24"
SURFACE_3 = "#43372c"
BORDER = "#534438"
TEXT = "#f6eee5"
MUTED = "#c8b7a6"
DIM = "#ac9784"
ACCENT = "#ffd2a1"
ACCENT_HOVER = "#ffe1bd"
CERTAIN = "#62ddb0"
APPROX = "#f0bd70"
REJECT = "#f87171"
DANGER = "#ef4444"
WARN = "#c084fc"
INFO = "#67c7e8"
STAGE = "#34251c"
STAGE_MOTIF = "#5b3a29"

LOG_COLORS = {"certain": CERTAIN, "approx": APPROX, "rejected": REJECT, "generic": DIM, "info": INFO, "warn": WARN,
              "error": REJECT, "line": MUTED, "status": DIM, "detail": DIM}

STYLE = f"""
* {{ font-family: "Segoe UI", "Segoe UI Variable Text", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog, #page {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}

#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {SURFACE_2}; }}
#brandName {{ font-family: "Bahnschrift SemiBold Condensed", "Segoe UI"; font-size: 17pt; }}
#menuToggle {{ padding: 0; font-size: 16pt; border-radius: 18px; }}
#brandSub {{ color: {MUTED}; font-size: 8.5pt; }}
#nav {{ background: transparent; border: none; outline: none; }}
#nav::item {{ padding: 10px 14px; margin: 2px 4px; border-radius: 18px; color: {MUTED}; }}
#nav::item:hover {{ background: {SURFACE}; color: {TEXT}; }}
#nav::item:selected {{ background: {SURFACE_3}; color: {ACCENT}; font-weight: 600; }}
#version {{ color: {DIM}; font-size: 8.5pt; }}

#pageTitle {{ font-family: "Bahnschrift SemiBold Condensed", "Segoe UI"; font-size: 25pt; }}
#pageSub {{ color: {MUTED}; }}
#card {{ background: {SURFACE}; border: 1px solid transparent; border-radius: 18px; }}
#cardTitle {{ font-family: "Bahnschrift SemiBold Condensed", "Segoe UI"; font-size: 15pt; }}
#hint, .hint {{ color: {MUTED}; font-size: 9pt; }}
#metrics {{ color: {MUTED}; font-size: 9pt; }}

#chestStage {{ background: {STAGE}; border: 1px solid transparent; border-radius: 28px; }}
#stageTotal {{ color: {ACCENT}; font-family: "Bahnschrift SemiBold Condensed", "Segoe UI"; font-size: 53pt; }}
#stageOdds {{ color: {ACCENT_HOVER}; font-family: "Bahnschrift SemiBold Condensed", "Segoe UI"; font-size: 22pt; }}
#recentOpenings {{ background: transparent; border: none; min-height: 120px; }}
#recentOpenings::item {{ padding: 6px 2px; }}

#countCard {{ background: {SURFACE_2}; border: 1px solid transparent; border-radius: 16px; }}
#countLabel {{ color: {MUTED}; font-size: 9pt; font-weight: 600; letter-spacing: 1px; }}
#countValue {{ font-size: 33pt; font-weight: 700; }}
#countSub {{ color: {MUTED}; font-size: 9pt; }}

#pill {{ border-radius: 11px; padding: 3px 12px; font-size: 9pt; font-weight: 600; }}
#banner {{ background: #3a1d22; border: 1px solid #6b2a33; border-radius: 8px; }}
#bannerText {{ color: #ffd7dc; }}
#notice {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; }}
#overlayBox {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 7px; }}
#screenOverlayCaption {{ color: {TEXT}; font-size: 12pt; font-weight: 600; }}

QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 12px; padding: 7px 14px; }}
QPushButton:hover {{ background: {SURFACE_3}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {DIM}; background: {SURFACE}; }}
QPushButton#primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: {BG}; font-weight: 600; border-radius: 18px; padding: 9px 22px; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: {SURFACE_3}; border-color: {SURFACE_3}; color: {MUTED}; }}
QPushButton#danger {{ background: {DANGER}; border: 1px solid {DANGER}; color: white; font-weight: 600; border-radius: 18px; padding: 9px 22px; }}
QPushButton#danger:hover {{ background: #f05a5a; }}
QPushButton#toggle {{ background: transparent; border: 1px solid {BORDER}; border-radius: 14px; padding: 5px 14px; color: {MUTED}; }}
QPushButton#toggle:checked {{ background: {SURFACE_2}; color: {TEXT}; border-color: {ACCENT}; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 0; }}
QPushButton#link:hover {{ color: {ACCENT_HOVER}; text-decoration: underline; }}

QComboBox, QLineEdit, QSpinBox {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 12px; padding: 6px 10px;
                                  selection-background-color: {SURFACE_3}; }}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{ border-color: {DIM}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right;
                        width: 25px; border: none; border-radius: 12px; }}
QComboBox::down-arrow {{ image: url("{ASSET_DIR}/dropdown_arrow.png"); width: 12px; height: 8px; }}
QComboBox:disabled {{ color: {DIM}; }}
QComboBox::down-arrow:disabled {{ image: url("{ASSET_DIR}/dropdown_arrow_disabled.png"); }}
QComboBox QAbstractItemView, QMenu {{ background: {SURFACE}; border: 1px solid {BORDER};
                                      outline: none; border-radius: 12px; padding: 4px; selection-background-color: {SURFACE_3};
                                      selection-color: {TEXT}; }}
QComboBox QAbstractItemView::item, QMenu::item {{ padding: 6px 10px; }}
QMenu::item:selected {{ background: {SURFACE_3}; color: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 7px; }}
QLineEdit:read-only {{ color: {MUTED}; }}

QCheckBox, QRadioButton {{ spacing: 8px; padding: 3px 0; }}
QCheckBox:focus, QRadioButton:focus {{ color: {ACCENT}; }}
QRadioButton::indicator {{ width: 12px; height: 12px; border: 1px solid {DIM};
                            border-radius: 7px; background: {BG}; }}
QRadioButton::indicator:checked {{ border: 4px solid {ACCENT}; width: 6px; height: 6px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}

QPlainTextEdit#log, QPlainTextEdit#report {{ background: #1c1814; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px;
                                            font-family: "Cascadia Mono", "Consolas", monospace; font-size: 9pt; }}
#previewBox {{ background: #000000; border: 1px solid {BORDER}; border-radius: 8px; color: {DIM}; }}

QProgressBar {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px; height: 12px; text-align: center;
                color: {TEXT}; font-size: 8.5pt; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 30px; }}
QSplitter::handle {{ background: transparent; }}
QMessageBox QLabel {{ min-width: 340px; }}
"""


def rgba(color, alpha):
    """'#rrggbb' + opacity 0..1 -> 'rgba(r, g, b, a)'. (Qt reads 8-digit hex as #AARRGGBB, so never append alpha.)"""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {round(alpha * 255)})"


def pill_style(color):
    """Status pill: tinted background, coloured text."""
    return f"background: {rgba(color, 0.13)}; color: {color}; border: 1px solid {rgba(color, 0.35)};"
