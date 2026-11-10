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
DANGER = "#ffb4ab"
DANGER_INK = "#690005"
WARN = "#c084fc"
INFO = "#67c7e8"
STAGE = "#34251c"
STAGE_MOTIF = "#5b3a29"

LOG_COLORS = {"certain": CERTAIN, "approx": APPROX, "rejected": REJECT, "generic": DIM, "info": INFO, "warn": WARN,
              "error": REJECT, "line": MUTED, "status": DIM, "detail": DIM}

STYLE = f"""
* {{ font-family: "Google Sans", "Segoe UI", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog, #page {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}

#navigationRail {{ background: {SURFACE}; }}
QPushButton#navDestination {{ background: transparent; border: 1px solid transparent; border-radius: 16px; padding: 0; }}
QPushButton#navDestination:hover {{ background: {SURFACE_2}; }}
QPushButton#navDestination:focus {{ border-color: {ACCENT}; }}
#navCaption {{ font-size: 12px; font-weight: 500; }}

#pageTitle {{ font-size: 32px; font-weight: 500; }}
#pageSub {{ color: {MUTED}; }}
#card {{ background: {SURFACE}; border: 1px solid transparent; border-radius: 18px; }}
#cardTitle {{ font-size: 16px; font-weight: 500; }}
#hint, .hint {{ color: {MUTED}; font-size: 9pt; }}
#metrics {{ color: {MUTED}; font-size: 9pt; }}

#chestStage {{ background: {STAGE}; border: 1px solid transparent; border-radius: 28px; }}
#stageTotal {{ color: {ACCENT}; font-size: 46pt; }}
#stageOdds {{ color: {ACCENT_HOVER}; font-size: 22pt; }}
#recentOpenings {{ background: transparent; border: none; min-height: 120px; }}
#recentOpenings::item {{ padding: 6px 2px; }}

#countCard {{ background: {SURFACE_2}; border: 1px solid transparent; border-radius: 16px; }}
#countLabel {{ color: {MUTED}; font-size: 9pt; font-weight: 500; }}
#countValue {{ font-size: 33pt; font-weight: 700; }}
#countSub {{ color: {MUTED}; font-size: 9pt; }}

#pill {{ border-radius: 11px; padding: 3px 12px; font-size: 9pt; font-weight: 500; }}
#sourceChip {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 4px;
                padding: 3px 9px; color: {MUTED}; font-size: 9pt; }}
#sourceChip[groupPosition="first"] {{ border-top-left-radius: 12px; border-bottom-left-radius: 12px;
                                    border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
#sourceChip[groupPosition="last"] {{ border-top-left-radius: 4px; border-bottom-left-radius: 4px;
                                   border-top-right-radius: 12px; border-bottom-right-radius: 12px; }}
#banner {{ background: #3a1d22; border: 1px solid #6b2a33; border-radius: 8px; }}
#bannerText {{ color: #ffd7dc; }}
#notice {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; }}
#overlayBox {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 14px; }}
#screenOverlayCaption {{ color: {TEXT}; font-size: 12pt; font-weight: 500; }}

QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 12px; padding: 7px 14px; }}
QPushButton#overlayUndo {{ padding: 9px 14px; }}
QPushButton[compactAction="true"] {{ padding: 7px 8px; }}
QPushButton:hover {{ background: {SURFACE_3}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {DIM}; background: {SURFACE}; }}
QPushButton#primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: {BG}; font-weight: 500; border-radius: 18px; padding: 9px 22px; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: {SURFACE_3}; border-color: {SURFACE_3}; color: {MUTED}; }}
QPushButton#danger {{ background: {DANGER}; border: 1px solid {DANGER}; color: {DANGER_INK}; font-weight: 500; border-radius: 18px; padding: 9px 22px; }}
QPushButton#danger:hover {{ background: #ffc8c1; }}
QPushButton#toggle {{ background: transparent; border: 1px solid {BORDER}; border-radius: 14px; padding: 5px 14px; color: {MUTED}; }}
QPushButton#toggle:checked {{ background: {SURFACE_2}; color: {TEXT}; border-color: {ACCENT}; }}
QPushButton[groupPosition="middle"], QPushButton#toggle[groupPosition="middle"] {{ border-radius: 4px; }}
QPushButton[groupPosition="first"], QPushButton#overlayUndo[groupPosition="first"], QPushButton#primary[groupPosition="first"],
QPushButton#danger[groupPosition="first"] {{
    border-top-left-radius: 16px; border-bottom-left-radius: 16px;
    border-top-right-radius: 4px; border-bottom-right-radius: 4px;
}}
QPushButton[groupPosition="last"], QPushButton#primary[groupPosition="last"],
QPushButton#danger[groupPosition="last"] {{
    border-top-left-radius: 4px; border-bottom-left-radius: 4px;
    border-top-right-radius: 16px; border-bottom-right-radius: 16px;
}}
QPushButton#toggle[groupPosition="first"] {{
    border-top-left-radius: 12px; border-bottom-left-radius: 12px;
    border-top-right-radius: 4px; border-bottom-right-radius: 4px;
}}
QPushButton#toggle[groupPosition="last"] {{
    border-top-left-radius: 4px; border-bottom-left-radius: 4px;
    border-top-right-radius: 12px; border-bottom-right-radius: 12px;
}}
QPushButton#toggle[groupPosition]:checked {{ background: {SURFACE_3}; border-color: {ACCENT}; border-radius: 12px; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 0; }}
QPushButton#link:hover {{ color: {ACCENT_HOVER}; text-decoration: underline; }}

QComboBox, QLineEdit, QSpinBox {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 12px; padding: 6px 10px;
                                  selection-background-color: {SURFACE_3}; }}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{ border-color: {DIM}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox {{ combobox-popup: 0; }}
QComboBox[groupPosition="first"] {{ border-top-left-radius: 16px; border-bottom-left-radius: 16px;
                                   border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
QComboBox[groupPosition="last"] {{ border-top-left-radius: 4px; border-bottom-left-radius: 4px;
                                  border-top-right-radius: 16px; border-bottom-right-radius: 16px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right;
                        width: 25px; border: none; border-radius: 12px; }}
QComboBox::down-arrow {{ image: url("{ASSET_DIR}/dropdown_arrow.png"); width: 12px; height: 8px; }}
QComboBox:disabled {{ color: {DIM}; }}
QComboBox::down-arrow:disabled {{ image: url("{ASSET_DIR}/dropdown_arrow_disabled.png"); }}
#comboPopup {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 16px; }}
QComboBox QAbstractItemView {{ background: transparent; border: none; outline: none;
                               selection-background-color: {SURFACE_3}; selection-color: {TEXT}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER};
                                      outline: none; border-radius: 12px; padding: 4px; selection-background-color: {SURFACE_3};
                                      selection-color: {TEXT}; }}
QComboBox QAbstractItemView::item, QMenu::item {{ padding: 6px 10px; }}
QMenu::item:selected {{ background: {SURFACE_3}; color: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 7px; }}
QLineEdit:read-only {{ color: {MUTED}; }}

QCheckBox, QRadioButton {{ spacing: 10px; padding: 3px 0; }}
QCheckBox:focus, QRadioButton:focus {{ color: {ACCENT}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 2px solid {DIM};
                        border-radius: 2px; background: {BG}; }}
QCheckBox::indicator:checked {{ border-color: {ACCENT}; background: {ACCENT};
                                image: url("{ASSET_DIR}/check_mark.png"); }}
QCheckBox::indicator:checked:disabled {{ border-color: {DIM}; background: {DIM}; }}
QCheckBox::indicator:unchecked:disabled, QRadioButton::indicator:unchecked:disabled {{ border-color: {BORDER}; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 2px solid {DIM};
                            border-radius: 10px; background: {BG}; }}
QRadioButton::indicator:checked {{ border-color: {ACCENT}; image: url("{ASSET_DIR}/radio_dot.png"); }}
QRadioButton::indicator:checked:disabled {{ border-color: {DIM}; image: url("{ASSET_DIR}/radio_dot_disabled.png"); }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}

QSpinBox {{ padding-left: 23px; padding-right: 23px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 22px; height: 15px;
                                            border: none; background: transparent; }}
QSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 12px; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 12px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: transparent; }}
QSpinBox::up-arrow {{ image: url("{ASSET_DIR}/stepper_up.png"); width: 10px; height: 6px; }}
QSpinBox::down-arrow {{ image: url("{ASSET_DIR}/dropdown_arrow.png"); width: 10px; height: 6px; }}
QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled {{ image: none; }}

#matchTable {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 12px; outline: none;
                selection-background-color: {SURFACE_3}; selection-color: {TEXT}; }}
#matchTable QHeaderView {{ background: transparent; }}
#matchTable QHeaderView::section {{ background: {SURFACE_2}; border: none; padding: 6px 8px; color: {MUTED}; }}
#matchTable QHeaderView::section:first {{ border-top-left-radius: 10px; }}
#matchTable QHeaderView::section:last {{ border-top-right-radius: 10px; }}
#matchTable::item {{ padding: 5px 8px; }}
#matchTable:focus {{ border-color: {ACCENT}; }}

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
#promptDialog {{ background: transparent; }}
#promptSurface {{ background: {SURFACE_2}; border-radius: 28px; }}
#dialogHeading {{ font-size: 24px; font-weight: 500; }}
#dialogBody {{ color: {MUTED}; font-size: 14px; }}

"""


def rgba(color, alpha):
    """'#rrggbb' + opacity 0..1 -> 'rgba(r, g, b, a)'. (Qt reads 8-digit hex as #AARRGGBB, so never append alpha.)"""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {round(alpha * 255)})"


def pill_style(color):
    """Status pill: tinted background, coloured text."""
    return f"background: {rgba(color, 0.13)}; color: {color}; border: 1px solid {rgba(color, 0.35)};"
