"""Flat theme engine ported from Qt UI Lab into ScreenText OCR.

The original design system (tokens, QSS renderer, painted checkmarks) is kept
intact and extended with ScreenText-OCR-specific selectors.  Keeping one sheet for
the whole application means the accent, radius and typeface recolour cards,
inputs, tabs, docks and the activity console at the same time.

Design rules:
  * one global diagonal gradient on the shell, with translucent panels layered
    on top of it instead of opaque blocks;
  * a real type scale (display / title / body / caption / mono) driven by
    FONT_STACK so a single family change re-renders the whole sheet;
  * translucency only through rgba(), never through window opacity, so the
    global gradient stays visible through docks, toolbars and cards.
  * every interactive element carries hover / pressed / focus / checked /
    disabled states, and every colour resolves from a token so that changing
    the accent recolours selection, hover text, sliders and scrollbars too.

BASE_QSS holds the shell + surfaces, CONTROL_QSS the interactive controls.
tokens_to_qss() re-derives every accent/font/radius rule from a token dict so
the inspector and the live QSS editor stay in sync.
"""

from __future__ import annotations

import atexit
import json
import tempfile
from pathlib import Path

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen

try:  # Qt >= 5.13 has an antialiasing flag on QImage; older builds do not.
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import QSize
except ImportError:  # pragma: no cover - PyQt5 always ships these
    QImage = QSize = None

# Typography: one stack for UI text, one for numerics, plus a modular scale.
FONT_STACK = '"Segoe UI Variable Display", "Segoe UI", "Inter", "SF Pro Text", sans-serif'
MONO_STACK = '"Cascadia Mono", "JetBrains Mono", Consolas, "Courier New", monospace'

FONT_SIZE_BODY = 10     # pt - base size for every control
FONT_SIZE_CAPTION = 9   # pt - hints, badges, secondary metadata
FONT_SIZE_TITLE = 11    # pt - group captions, dock titles
FONT_SIZE_MONO = 9      # pt - log console and numeric readouts

# Layered glass tokens: rgba over the global navy gradient.  The ramp is
# intentionally blue (not neutral graphite) so every surface belongs to the
# same navy family as the shell; the accent is the only saturated element.
BG_SHELL_0 = "#142440"
BG_SHELL_1 = "#0d1a31"
BG_SHELL_2 = "#0a1224"
PANEL = "rgba(86, 130, 205, 0.10)"
PANEL_HOVER = "rgba(61, 139, 253, 0.16)"
PANEL_ACTIVE = "rgba(11, 110, 232, 0.24)"
CARD = "rgba(25, 45, 76, 0.60)"
CARD_FLAT = "rgba(20, 35, 59, 0.62)"
CARD_SHADOW = "rgba(0, 0, 0, 0.42)"
WELL = "rgba(16, 33, 58, 0.86)"
WELL_DEEP = "rgba(20, 40, 68, 0.90)"
HAIRLINE = "rgba(118, 168, 242, 0.14)"
HAIRLINE_STRONG = "rgba(140, 190, 255, 0.24)"

# Ambient surfaces. Shell stops are also reused by MDI/wizard backgrounds so
# detached surfaces never look flat grey next to the main gradient.
SHELL_TOP = "#142440"
SHELL_BLOOM = "#102443"
SHELL_MID = "#0d1a31"
SHELL_LOW = "#091326"
SHELL_BOTTOM = "#0a1224"

TOOLBAR_TOP = "rgba(22, 39, 68, 0.42)"
TOOLBAR_MID = "rgba(13, 26, 49, 0.36)"
TOOLBAR_BOTTOM = "rgba(8, 16, 32, 0.32)"
TOOLBAR_FILL = "rgba(7, 14, 29, 0.46)"
HEADER_FILL = "rgba(18, 31, 54, 0.56)"
ROW_ALT = "rgba(74, 143, 255, 0.08)"
POPUP = "rgba(20, 35, 58, 0.995)"
MENU_TOP = "rgba(30, 43, 64, 0.99)"
MENU_BOTTOM = "rgba(12, 19, 30, 0.995)"
MENU_HOVER_TOP = "rgba(40, 102, 192, 0.78)"
MENU_HOVER_BOTTOM = "rgba(18, 58, 122, 0.90)"

# Wells / tracks / rails stay blue-neutral so the accent reads as the only
# saturated thing on screen.  Scrollbar thumbs join the chrome as soft glass:
# translucent azure instead of a solid slab, so the page scrollbar never turns
# into the brightest bar next to the panel seam.
TRACK = "rgba(136, 170, 224, 0.18)"
TRACK_HOVER = "rgba(155, 199, 255, 0.28)"
RAIL = "rgba(18, 31, 52, 0.82)"
SCROLL_HANDLE = "rgba(104, 152, 214, 0.42)"
SCROLL_HANDLE_HOVER = "rgba(132, 178, 236, 0.60)"
SCROLL_HANDLE_PRESSED = "rgba(150, 192, 245, 0.72)"
PRESSED_FILL = "rgba(0, 61, 139, 0.55)"
DISABLED_FILL = "rgba(255, 255, 255, 0.04)"
DISABLED_FILL_STRONG = "rgba(255, 255, 255, 0.10)"
READONLY_FILL = "rgba(255, 255, 255, 0.03)"

# Action hierarchy: primary = azure, secondary = deep steel blue, dangerous =
# flat wine.  Each surface is one flat fill; state changes only its lightness.
STATE_HOVER = "rgba(46, 110, 200, 0.30)"
STATE_PRESSED = "rgba(0, 61, 139, 0.92)"
STATE_SELECTED = "rgba(17, 76, 146, 0.92)"
STATE_SELECTED_HOVER = "rgba(24, 103, 184, 0.96)"
BUTTON_TOP = "#173a5c"
BUTTON_HOVER_TOP = "#24527f"
BUTTON_PRESSED = "#0f2b49"
BUTTON_TEXT = "#f2f6ff"
BUTTON_TOOL = "#3f4b5c"
BUTTON_TOOL_HOVER = "#4b596b"
ACCENT_BUTTON = "#095ec5"
ACCENT_BUTTON_HOVER = "#0a68dc"
DANGER_BUTTON_FILL = "#b03427"
DANGER_BUTTON_HOVER = "#c13d31"
DANGER_BUTTON_PRESSED = "#8e2a20"
DANGER_BUTTON_TEXT = "#fff7f4"

# Light palette mirror: the same token names, re-derived from a bright shell so
# ``render_qss(tokens)`` can produce a full light sheet without a second QSS.
# The reading is "white tiles on a pale azure sky": opaque cards, pale blue
# shell, the same azure accent and the same steel-blue secondary buttons.
LIGHT_TOKENS = {
    "accent": "#0f5cc7",
    "accent_hover": "#0a4fa8",
    "text": "#12233d",
    "text_muted": "rgba(18, 35, 61, 0.64)",
    "surface": "#eef2f9",
    "surface_alt": "#e3eaf5",
    "border": "rgba(24, 56, 104, 0.10)",
    "danger": "#b03427",
    "success": "#2f7a52",
    "radius": 10,
    "font_family": "Segoe UI Variable Display",
    "font_size": 9,
    "mono_family": "Cascadia Mono",
    "mark": "#ffffff",
}

# Overrides applied on top of the dark sheet when rendering the light variant.
LIGHT_OVERRIDES = {
    "TEXT": "#12233d",
    "TEXT_SOFT": "rgba(18, 35, 61, 0.92)",
    "TEXT_MUTED": "rgba(18, 35, 61, 0.64)",
    "TEXT_DISABLED": "rgba(18, 35, 61, 0.36)",
    "ACCENT_TEXT": "#0a4b8f",
    "MONO_TEXT": "#085e8a",
    "SELECTION_INK": "#12233d",
    "PANEL": "rgba(12, 52, 110, 0.06)",
    "PANEL_HOVER": "rgba(11, 110, 232, 0.10)",
    "PANEL_ACTIVE": "rgba(11, 110, 232, 0.14)",
    "CARD": "rgba(255, 255, 255, 0.92)",
    "CARD_FLAT": "rgba(255, 255, 255, 0.96)",
    "CARD_SHADOW": "rgba(20, 45, 85, 0.26)",
    "WELL": "rgba(228, 237, 250, 0.96)",
    "WELL_DEEP": "rgba(220, 231, 247, 0.98)",
    "HAIRLINE": "rgba(24, 56, 104, 0.14)",
    "HAIRLINE_STRONG": "rgba(24, 56, 104, 0.24)",
    "TOOLBAR_TOP": "rgba(255, 255, 255, 0.72)",
    "TOOLBAR_MID": "rgba(240, 245, 252, 0.62)",
    "TOOLBAR_BOTTOM": "rgba(228, 237, 249, 0.58)",
    "TOOLBAR_FILL": "rgba(255, 255, 255, 0.55)",
    "HEADER_FILL": "rgba(232, 240, 251, 0.90)",
    "ROW_ALT": "rgba(11, 110, 232, 0.05)",
    "POPUP": "rgba(250, 251, 252, 0.99)",
    "MENU_TOP": "rgba(255, 255, 255, 0.995)",
    "MENU_BOTTOM": "rgba(238, 244, 252, 0.995)",
    "MENU_HOVER_TOP": "rgba(215, 232, 255, 0.95)",
    "MENU_HOVER_BOTTOM": "rgba(188, 216, 252, 0.98)",
    "TRACK": "rgba(24, 56, 104, 0.14)",
    "TRACK_HOVER": "rgba(24, 56, 104, 0.22)",
    "RAIL": "rgba(24, 56, 104, 0.06)",
    "SCROLL_HANDLE": "rgba(74, 134, 216, 0.38)",
    "SCROLL_HANDLE_HOVER": "rgba(47, 111, 199, 0.56)",
    "SCROLL_HANDLE_PRESSED": "rgba(31, 95, 184, 0.70)",
    "PRESSED_FILL": "rgba(11, 110, 232, 0.20)",
    "DISABLED_FILL": "rgba(24, 56, 104, 0.05)",
    "DISABLED_FILL_STRONG": "rgba(24, 56, 104, 0.12)",
    "READONLY_FILL": "rgba(24, 56, 104, 0.03)",
    "STATE_HOVER": "rgba(11, 110, 232, 0.10)",
    "STATE_PRESSED": "rgba(11, 110, 232, 0.24)",
    "STATE_SELECTED": "rgba(11, 110, 232, 0.16)",
    "STATE_SELECTED_HOVER": "rgba(11, 110, 232, 0.24)",
    "BUTTON_TOP": "#dbe5f4",
    "BUTTON_HOVER_TOP": "#cbd9ee",
    "BUTTON_PRESSED": "#b9cbe6",
    "BUTTON_TEXT": "#12233d",
    "BUTTON_TOOL": "#e6ecf6",
    "BUTTON_TOOL_HOVER": "#d8e2f1",
    "ACCENT_BUTTON": "#0f5cc7",
    "ACCENT_BUTTON_HOVER": "#0a4fa8",
    "DANGER_BUTTON_FILL": "#b03427",
    "DANGER_BUTTON_HOVER": "#c13d31",
    "DANGER_BUTTON_PRESSED": "#8e2a20",
    "DANGER_BUTTON_TEXT": "#fff7f4",
    "SHELL_TOP": "#f4f7fc",
    "SHELL_BLOOM": "#eaf1fb",
    "SHELL_MID": "#e4ebf6",
    "SHELL_LOW": "#dde6f3",
    "SHELL_BOTTOM": "#d7e1f0",
    "SHELL_GLOW_1": "#ffffff",
    "SHELL_GLOW_2": "#f2f6fc",
    "SHELL_GLOW_3": "#e9f0fa",
    "SHELL_GLOW_4": "#dfe8f5",
    "SHELL_GLOW_5": "#d6e1f0",
    "SHELL_GLOW_6": "#cfdbec",
    "DANGER_TEXT": "#8e2a20",
    "WARN_TEXT": "#6f5518",
    "SUCCESS_TEXT": "#1f6b45",
    "ACCENT_GLASS_ALPHA": "0.40",
    "ACCENT_GLASS_ALPHA_BRIGHT": "0.58",
}


# Text ramp. Every label colour comes from here so the palette stays coherent.
TEXT = "#f2f6ff"
TEXT_SOFT = "rgba(239, 245, 255, 0.94)"
TEXT_MUTED = "rgba(190, 207, 237, 0.74)"
TEXT_DISABLED = "rgba(190, 207, 237, 0.38)"
ACCENT_TEXT = "#e6f0ff"
MONO_TEXT = "#73e9ff"
# Ink used on translucent selection washes (rows, menu highlight, radio dots).
# It is not the same as MARK: MARK sits on the solid azure fill and stays white,
# while a pale wash needs the ordinary body ink.
SELECTION_INK = "#f2f6ff"

DANGER = "#c0504a"
DANGER_WASH = "rgba(162, 56, 47, 0.28)"
DANGER_WASH_STRONG = "rgba(192, 80, 74, 0.45)"
DANGER_TEXT = "#f2b8b2"
WARN = "#b08b3e"
WARN_WASH = "rgba(176, 139, 62, 0.20)"
WARN_TEXT = "#efd39a"
SUCCESS_WASH = "rgba(63, 154, 90, 0.22)"
SUCCESS_TEXT = "#9fe3bb"

# Shell glow ramp used by the radial board gradient (flatuiux 2.1.0).  The
# centre sits in the lower-left corner, so the bloom reads as ambient light
# behind the cards instead of a flat fill.
SHELL_GLOW_1 = "#123f74"
SHELL_GLOW_2 = "#0d2d59"
SHELL_GLOW_3 = "#0c1f3f"
SHELL_GLOW_4 = "#091730"
SHELL_GLOW_5 = "#060f20"
SHELL_GLOW_6 = "#040a17"

BASE_QSS = """
*, QWidget {
    background: transparent;
    color: __TEXT__;
    font-family: __FONT__;
    font-size: __BODY__pt;
}

/* ==== global background: a wide diagonal gradient so every panel has depth.
       Child widgets stay transparent and layer translucent fills on top.
       The stops double as the ambient light the translucent panels sit in. ==== */
QWidget#MainWindow, QMainWindow, QDialog, QWizard, QWizardPage {
    background: __SHELL_BG__;
}
QWidget#centralHost { background: transparent; }
QLabel, QAbstractButton { background: transparent; }

QDockWidget { background: transparent; border: none; titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget > QWidget { background: transparent; }
QDockWidget::close-button, QDockWidget::float-button {
    background: transparent; border: none; icon-size: 0px; padding: 0; width: 0; height: 0;
}
QMainWindow::separator { background: transparent; width: 0; height: 0; }

QScrollArea, QAbstractScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStackedWidget { background: transparent; }
QFrame[role="sep"] { background: __HAIRLINE__; max-height: 1px; border: none; }
QFrame[frameShape="4"], QFrame[frameShape="5"] { background: __HAIRLINE__; border: none; max-height: 1px; }

QToolTip {
    background: __POPUP__; color: __TEXT__;
    border: 1px solid __HAIRLINE_STRONG__; border-radius: __RADIUS_PANEL__px;
    padding: 7px 11px; font-size: __CAPTION__pt;
}

/* ==== group boxes: frameless caption band over the shared background ==== */
QGroupBox {
    background: transparent;
    border: none;
    margin-top: 4px;
    padding: __GROUP_PAD__ 0 0 0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 0; padding: 0 0 6px 0;
    color: __ACCENT_HOVER__;
    font-weight: 600;
    font-size: __TITLE__pt;
    letter-spacing: 0.3px;
}
QGroupBox[role="card"] {
    background: __PANEL__;
    border-radius: __RADIUS__px;
    padding: __GROUP_PAD__ __GROUP_PAD__ 0 __GROUP_PAD__;
}
QGroupBox::indicator {
    width: __INDICATOR__px; height: __INDICATOR__px;
    border: 1px solid __HAIRLINE_STRONG__; border-radius: __INDICATOR_RADIUS__px;
    background: __WELL__; margin-right: 8px;
}
QGroupBox::indicator:hover { border: 1px solid __ACCENT__; background: __ACCENT_WASH__; }
QGroupBox::indicator:checked {
    image: url("__CHECK_IMG__");
    border: 1px solid __ACCENT__; background: __ACCENT__;
}
QGroupBox::indicator:disabled {
    border: 1px solid __HAIRLINE__; background: __DISABLED_FILL__;
}
QGroupBox[flat="true"] { margin-top: 0; }

QLabel { background: transparent; }
QLabel[role="hint"] {
    color: __TEXT_MUTED__;
    font-size: __CAPTION__pt;
}
/* The status bar keeps the only transient message surface after the inline
   plaque was removed, so it tints itself by the tone its caller passes. */
QLabel[role="hint"][tone="ok"]     { color: __SUCCESS_TEXT__; }
QLabel[role="hint"][tone="warn"]   { color: __WARN_TEXT__; }
QLabel[role="hint"][tone="danger"] { color: __DANGER_TEXT__; }
QLabel[role="section"] {
    color: __ACCENT_HOVER__;
    font-weight: 700; font-size: __CAPTION__pt;
    text-transform: uppercase; letter-spacing: 1.5px;
    padding: 2px 0;
}
QLabel[role="value"] {
    color: __ACCENT_TEXT__; font-family: __MONO__; font-size: __MONO_SIZE__pt;
    background: __CARD_FLAT__;
    border: 1px solid __HAIRLINE__;
    border-radius: __RADIUS_TILE__px; padding: 3px 10px;
}
QLabel[role="swatch"] {
    border: 1px solid __HAIRLINE__; border-radius: __RADIUS_TILE__px; background: __WELL__;
    min-width: 46px; min-height: 20px;
}
QLabel[role="badge"] {
    color: __MARK__; background: __ACCENT_BUTTON__;
    border-radius: __RADIUS_BADGE__px; padding: 1px 8px;
    font-size: __CAPTION__pt; font-weight: 700;
}
QLabel[role="chip"] {
    color: __TEXT__; background: __PANEL__;
    border: 1px solid __HAIRLINE__; border-radius: __RADIUS_CHIP__px; padding: 1px 9px;
    font-size: __CAPTION__pt; font-weight: 600;
}
QLabel[role="chip"][tone="ok"]       { background: __SUCCESS_WASH__; color: __SUCCESS_TEXT__; }
QLabel[role="chip"][tone="warn"]     { background: __WARN_WASH__;    color: __WARN_TEXT__; }
QLabel[role="chip"][tone="danger"]   { background: __DANGER_WASH__;  color: __DANGER_TEXT__; }
QLabel[role="chip"][tone="accent"]   { background: __ACCENT_WASH__;  color: __ACCENT_TEXT__; }
QLabel[role="title"] {
    color: __ACCENT_TEXT__; font-weight: 600; font-size: __TITLE__pt;
}
QLabel[role="mono"] { font-family: __MONO__; font-size: __MONO_SIZE__pt; color: __MONO_TEXT__; }
QLabel[role="toast"] {
    background: __PANEL_HOVER__;
    color: __TEXT__;
    border: none; border-left: 2px solid __ACCENT__;
    border-radius: __RADIUS__px;
    padding: 8px 12px;
    font-weight: 600;
}
QLabel[role="toast"][tone="ok"]     { border-left-color: __SUCCESS_TEXT__; background: __SUCCESS_WASH__; }
QLabel[role="toast"][tone="warn"]   { border-left-color: __WARN__;     background: __WARN_WASH__; }
QLabel[role="toast"][tone="danger"] { border-left-color: __DANGER__;   background: __DANGER_WASH__; }
QLabel[role="toast"][tone="accent"] { border-left-color: __ACCENT__;   background: __ACCENT_WASH__; }
QLabel:disabled { color: __TEXT_DISABLED__; }

/* ==== flat tabs: translucent chips, cyan underline when active ==== */
QTabWidget::pane { background: transparent; border: none; top: 0; }
QTabWidget::tab-bar { alignment: left; }
QTabWidget > QWidget { background: transparent; }
QTabBar { background: transparent; qproperty-drawBase: 0; font-weight: 600; }
/* The horizontal padding mirrors widgets.NavTabBar.H_PADDING (6 px) and the
   vertical one its V_PADDING (7 px); the margin mirrors its MARGIN_H (6 px).
   The bar measures its own tab rects from those constants, so a different
   inset here would clip the label inside a rect computed for a narrower one. */
QTabBar::tab {
    background: transparent;
    color: __TEXT__;
    padding: 7px 6px;
    margin-right: 6px;
    margin-bottom: 4px;
    border: 1px solid transparent;
    border-radius: __RADIUS_CHIP__px;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    color: __TEXT__;
    background: __BUTTON_TOOL__;
    border-color: transparent;
}
QTabBar::tab:selected {
    color: __MARK__;
    background: __ACCENT_BUTTON__;
    border-color: transparent;
}
QTabBar::tab:selected:hover {
    color: __MARK__;
    background: __ACCENT_BUTTON_HOVER__;
    border-color: transparent;
}
QTabBar::tab:disabled { color: __TEXT_DISABLED__; }
QTabBar::tab:selected:focus { border-color: transparent; }
QTabBar::close-button {
    subcontrol-position: right; background: transparent; border: none;
    image: none; width: 12px; height: 12px; margin-left: 6px;
}
QTabBar::close-button:hover { background: __DANGER_WASH__; border-radius: __RADIUS_SM__px; }
QTabBar QToolButton {
    background: transparent; border: none; color: __TEXT_MUTED__; padding: 2px 6px;
}
QTabBar QToolButton:hover { color: __ACCENT_HOVER__; background: __PANEL__; }

/* ==== toolbars and menus: translucent glass strips ==== */
QToolBar {
    background: __TOOLBAR_BG__;
    border: none; border-bottom: 1px solid __HAIRLINE__;
    spacing: 4px; padding: 6px 10px;
}
QToolBar::separator {
    background: __HAIRLINE_STRONG__; width: 1px; margin: 5px 8px;
}
QToolBar::handle { background: transparent; width: 6px; }
QToolButton {
    background: __BUTTON_TOOL__; border: 1px solid transparent;
    border-radius: __RADIUS_CONTROL__; padding: 7px 12px;
    color: __BUTTON_TEXT__;
    font-weight: 600;
}
QToolButton:hover { background: __BUTTON_TOOL_HOVER__; color: __TEXT__; }
QToolButton:pressed { background: __BUTTON_PRESSED__; color: __BUTTON_TEXT__; }
QToolButton:checked { background: __ACCENT_BUTTON__; color: __MARK__; }
QToolButton:checked:hover { background: __ACCENT_BUTTON_HOVER__; }
QToolButton:disabled { color: __TEXT_DISABLED__; background: transparent; }
/* A focus border on a rounded button is drawn incompletely by Qt, so the
   focused state is expressed as a fill instead: it stays flat and intact. */
QToolButton:focus { background: __BUTTON_TOOL_HOVER__; color: __TEXT__; }
QToolButton:focus:hover { background: __BUTTON_TOOL_HOVER__; }
QToolButton[popupMode="1"], QToolButton[popupMode="2"] { padding-right: 22px; }
QToolButton[popupMode="1"]::menu-indicator,
QToolButton[popupMode="2"]::menu-indicator {
    image: url("__CHEVRON_TEXT__");
    subcontrol-origin: padding; subcontrol-position: right center;
    width: 14px; height: 14px; margin-right: 6px;
}
QToolButton[popupMode="0"]::menu-indicator { image: none; width: 0; height: 0; }

QMenuBar {
    background: transparent; color: __TEXT_SOFT__;
    border-bottom: 1px solid __HAIRLINE__;
}
QMenuBar::item { padding: 8px 13px; background: transparent; border-radius: __RADIUS_TILE__px; margin: 2px; }
QMenuBar::item:selected { background: __PANEL_HOVER__; color: __ACCENT_TEXT__; }
QMenuBar::item:pressed { background: __ACCENT_BUTTON__; color: __MARK__; }
QMenuBar::item:disabled { color: __TEXT_DISABLED__; }
QMenuBar QToolButton {
    background: __BUTTON_TOOL__; color: __BUTTON_TEXT__;
    border: 1px solid transparent; border-radius: __RADIUS_TILE__px;
    padding: 2px 22px 2px 9px; margin: 3px 6px 3px 2px; font-weight: 600;
}
QMenuBar QToolButton:hover { background: __BUTTON_TOOL_HOVER__; color: __TEXT__; }
QMenuBar QToolButton:pressed { background: __BUTTON_PRESSED__; color: __BUTTON_TEXT__; }
QMenuBar QToolButton::menu-indicator {
    image: url("__CHEVRON_TEXT__");
    subcontrol-origin: padding; subcontrol-position: right center;
    width: 12px; height: 12px; margin-right: 6px;
}

QMenu {
    background: qlineargradient(x1:0, y1:0, x2:0.85, y2:1,
                stop:0 __MENU_TOP__,
                stop:0.48 __CARD_FLAT__,
                stop:1 __MENU_BOTTOM__);
    border: 1px solid __HAIRLINE_STRONG__;
    padding: 8px; border-radius: __RADIUS_PANEL__px;
}
QMenu::item { padding: 8px 30px 8px 24px; border-radius: __RADIUS_TILE__px; color: __TEXT__; min-height: 20px; }
QMenu::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 __MENU_HOVER_TOP__, stop:1 __MENU_HOVER_BOTTOM__);
    color: __SELECTION_INK__;
}
QMenu::item:disabled { color: __TEXT_DISABLED__; }
QMenu::separator { height: 1px; background: __HAIRLINE__; margin: 6px 12px; }
QMenu::icon { left: 8px; }
QMenu::indicator { width: __INDICATOR__px; height: __INDICATOR__px; }
QMenu::indicator:exclusive:checked { image: url("__MENU_DOT_IMG__"); background: transparent; }
QMenu::indicator:checked { image: url("__MENU_CHECK_IMG__"); background: transparent; }
QMenu::right-arrow {
    image: url("__CHEVRON_RIGHT__");
    subcontrol-origin: padding; subcontrol-position: right center;
    width: 12px; height: 12px; margin-right: 10px;
}

QStatusBar {
    background: transparent; color: __TEXT_MUTED__;
    border: none; border-top: 1px solid __HAIRLINE__;
    font-size: __CAPTION__pt; min-height: 20px;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { color: __TEXT_MUTED__; font-size: __CAPTION__pt; }

/* ==== item views: transparent lists on the card surface ==== */
QAbstractItemView {
    background: transparent;
    alternate-background-color: __ROW_ALT__;
    border: none;
    border-radius: __RADIUS_TILE__px;
    selection-background-color: __STATE_SELECTED__;
    selection-color: __SELECTION_INK__;
    outline: none;
}
QTableView, QTreeView, QListView, QTableWidget, QTreeWidget, QListWidget,
QColumnView, QUndoView, QHelpContentWidget {
    background: transparent;
    alternate-background-color: __ROW_ALT__;
    border: none;
    border-radius: __RADIUS_TILE__px;
    selection-background-color: __STATE_SELECTED__;
    selection-color: __SELECTION_INK__;
    outline: none;
}
QAbstractItemView:disabled { color: __TEXT_DISABLED__; }

QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: __HEADER_FILL__;
    color: __TEXT_MUTED__;
    padding: 8px 11px;
    border: none; border-bottom: 1px solid __HAIRLINE_STRONG__;
    font-weight: 600; font-size: __CAPTION__pt;
    text-transform: uppercase; letter-spacing: 0.6px;
}
QHeaderView::section:hover { background: __PANEL_HOVER__; color: __TEXT__; }
QHeaderView::section:pressed { background: __PANEL_ACTIVE__; }
QHeaderView::section:checked { color: __ACCENT_HOVER__; }
QHeaderView::down-arrow, QHeaderView::up-arrow {
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 12px; height: 12px; margin-right: 7px;
}
QHeaderView::down-arrow {
    image: url("__CHEVRON_DOWN__");
}
QHeaderView::up-arrow {
    image: url("__CHEVRON_UP__");
}
QTableView QTableCornerButton::section {
    background: __HEADER_FILL__; border: none;
}

QTableView::item, QTreeView::item, QListView::item,
QTableWidget::item, QTreeWidget::item, QListWidget::item, QColumnView::item {
    padding: 7px 9px; border: none;
}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected,
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected,
QColumnView::item:selected {
    background: __STATE_SELECTED__; color: __SELECTION_INK__;
}
QTableView::item:hover, QTreeView::item:hover, QListView::item:hover,
QTableWidget::item:hover, QTreeWidget::item:hover, QListWidget::item:hover,
QColumnView::item:hover { background: __PANEL_HOVER__; }
QTableView::item:disabled, QTreeView::item:disabled, QListView::item:disabled,
QTableWidget::item:disabled, QTreeWidget::item:disabled, QListWidget::item:disabled {
    color: __TEXT_DISABLED__;
}

/* Check indicators inside item views need their own glyph rules, otherwise the
   view falls back to the native style and breaks the flat look. */
QAbstractItemView::indicator, QListView::indicator, QTreeView::indicator,
QTableView::indicator, QListWidget::indicator, QTreeWidget::indicator {
    width: __INDICATOR__px; height: __INDICATOR__px;
    border: 1px solid __HAIRLINE_STRONG__;
    border-radius: __INDICATOR_RADIUS__px;
    background: __WELL__;
}
QAbstractItemView::indicator:hover, QListView::indicator:hover,
QTreeView::indicator:hover, QTableView::indicator:hover {
    border: 1px solid __ACCENT__; background: __ACCENT_WASH__;
}
QAbstractItemView::indicator:checked, QListView::indicator:checked,
QTreeView::indicator:checked, QTableView::indicator:checked {
    image: url("__CHECK_IMG__");
    border: 1px solid __ACCENT__;
    background: __ACCENT__;
}
QAbstractItemView::indicator:indeterminate, QListView::indicator:indeterminate,
QTreeView::indicator:indeterminate, QTableView::indicator:indeterminate {
    image: url("__DASH_IMG__");
    border: none;
    background: transparent;
}
QAbstractItemView::indicator:disabled {
    border: 1px solid __HAIRLINE__; background: __DISABLED_FILL__;
}
QTreeView::branch { background: transparent; }
QTreeView::branch:hover { background: transparent; }

/* The splitter handle is a seam between panels, not a lit bar: it stays a
   hairline and hover only warms it with the accent wash. */
QSplitter { background: transparent; }
QSplitter::handle { background: __HAIRLINE__; }
QSplitter::handle:hover { background: __ACCENT_WASH_SOLID__; }
QSplitter::handle:pressed { background: __ACCENT_WASH_SOLID__; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }

QDockWidget::title {
    background: transparent; color: __ACCENT_TEXT__;
    padding: 8px 6px 6px 6px; border: none;
    font-weight: 700; letter-spacing: 1.2px;
    font-size: __CAPTION__pt;
}
QDockWidget::title:hover { color: __ACCENT_TEXT__; }

/* ==== toolbox: flat accordion, cyan rail on the active page ==== */
QToolBox { background: transparent; border: none; }
QToolBox::tab {
    background: __PANEL__;
    border: none; border-left: 2px solid transparent;
    border-radius: __RADIUS_SM__px;
    color: __TEXT_SOFT__;
    padding: 8px 12px; margin: 1px 0;
    font-weight: 600;
}
QToolBox::tab:hover { background: __PANEL_HOVER__; color: __ACCENT_TEXT__; }
QToolBox::tab:selected {
    background: __PANEL_ACTIVE__; color: __ACCENT_HOVER__;
    border-left: 2px solid __ACCENT__;
}
QToolBox::tab:disabled { color: __TEXT_DISABLED__; }
QToolBox > QWidget { background: transparent; }

/* ==== calendar: flat grid, accent selection, quiet header ==== */
QCalendarWidget { background: transparent; border: none; }
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: __PANEL__; border: none; border-radius: __RADIUS__px;
}
QCalendarWidget QToolButton {
    background: transparent; border: none; border-radius: __RADIUS_SM__px;
    color: __TEXT__; padding: 6px 10px; font-weight: 600;
}
QCalendarWidget QToolButton:hover { background: __PANEL_HOVER__; color: __ACCENT_HOVER__; }
QCalendarWidget QToolButton:pressed { background: __PANEL_ACTIVE__; }
QCalendarWidget QToolButton::menu-indicator { image: none; width: 0; }
QCalendarWidget QMenu { background: __POPUP__; }
QCalendarWidget QSpinBox {
    background: transparent; border: none; border-bottom: 1px solid __HAIRLINE__;
    border-radius: 0; color: __TEXT__; selection-background-color: __SELECTION__;
}
QCalendarWidget QAbstractItemView {
    background: __WELL__;
    alternate-background-color: __ROW_ALT__;
    color: __TEXT__;
    selection-background-color: __ACCENT__;
    selection-color: __MARK__;
    outline: none;
    border: none;
}
QCalendarWidget QAbstractItemView:enabled {
    background: __WELL__; color: __TEXT__;
    selection-background-color: __ACCENT__; selection-color: __MARK__;
}
QCalendarWidget QAbstractItemView:disabled { color: __TEXT_DISABLED__; }
QCalendarWidget QWidget { alternate-background-color: __ROW_ALT__; }

QTextBrowser, QTextBrowser#log, QTextEdit#log {
    background: __WELL_DEEP__; border: none; border-radius: __RADIUS__px;
    font-family: __MONO__; font-size: __MONO_SIZE__pt;
}

/* ==== graphics view: no native frame, translucent canvas ==== */
QGraphicsView {
    background: __WELL_DEEP__;
    border: none; border-radius: __RADIUS__px;
    selection-background-color: __SELECTION__;
}
QGraphicsView::rubberband { background: __ACCENT_WASH__; border: 1px solid __ACCENT__; }

/* ==== MDI / wizard surfaces inherit the shell gradient ==== */
QMdiArea { background: qlineargradient(x1:0, y1:0, x2:0.85, y2:1,
                stop:0 __SHELL_TOP__, stop:1 __SHELL_BOTTOM__); border: none; }
QMdiSubWindow { background: transparent; border: none; }
"""


CONTROL_QSS = """
/* ==== buttons: one flat fill, interaction only changes its lightness ==== */
QPushButton {
    background: __BUTTON_TOP__;
    border: none;
    border-radius: __RADIUS_CONTROL__px;
    padding: 7px 16px; color: __BUTTON_TEXT__;
    min-height: 20px;
    font-weight: 600;
}
QPushButton:hover { background: __BUTTON_HOVER_TOP__; color: __BUTTON_TEXT__; }
QPushButton:pressed { background: __BUTTON_PRESSED__; color: __BUTTON_TEXT__; }
QPushButton:focus { background: __BUTTON_HOVER_TOP__; color: __BUTTON_TEXT__; }
QPushButton:disabled {
    background: __DISABLED_FILL__; color: __TEXT_DISABLED__;
}
QPushButton:checked {
    background: __ACCENT_BUTTON__; color: __MARK__; font-weight: 600;
}
QPushButton:checked:hover { background: __ACCENT_BUTTON_HOVER__; }
/* Accent / default button: pure flat azure fill - no gradient, no bevel. */
QPushButton#accent, QPushButton:default {
    background: __ACCENT_BUTTON__;
    border: none; color: __MARK__; font-weight: 700;
    padding: 7px 16px;
}
QPushButton#accent:hover, QPushButton:default:hover { background: __ACCENT_BUTTON_HOVER__; }
QPushButton#accent:pressed, QPushButton:default:pressed { background: __ACCENT_MUTED__; }
QPushButton#accent:disabled, QPushButton:default:disabled {
    background: __DISABLED_FILL__; color: __TEXT_DISABLED__;
}
QPushButton#accent:focus, QPushButton:default:focus { background: __ACCENT_BUTTON_HOVER__; }
QPushButton#danger {
    background: __DANGER_BUTTON_FILL__; color: __DANGER_BUTTON_TEXT__;
}
QPushButton#danger:hover { background: __DANGER_BUTTON_HOVER__; color: __DANGER_BUTTON_TEXT__; }
QPushButton#danger:pressed { background: __DANGER_BUTTON_PRESSED__; color: __DANGER_BUTTON_TEXT__; }
QPushButton#danger:disabled { background: __DISABLED_FILL__; color: __TEXT_DISABLED__; }
QPushButton[flat="true"] {
    background: transparent; border: none; padding: 6px 4px; color: __ACCENT_TEXT__;
}
QPushButton[flat="true"]:hover { background: __PANEL_HOVER__; color: __ACCENT_TEXT__; }
QPushButton[flat="true"]:pressed { background: __PANEL_ACTIVE__; color: __ACCENT_TEXT__; }
QPushButton[flat="true"]:disabled { color: __TEXT_DISABLED__; }
QCommandLinkButton {
    background: __BUTTON_TOP__; border: none; border-radius: __RADIUS_CONTROL__px;
    padding: 9px 12px; color: __TEXT__; text-align: left;
}
QCommandLinkButton:hover { background: __BUTTON_HOVER_TOP__; }
QCommandLinkButton:pressed { background: __BUTTON_PRESSED__; color: __BUTTON_TEXT__; }
QCommandLinkButton:focus { background: __BUTTON_HOVER_TOP__; color: __BUTTON_TEXT__; }

QDialogButtonBox { background: transparent; }
QDialogButtonBox QPushButton { min-width: 84px; }

/* ==== inputs: flat card surface with a quiet azure underline on focus ==== */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit,
QTimeEdit, QDateTimeEdit, QComboBox {
    background: __CARD_FLAT__;
    border: none;
    border-bottom: 1px solid __HAIRLINE__;
    border-radius: __RADIUS_CHIP__px;
    padding: 7px 12px;
    min-height: 20px;
    selection-background-color: __STATE_SELECTED__;
    selection-color: __SELECTION_INK__;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QDateEdit:hover, QTimeEdit:hover, QDateTimeEdit:hover, QPlainTextEdit:hover,
QTextEdit:hover {
    border-bottom-color: __HAIRLINE_STRONG__;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus,
QComboBox:focus, QComboBox:on {
    border-bottom: 2px solid __ACCENT__;
    background: __WELL_DEEP__;
    padding-bottom: 6px;
}
QPlainTextEdit, QTextEdit {
    background: __WELL_DEEP__; border: none; padding: 9px 12px;
    border-radius: __RADIUS_CONTROL__px;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QDateEdit:disabled, QTimeEdit:disabled, QDateTimeEdit:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled {
    color: __TEXT_DISABLED__; background: __DISABLED_FILL__;
}
QLineEdit[state="error"], QComboBox[state="error"], QSpinBox[state="error"] {
    border-bottom: 2px solid __DANGER__; background: __DANGER_WASH__;
}
QLineEdit[state="ok"] { border-bottom: 2px solid __ACCENT__; }
QLineEdit[state="warn"] { border-bottom: 2px solid __WARN__; background: __WARN_WASH__; }
QLineEdit[readOnly="true"] { color: __TEXT_MUTED__; background: __READONLY_FILL__; }
QLineEdit::placeholder { color: __TEXT_MUTED__; }

QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right;
    border: none; width: 28px;
}
QComboBox::drop-down:hover { background: transparent; border-top-right-radius: __RADIUS_CHIP__px; }
/* Qt paints the border-triangle trick as a solid filled rectangle instead of a
   chevron, so every arrow in this sheet is a painted PNG referenced by URL.
   That keeps the mark crisp at 12-14px and recoloured per token. */
QComboBox::down-arrow {
    image: url("__CHEVRON_DOWN__");
    width: 14px; height: 14px; margin-right: 8px;
}
QComboBox::down-arrow:disabled { image: url("__CHEVRON_DISABLED__"); }
QComboBox QAbstractItemView {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 __MENU_TOP__, stop:0.48 __CARD_FLAT__, stop:1 __MENU_BOTTOM__);
    border: 1px solid __HAIRLINE_STRONG__;
    border-radius: __RADIUS_PANEL__px;
    selection-background-color: __STATE_SELECTED__; selection-color: __SELECTION_INK__;
    outline: none; padding: 6px;
}
QComboBox QAbstractItemView::item { padding: 6px 10px; border-radius: __RADIUS_TILE__px; min-height: 20px; }
QComboBox QAbstractItemView::item:selected { background: __STATE_SELECTED__; color: __SELECTION_INK__; }
QComboBox QAbstractItemView::item:hover { background: __PANEL_HOVER__; }

/* ==== toggles: compact flat wells, real glyphs painted as images.
       Deliberately small (__INDICATOR__px): a checkbox is a marker, not a
       button, so it stays visually subordinate to the label next to it. ==== */
QCheckBox, QRadioButton {
    spacing: 7px; background: transparent;
    padding: 2px 0; color: __TEXT__;
}
QCheckBox:hover, QRadioButton:hover { color: __ACCENT_TEXT__; }
QCheckBox:disabled, QRadioButton:disabled { color: __TEXT_DISABLED__; }
QCheckBox::indicator, QRadioButton::indicator { width: __INDICATOR__px; height: __INDICATOR__px; }

QCheckBox::indicator {
    border: 1px solid __HAIRLINE_STRONG__;
    border-radius: __INDICATOR_RADIUS__px;
    background: __WELL__;
}
QCheckBox::indicator:hover { border: 1px solid __ACCENT__; background: __ACCENT_WASH__; }
QCheckBox::indicator:checked {
    image: url("__CHECK_IMG__");
    border: 1px solid __ACCENT__;
    background: __ACCENT__;
}
QCheckBox::indicator:checked:hover { background: __ACCENT_HOVER__; }
QCheckBox::indicator:indeterminate {
    image: url("__DASH_IMG__");
    border: none;
    background: transparent;
}
QCheckBox::indicator:indeterminate:hover { image: url("__DASH_HOVER_IMG__"); }
QCheckBox::indicator:disabled {
    border: 1px solid __HAIRLINE__;
    background: __DISABLED_FILL__;
}

QRadioButton::indicator {
    border: 1px solid __HAIRLINE_STRONG__;
    border-radius: __HALF_INDICATOR__px;
    background: __WELL__;
}
QRadioButton::indicator:hover { border: 1px solid __ACCENT__; background: __ACCENT_WASH__; }
QRadioButton::indicator:checked {
    image: url("__DOT_IMG__");
    border: 1px solid __ACCENT__;
    background: __ACCENT__;
}
QRadioButton::indicator:checked:hover { border: 1px solid __ACCENT_HOVER__; background: __ACCENT_HOVER__; }
QRadioButton::indicator:disabled {
    border: 1px solid __HAIRLINE__;
    background: __DISABLED_FILL__;
}

/* ==== sliders: flat track, accent handle ==== */
QSlider { background: transparent; min-height: 22px; }
QSlider::groove:horizontal {
    height: 3px; background: __TRACK__; border-radius: 2px;
}
QSlider::sub-page:horizontal { background: __ACCENT__; border-radius: 2px; }
QSlider::add-page:horizontal { background: __TRACK__; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 13px; height: 13px; margin: -5px 0; border-radius: 7px;
    background: __ACCENT__; border: none;
}
QSlider::handle:horizontal:hover { background: __ACCENT_HOVER__; }
QSlider::handle:horizontal:pressed { background: __ACCENT_MUTED__; }
QSlider::handle:horizontal:disabled { background: __DISABLED_FILL_STRONG__; }
QSlider::groove:vertical {
    width: 3px; background: __TRACK__; border-radius: 2px;
}
QSlider::add-page:vertical { background: __TRACK__; border-radius: 2px; }
QSlider::sub-page:vertical { background: __ACCENT__; border-radius: 2px; }
QSlider::handle:vertical {
    width: 13px; height: 13px; margin: 0 -5px; border-radius: 7px;
    background: __ACCENT__; border: none;
}
QSlider::handle:vertical:hover { background: __ACCENT_HOVER__; }
QSlider::handle:vertical:pressed { background: __ACCENT_MUTED__; }
QSlider::handle:vertical:disabled { background: __DISABLED_FILL_STRONG__; }
QSlider:focus { outline: none; }

QProgressBar {
    background: __TRACK__;
    border: none;
    border-radius: 3px; text-align: center;
    color: __ACCENT_TEXT__; height: 22px;
    font-size: __CAPTION__pt; font-weight: 600;
}
/* The filled portion is translucent glass, not an opaque slab: the ambient
   gradient of the shell stays visible through the bar, so it reads as a
   measurement over the surface rather than a sticker on top of it.
   The alpha ramp left-to-right keeps the leading edge slightly brighter so a
   filling bar reads as motion even when it is standing still.
   Note: extra state selectors on ::chunk (:hover, :indeterminate) break the
   fill-width calculation in QStyleSheetStyle - the chunk is then painted
   across the whole widget at every value. Only the base ::chunk rule and the
   :disabled background may be declared here; hover feedback lives on the bar
   itself. */
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 __ACCENT_GLASS__,
        stop:1 __ACCENT_GLASS_BRIGHT__);
    border: none; border-radius: 3px;
}
QProgressBar:hover { background: __TRACK_HOVER__; }
QProgressBar:focus { background: __TRACK_HOVER__; }
QProgressBar:disabled { color: __TEXT_DISABLED__; background: __DISABLED_FILL__; }
QProgressBar:disabled::chunk { background: __DISABLED_FILL_STRONG__; }

/* ==== scrollbars: azure ramp thumb on a transparent rail ==== */
QScrollBar:vertical {
    background: transparent; width: 12px; margin: 0; border: none;
}
QScrollBar::handle:vertical {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 __SCROLL_HANDLE__, stop:1 __SCROLL_HANDLE_HOVER__);
    min-height: 36px; border-radius: 3px; margin: 0 2px;
}
QScrollBar::handle:vertical:hover { background: __SCROLL_HANDLE_HOVER__; }
QScrollBar::handle:vertical:pressed { background: __SCROLL_HANDLE_PRESSED__; }
QScrollBar:horizontal {
    background: transparent; height: 12px; margin: 0; border: none;
}
QScrollBar::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 __SCROLL_HANDLE__, stop:1 __SCROLL_HANDLE_HOVER__);
    min-width: 36px; border-radius: 3px; margin: 2px 0;
}
QScrollBar::handle:horizontal:hover { background: __SCROLL_HANDLE_HOVER__; }
QScrollBar::handle:horizontal:pressed { background: __SCROLL_HANDLE_PRESSED__; }
QScrollBar::add-line, QScrollBar::sub-line {
    height: 0; width: 0; border: none; background: transparent; image: none;
}
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:disabled { background: transparent; }
QScrollBar::handle:disabled { background: __HAIRLINE__; }

/* ==== spin boxes: bare chevrons, no button chrome ==== */
QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit { padding-right: 22px; }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button,
QDateEdit::up-button, QDateEdit::down-button,
QTimeEdit::up-button, QTimeEdit::down-button,
QDateTimeEdit::up-button, QDateTimeEdit::down-button {
    subcontrol-origin: border; width: 20px; border: none;
    background: transparent; border-radius: 0;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QDateEdit::up-button, QTimeEdit::up-button, QDateTimeEdit::up-button {
    subcontrol-position: top right;
}
QSpinBox::down-button, QDoubleSpinBox::down-button,
QDateEdit::down-button, QTimeEdit::down-button, QDateTimeEdit::down-button {
    subcontrol-position: bottom right;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover,
QDateEdit::up-button:hover, QDateEdit::down-button:hover,
QTimeEdit::up-button:hover, QTimeEdit::down-button:hover,
QDateTimeEdit::up-button:hover, QDateTimeEdit::down-button:hover {
    background: __PANEL_HOVER__;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed,
QDateEdit::up-button:pressed, QDateEdit::down-button:pressed,
QTimeEdit::up-button:pressed, QTimeEdit::down-button:pressed,
QDateTimeEdit::up-button:pressed, QDateTimeEdit::down-button:pressed {
    background: __PANEL_ACTIVE__;
}
QSpinBox::up-button:disabled, QSpinBox::down-button:disabled,
QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled,
QDateEdit::up-button:disabled, QDateEdit::down-button:disabled,
QTimeEdit::up-button:disabled, QTimeEdit::down-button:disabled,
QDateTimeEdit::up-button:disabled, QDateTimeEdit::down-button:disabled {
    background: transparent;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QDateEdit::up-arrow, QTimeEdit::up-arrow, QDateTimeEdit::up-arrow {
    image: url("__CHEVRON_UP__");
    width: 12px; height: 12px; margin-bottom: 3px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow,
QDateEdit::down-arrow, QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {
    image: url("__CHEVRON_DOWN__");
    width: 12px; height: 12px; margin-top: 3px;
}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QDateEdit::up-arrow:disabled, QTimeEdit::up-arrow:disabled,
QDateTimeEdit::up-arrow:disabled {
    image: url("__CHEVRON_DISABLED_UP__");
}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
QDateEdit::down-arrow:disabled, QTimeEdit::down-arrow:disabled,
QDateTimeEdit::down-arrow:disabled {
    image: url("__CHEVRON_DISABLED__");
}

/* ==== LCD readouts: flat well, accent digits ==== */
QLCDNumber {
    background: __WELL_DEEP__; border: none; border-radius: __RADIUS__px;
    color: __ACCENT_HOVER__;
}

/* ==== dials get a plain transparent plate so the groove below shows ==== */
QDial { background: transparent; }
"""


# ScreenText OCR additions.  They only use existing tokens, so the dark/light
# variants, custom accents and radius changes keep working automatically.
APP_QSS = """
/* ==== cards: painted floating tiles; QSS only keeps the surface transparent ==== */
QFrame[role="card"] {
    background: transparent;
    border: none;
    border-radius: __RADIUS_CARD__px;
}
QFrame[role="card"][tone="well"] {
    background: transparent;
}
QFrame[role="sidePanel"] {
    background: transparent;
    border: none;
}
QFrame[role="leftPanel"] {
    background: transparent;
    border: none;
}
QFrame[role="separator"] {
    background: __HAIRLINE__;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QLabel[role="cardTitle"] {
    color: __ACCENT_HOVER__;
    font-size: __TITLE__pt;
    font-weight: 700;
    letter-spacing: 0.3px;
}
QLabel[role="cardHint"] {
    color: __TEXT_MUTED__;
    font-size: __CAPTION__pt;
}
QLabel[role="metric"] {
    color: __MONO_TEXT__;
    font-family: __MONO__;
    font-size: __MONO_SIZE__pt;
}
QLabel[role="brand"] {
    color: __TEXT__;
    font-size: __TITLE__pt;
    font-weight: 700;
    letter-spacing: 2.4px;
}
QLabel[role="brandMark"] {
    background: __ACCENT_BUTTON__;
    color: __MARK__;
    border-radius: __RADIUS_TILE__px;
    padding: 4px 7px;
    font-weight: 800;
    font-size: __TITLE__pt;
}

/* ==== image wells and output surfaces ==== */
QLabel#previewLabel {
    background: __WELL_DEEP__;
    border: 1px dashed __HAIRLINE_STRONG__;
    border-radius: __RADIUS_CONTROL__px;
    color: __TEXT_MUTED__;
    padding: 12px;
}
QLabel#previewLabel[hasImage="true"] {
    border: 1px solid __HAIRLINE__;
}
QTextEdit#outputText {
    background: __WELL_DEEP__;
    border: none;
    border-radius: __RADIUS_CONTROL__px;
    padding: 10px 12px;
    color: __TEXT__;
    font-family: __MONO__;
    font-size: __MONO_SIZE__pt;
}
QTextBrowser#helpBrowser {
    background: transparent;
    border: none;
    padding: 0;
}
QPlainTextEdit#activityView {
    background: __WELL_DEEP__;
    border: none;
    border-radius: __RADIUS_CONTROL__px;
    padding: 8px 10px;
    color: __TEXT_SOFT__;
}

/* ==== navigation rail ==== */
QListWidget#navList {
    background: transparent;
    border: none;
    outline: none;
    padding: 2px;
}
QListWidget#navList::item {
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    border-radius: __RADIUS_SM__px;
    color: __TEXT_MUTED__;
    padding: 10px 12px;
    margin: 1px 0;
    font-weight: 600;
}
QListWidget#navList::item:hover {
    background: __PANEL_HOVER__;
    color: __TEXT__;
}
QListWidget#navList::item:selected {
    background: __PANEL_ACTIVE__;
    border-left: 2px solid __ACCENT__;
    color: __ACCENT_HOVER__;
}

/* ==== setting validation replaces the original custom state names ==== */
QLineEdit[state="ok"], QComboBox[state="ok"], QSpinBox[state="ok"] {
    border-bottom: 2px solid __ACCENT__;
}
QLineEdit[state="warn"], QComboBox[state="warn"], QSpinBox[state="warn"] {
    border-bottom: 2px solid __WARN__;
    background: __WARN_WASH__;
}
QLineEdit[state="error"], QComboBox[state="error"], QSpinBox[state="error"] {
    border-bottom: 2px solid __DANGER__;
    background: __DANGER_WASH__;
}

/* ==== toolbar labels and compact buttons ==== */
QToolBar QLabel { background: transparent; }
QToolBar QLabel[role="brand"] { padding: 0 2px; }
QToolButton#primaryAction {
    background: __ACCENT_BUTTON__;
    color: __MARK__;
    border-radius: __RADIUS_CONTROL__px;
    padding: 7px 16px;
    font-weight: 700;
}
QToolButton#primaryAction:hover { background: __ACCENT_BUTTON_HOVER__; }
QToolButton#primaryAction:pressed { background: __ACCENT_MUTED__; }
QToolButton#primaryAction:disabled { background: __DISABLED_FILL__; color: __TEXT_DISABLED__; }

/* Menu-bar corner controls (appearance, theme, language): identical icon-only
   tiles. They share one surface and the same hover/pressed/focus states so the
   row never shows two different effects. They sit inside QMenuBar, so the
   generic menu-chip rule would otherwise add its chevron padding; the ID
   selector wins over that type selector and keeps the 30 px square shape from
   the widget itself. */
QToolButton#cornerButton, QToolButton#languageButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: __RADIUS_TILE__px;
    padding: 0;
    margin: 0;
}
QToolButton#cornerButton:hover, QToolButton#languageButton:hover {
    background: __BUTTON_TOOL__;
    border-color: __HAIRLINE__;
}
QToolButton#cornerButton:pressed, QToolButton#languageButton:pressed {
    background: __BUTTON_PRESSED__;
}
QToolButton#cornerButton:focus, QToolButton#languageButton:focus {
    background: __BUTTON_TOOL__;
    border-color: __HAIRLINE__;
}
QToolButton#cornerButton:disabled, QToolButton#languageButton:disabled {
    background: transparent;
    border-color: transparent;
}
QToolButton#cornerButton::menu-indicator, QToolButton#languageButton::menu-indicator {
    image: none; width: 0; height: 0;
}

QFrame#toolbarBrand {
    background: transparent;
    border: none;
    padding: 0 6px;
}
"""


# ========================================================================== popup
# The QComboBox popup lives in Qt's private container window, whose frame and
# item view are outside the main sheet. Flattening the rows there gives the same
# single rounded surface and hover wash as the QMenu dropdown instead of a stack
# of separate dark blocks.
POPUP_QSS = """
QComboBoxPrivateContainer {
    background: __POPUP__;
    border: 1px solid __HAIRLINE_STRONG__;
    border-radius: __RADIUS_PANEL__px;
}
QComboBoxPrivateContainer QAbstractItemView {
    background: transparent;
    border: none;
    padding: 6px;
    outline: none;
    color: __TEXT__;
}
QComboBoxPrivateContainer QAbstractItemView::item {
    padding: 7px 12px;
    border-radius: __RADIUS_TILE__px;
    min-height: 20px;
    color: __TEXT__;
    background: transparent;
}
QComboBoxPrivateContainer QAbstractItemView::item:hover {
    background: __PANEL_HOVER__;
}
QComboBoxPrivateContainer QAbstractItemView::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 __MENU_HOVER_TOP__, stop:1 __MENU_HOVER_BOTTOM__);
    color: __SELECTION_INK__;
}
"""


# =========================================================================== glyphs
# QSS alone cannot draw a checkmark, so checked indicators are painted into PNGs
# once per process and referenced by URL in the sheet. This keeps the widgets
# flat (no native style chrome) while still showing a real mark.

_IMAGE_DIR: Path | None = None
_IMAGE_CACHE: dict[tuple[str, str], str] = {}
_CHEVRON_CACHE: dict[tuple[str, str], str] = {}
# Indicator metrics: a checkbox is a small marker, so the box is deliberately
# compact and its corner radius scales with it instead of the global radius.
INDICATOR_PX = 16
INDICATOR_RADIUS = 4
INDICATOR_HALF = 8


def _image_dir() -> Path:
    global _IMAGE_DIR
    if _IMAGE_DIR is None:
        _IMAGE_DIR = Path(tempfile.mkdtemp(prefix="screentext_ocr_glyphs_"))
        atexit.register(lambda: _cleanup(_IMAGE_DIR))
    return _IMAGE_DIR


def _cleanup(directory: Path | None) -> None:
    if directory is None:
        return
    for entry in directory.glob("*.png"):
        try:
            entry.unlink()
        except OSError:
            pass
    try:
        directory.rmdir()
    except OSError:
        pass


def _canvas(size: int) -> tuple["QImage", QPainter]:
    image = QImage(QSize(size, size), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    return image, painter


def _checkmark(color: str, size: int = INDICATOR_PX) -> "QImage":
    image, painter = _canvas(size)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.6, size * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath(QPointF(size * 0.24, size * 0.52))
    path.lineTo(QPointF(size * 0.43, size * 0.71))
    path.lineTo(QPointF(size * 0.78, size * 0.30))
    painter.drawPath(path)
    painter.end()
    return image


def _dash(color: str, size: int = INDICATOR_PX, plate: int = 46) -> "QImage":
    """Indeterminate mark: a dash on its own translucent plate.

    Qt forces an opaque light plate behind ``:indeterminate`` indicators when a
    ``background`` is combined with ``image``, which made the dash vanish against
    it. The plate is therefore baked into the glyph and the sheet sets neither
    border nor background for that state.
    """
    image, painter = _canvas(size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, plate))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), size * 0.2, size * 0.2)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(
        QRectF(size * 0.26, size * 0.42, size * 0.48, max(2.0, size * 0.17)),
        size * 0.08,
        size * 0.08,
    )
    painter.end()
    return image


def _radio_dot(color: str, size: int = INDICATOR_PX) -> "QImage":
    image, painter = _canvas(size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    inset = size * 0.28
    painter.drawEllipse(QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    painter.end()
    return image


# A chevron is stroke geometry, not a filled polygon.  QSS cannot draw one (a
# border-width triangle is painted as a solid rectangle by Qt), so the mark is
# baked into a PNG at the size the sheet displays it.
CHEVRON_PX = 14  # QSS display size; the glyph is drawn inside this canvas


def _chevron(color: str, direction: str = "down", size: int = CHEVRON_PX) -> "QImage":
    """A small stroked chevron; QSS cannot draw one from border widths."""
    image, painter = _canvas(size)
    pen = QPen(_parse_color(color))
    pen.setWidthF(max(1.4, size * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    if direction == "right":
        # Vertical stroke pair, elbow pointing right: ``>``.
        path = QPainterPath(QPointF(size * 0.42, size * 0.28))
        path.lineTo(QPointF(size * 0.58, size * 0.50))
        path.lineTo(QPointF(size * 0.42, size * 0.72))
    else:
        # Horizontal stroke pair, elbow at 0.58 down / 0.42 up: ``v`` / ``^``.
        elbow = size * (0.58 if direction == "down" else 0.42)
        outer = size * (0.30 if direction == "down" else 0.70)
        path = QPainterPath(QPointF(size * 0.28, outer))
        path.lineTo(QPointF(size * 0.50, elbow))
        path.lineTo(QPointF(size * 0.72, outer))
    painter.drawPath(path)
    painter.end()
    return image


def chevron_path(color: str, direction: str = "down") -> str:
    """Cached absolute PNG path for one chevron ink/direction."""
    key = (color, direction)
    cached = _CHEVRON_CACHE.get(key)
    if cached is not None:
        return cached
    parsed = _parse_color(color)
    if parsed.isValid():
        # A colour name keeps the file name readable and ASCII on Windows.
        slug = parsed.name().lstrip("#")
        if parsed.alpha() != 255:
            slug = f"{slug}{parsed.alpha():02x}"
    else:
        slug = "".join(character if character.isalnum() else "" for character in color)[:24]
    path = _save(f"chev_{direction}_{slug}", _chevron(color, direction))
    _CHEVRON_CACHE[key] = path
    return path


def _save(name: str, image: "QImage") -> str:
    directory = _image_dir()
    target = directory / f"{name}.png"
    image.save(str(target), "PNG")
    return target.as_posix()


def indicator_paths(accent: str, mark: str = "#04161c") -> dict[str, str]:
    """Absolute PNG paths for check / dash / radio-dot glyphs (cached)."""
    key = (accent, mark)
    cached = _IMAGE_CACHE.get(key)
    if cached is not None:
        return json.loads(cached)
    paths = {
        "check": _save(f"check_{accent.strip('#')}_{mark.strip('#')}", _checkmark(mark)),
        "dash": _save(f"dash_{accent.strip('#')}_{mark.strip('#')}", _dash(mark)),
        "dash_hover": _save(
            f"dashh_{accent.strip('#')}_{mark.strip('#')}",
            _dash(_lighten(accent, 1.2), plate=86),
        ),
        "dot": _save(f"dot_{accent.strip('#')}_{mark.strip('#')}", _radio_dot(mark)),
    }
    _IMAGE_CACHE[key] = json.dumps(paths)
    return paths


DEFAULT_TOKENS = {
    "accent": "#0b6ee8",
    "accent_hover": "#3d8bfd",
    "surface": BG_SHELL_1,
    "surface_alt": BG_SHELL_2,
    "border": HAIRLINE,
    "text": TEXT,
    "text_muted": TEXT_MUTED,
    "danger": DANGER,
    "success": SUCCESS_TEXT,
    "radius": 10,
    "font_family": "Segoe UI Variable Display",
    "font_size": FONT_SIZE_BODY,
    "mono_family": "Cascadia Mono",
    "mark": "#f7fdff",
    "selection_ink": SELECTION_INK,
    "card": CARD,
    "card_flat": CARD_FLAT,
    "card_shadow": CARD_SHADOW,
    "well": WELL,
    "well_deep": WELL_DEEP,
    "hairline": HAIRLINE,
    "hairline_strong": HAIRLINE_STRONG,
    "panel": PANEL,
    "panel_hover": PANEL_HOVER,
    "panel_active": PANEL_ACTIVE,
    "shell_top": SHELL_TOP,
    "shell_bloom": SHELL_BLOOM,
    "shell_mid": SHELL_MID,
    "shell_low": SHELL_LOW,
    "shell_bottom": SHELL_BOTTOM,
    "button": BUTTON_TOP,
    "button_hover": BUTTON_HOVER_TOP,
    "button_pressed": BUTTON_PRESSED,
    "button_text": BUTTON_TEXT,
    "button_tool": BUTTON_TOOL,
    "button_tool_hover": BUTTON_TOOL_HOVER,
    "accent_button": ACCENT_BUTTON,
    "accent_button_hover": ACCENT_BUTTON_HOVER,
    "menu_top": MENU_TOP,
    "menu_bottom": MENU_BOTTOM,
    "menu_hover_top": MENU_HOVER_TOP,
    "menu_hover_bottom": MENU_HOVER_BOTTOM,
    "toolbar_top": TOOLBAR_TOP,
    "toolbar_mid": TOOLBAR_MID,
    "toolbar_bottom": TOOLBAR_BOTTOM,
    "scroll_handle": SCROLL_HANDLE,
    "scroll_handle_hover": SCROLL_HANDLE_HOVER,
    "scroll_handle_pressed": SCROLL_HANDLE_PRESSED,
}


# --------------------------------------------------------------------------- palette
# QPainter-based widgets (the painted card, the region overlay) cannot read a
# stylesheet, so the active token dict is published here on every theme pass.
# ``None`` means the native/system style is active and painters must stand down.
_ACTIVE_TOKENS: dict | None = None


def publish_tokens(tokens: dict | None) -> None:
    """Expose the resolved token dict to custom-painted widgets."""
    global _ACTIVE_TOKENS
    _ACTIVE_TOKENS = None if tokens is None else dict(tokens)


def active_tokens() -> dict | None:
    """The tokens currently applied, or ``None`` in system/native mode."""
    return None if _ACTIVE_TOKENS is None else dict(_ACTIVE_TOKENS)


def _token_color(tokens: dict | None, name: str, fallback: str) -> QColor:
    value = (tokens or {}).get(name, fallback)
    color = _parse_color(value)
    return color if color.isValid() else _parse_color(fallback)


def _parse_color(value) -> QColor:
    """Parse a token colour, including the CSS ``rgba(r, g, b, a)`` form.

    ``QColor("rgba(17, 30, 52, 0.48)")`` is invalid in Qt, so every surface
    token would otherwise collapse to opaque black in painter-based widgets.
    """
    if isinstance(value, QColor):
        return QColor(value)
    text = str(value).strip()
    lowered = text.lower()
    if (lowered.startswith("rgba(") or lowered.startswith("rgb(")) and text.endswith(")"):
        inner = text[text.index("(") + 1 : -1]
        parts = [part.strip() for part in inner.split(",")]
        if len(parts) in (3, 4):
            try:
                red = int(round(float(parts[0])))
                green = int(round(float(parts[1])))
                blue = int(round(float(parts[2])))
                alpha = 255
                if len(parts) == 4:
                    alpha_text = parts[3]
                    alpha_value = (
                        float(alpha_text[:-1]) * 2.55
                        if alpha_text.endswith("%")
                        else float(alpha_text)
                    )
                    alpha = alpha_value * 255.0 if alpha_value <= 1.0 else alpha_value
                    alpha = int(round(alpha))
                color = QColor(
                    max(0, min(255, red)),
                    max(0, min(255, green)),
                    max(0, min(255, blue)),
                    max(0, min(255, alpha)),
                )
                if color.isValid():
                    return color
            except ValueError:
                pass
    return QColor(text)


def card_radius(tokens: dict | None = None) -> int:
    """Painted card corner radius: the token radius plus a soft card offset."""
    source = tokens if tokens is not None else (_ACTIVE_TOKENS or DEFAULT_TOKENS)
    return max(6, int(source.get("radius", 10)) + 4)


def painted_palette(tokens: dict | None = None) -> dict:
    """Resolved QColor values for painter-based widgets."""
    source = tokens if tokens is not None else (_ACTIVE_TOKENS or DEFAULT_TOKENS)
    return {
        "card": _token_color(source, "card", CARD),
        "card_flat": _token_color(source, "card_flat", CARD_FLAT),
        "card_border": _token_color(source, "hairline", HAIRLINE),
        "card_shadow": _token_color(source, "card_shadow", CARD_SHADOW),
        "well": _token_color(source, "well", WELL),
        "well_deep": _token_color(source, "well_deep", WELL_DEEP),
        "panel": _token_color(source, "panel", PANEL),
        "text": _token_color(source, "text", TEXT),
        "text_muted": _token_color(source, "text_muted", TEXT_MUTED),
        "accent": _token_color(source, "accent", DEFAULT_TOKENS["accent"]),
        "accent_hover": _token_color(source, "accent_hover", DEFAULT_TOKENS["accent_hover"]),
        "mark": _token_color(source, "mark", DEFAULT_TOKENS["mark"]),
        "radius": int(source.get("radius", 10)),
        "card_radius": card_radius(source),
    }


def _darken(color: str, factor: float = 0.85) -> str:
    """Multiply an #rrggbb colour towards black; non-hex input passes through."""
    text = color.strip()
    if not text.startswith("#") or len(text) not in (7, 9):
        return color
    try:
        rgb = [int(text[i : i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        return color
    scaled = [max(0, min(255, round(channel * factor))) for channel in rgb]
    return "#" + "".join(f"{channel:02x}" for channel in scaled)


def _blend(base: str, over: str, alpha: float) -> str:
    """Composite ``over`` onto ``base`` at ``alpha`` and return #rrggbb.

    Used to derive translucent accent washes from an arbitrary accent colour,
    so a custom accent keeps the same visual weight as the default one.
    """
    try:
        base_rgb = [int(base.strip().lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
        over_rgb = [int(over.strip().lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return over
    mixed = [
        max(0, min(255, round(b + (o - b) * alpha)))
        for b, o in zip(base_rgb, over_rgb)
    ]
    return "#" + "".join(f"{c:02x}" for c in mixed)


def _rgba(color: str, alpha: float) -> str:
    """Turn ``#rrggbb`` into an ``rgba(...)`` string with the given alpha."""
    text = color.strip().lstrip("#")
    if len(text) != 6:
        return color
    try:
        r, g, b = (int(text[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return color
    return f"rgba({r}, {g}, {b}, {alpha:g})"


def _lighten(color: str, factor: float = 1.2) -> str:
    """Scale an ``#rrggbb`` colour towards white; non-hex input passes through."""
    text = color.strip()
    if not text.startswith("#") or len(text) != 7:
        return color
    try:
        rgb = [int(text[i : i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        return color
    scaled = [max(0, min(255, round(channel * factor))) for channel in rgb]
    return "#" + "".join(f"{channel:02x}" for channel in scaled)


def _substitutions(tokens: dict) -> dict[str, str]:
    """Map every __NAME__ placeholder to its value for the current tokens.

    Surface tokens fall back to the module globals, but any value supplied in
    ``tokens`` under the matching upper-case name wins. That is what lets the
    light variant reuse the exact same sheet with re-derived translucencies.
    """
    def surface(name: str, default: str) -> str:
        return str(tokens.get(name.lower(), tokens.get(name, default)))

    accent = str(tokens["accent"])
    hover = str(tokens["accent_hover"])
    family = str(tokens.get("font_family", "Segoe UI Variable Display"))
    mono = str(tokens.get("mono_family", "Cascadia Mono"))
    body = int(tokens.get("font_size", FONT_SIZE_BODY))
    text = str(tokens.get("text", TEXT))
    muted = str(tokens.get("text_muted", TEXT_MUTED))
    mark = str(tokens.get("mark", "#f7fdff"))
    selection_ink = str(tokens.get("selection_ink", SELECTION_INK))
    # Chevron inks reuse the exact inks of their context: accent text inside
    # accent-tinted controls, body ink for dropdown arrows, muted for menu
    # navigation and the disabled ink for inactive arrows.
    accent_text = surface("ACCENT_TEXT", ACCENT_TEXT)
    disabled_text = surface("TEXT_DISABLED", TEXT_DISABLED)
    radius = int(tokens.get("radius", 10))
    radius_sm = max(0, radius - 1)
    badge_radius = max(2, radius - 1)
    chip_radius = max(0, radius)
    control_radius = max(0, radius + 1)
    panel_radius = max(0, radius + 2)
    card_radius_value = card_radius(tokens)
    tile_radius = max(0, radius - 2)

    shell_bg = (
        "qradialgradient(cx:0.08, cy:0.92, radius:1.34, fx:0.08, fy:0.92,"
        f" stop:0 {surface('SHELL_GLOW_1', SHELL_GLOW_1)},"
        f" stop:0.22 {surface('SHELL_GLOW_2', SHELL_GLOW_2)},"
        f" stop:0.46 {surface('SHELL_GLOW_3', SHELL_GLOW_3)},"
        f" stop:0.68 {surface('SHELL_GLOW_4', SHELL_GLOW_4)},"
        f" stop:0.86 {surface('SHELL_GLOW_5', SHELL_GLOW_5)},"
        f" stop:1 {surface('SHELL_GLOW_6', SHELL_GLOW_6)})"
    )
    toolbar_bg = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f" stop:0 {surface('TOOLBAR_TOP', TOOLBAR_TOP)},"
        f" stop:0.5 {surface('TOOLBAR_MID', TOOLBAR_MID)},"
        f" stop:1 {surface('TOOLBAR_BOTTOM', TOOLBAR_BOTTOM)})"
    )
    return {
        "__FONT__": f'"{family}", {FONT_STACK.split(",", 1)[1].strip()}',
        "__MONO__": f'"{mono}", {MONO_STACK.split(",", 1)[1].strip()}',
        "__BODY__": str(body),
        "__TITLE__": str(body + 1),
        "__CAPTION__": str(FONT_SIZE_CAPTION) if body == FONT_SIZE_BODY else str(body - 1),
        "__MONO_SIZE__": str(FONT_SIZE_MONO) if body == FONT_SIZE_BODY else str(body),
        "__ACCENT__": accent,
        "__ACCENT_HOVER__": hover,
        "__ACCENT_MUTED__": _darken(accent, 0.82),
        "__ACCENT_TEXT__": surface("ACCENT_TEXT", ACCENT_TEXT),
        "__ACCENT_WASH__": _rgba(accent, 0.14),
        "__ACCENT_WASH_SOLID__": _rgba(accent, 0.24),
        # A translucent alpha ramp keeps the bar glassy; the light variant uses
        # the same idea with its own alphas so the fill stays visible on white.
        "__ACCENT_GLASS__": _rgba(accent, float(tokens.get("ACCENT_GLASS_ALPHA", 0.44))),
        "__ACCENT_GLASS_BRIGHT__": _rgba(
            _lighten(accent, 1.15), float(tokens.get("ACCENT_GLASS_ALPHA_BRIGHT", 0.58))
        ),
        "__SELECTION__": _rgba(accent, 0.32),
        "__MARK__": mark,
        "__MONO_TEXT__": surface("MONO_TEXT", MONO_TEXT),
        "__CHECK_IMG__": indicator_paths(accent, mark)["check"],
        "__DASH_IMG__": indicator_paths(accent, mark)["dash"],
        "__DASH_HOVER_IMG__": indicator_paths(accent, mark)["dash_hover"],
        "__DOT_IMG__": indicator_paths(accent, mark)["dot"],
        "__MENU_CHECK_IMG__": indicator_paths(accent, selection_ink)["check"],
        "__MENU_DOT_IMG__": indicator_paths(accent, selection_ink)["dot"],
        "__CHEVRON_DOWN__": chevron_path(accent_text, "down"),
        "__CHEVRON_UP__": chevron_path(accent_text, "up"),
        "__CHEVRON_RIGHT__": chevron_path(muted, "right"),
        "__CHEVRON_TEXT__": chevron_path(text, "down"),
        "__CHEVRON_DISABLED__": chevron_path(disabled_text, "down"),
        "__CHEVRON_DISABLED_UP__": chevron_path(disabled_text, "up"),
        "__SELECTION_INK__": selection_ink,
        "__SHELL_BG__": shell_bg,
        "__TOOLBAR_BG__": toolbar_bg,
        "__PANEL__": surface("PANEL", PANEL),
        "__PANEL_HOVER__": surface("PANEL_HOVER", PANEL_HOVER),
        "__PANEL_ACTIVE__": surface("PANEL_ACTIVE", PANEL_ACTIVE),
        "__CARD__": surface("CARD", CARD),
        "__CARD_FLAT__": surface("CARD_FLAT", CARD_FLAT),
        "__CARD_SHADOW__": surface("CARD_SHADOW", CARD_SHADOW),
        "__WELL__": surface("WELL", WELL),
        "__WELL_DEEP__": surface("WELL_DEEP", WELL_DEEP),
        "__HAIRLINE__": surface("HAIRLINE", HAIRLINE),
        "__HAIRLINE_STRONG__": surface("HAIRLINE_STRONG", HAIRLINE_STRONG),
        "__SHELL_TOP__": surface("SHELL_TOP", SHELL_TOP),
        "__SHELL_BLOOM__": surface("SHELL_BLOOM", SHELL_BLOOM),
        "__SHELL_MID__": surface("SHELL_MID", SHELL_MID),
        "__SHELL_LOW__": surface("SHELL_LOW", SHELL_LOW),
        "__SHELL_BOTTOM__": surface("SHELL_BOTTOM", SHELL_BOTTOM),
        "__TOOLBAR_FILL__": surface("TOOLBAR_FILL", TOOLBAR_FILL),
        "__HEADER_FILL__": surface("HEADER_FILL", HEADER_FILL),
        "__ROW_ALT__": surface("ROW_ALT", ROW_ALT),
        "__POPUP__": surface("POPUP", POPUP),
        "__MENU_TOP__": surface("MENU_TOP", MENU_TOP),
        "__MENU_BOTTOM__": surface("MENU_BOTTOM", MENU_BOTTOM),
        "__MENU_HOVER_TOP__": surface("MENU_HOVER_TOP", MENU_HOVER_TOP),
        "__MENU_HOVER_BOTTOM__": surface("MENU_HOVER_BOTTOM", MENU_HOVER_BOTTOM),
        "__TRACK__": surface("TRACK", TRACK),
        "__TRACK_HOVER__": surface("TRACK_HOVER", TRACK_HOVER),
        "__RAIL__": surface("RAIL", RAIL),
        "__SCROLL_HANDLE__": surface("SCROLL_HANDLE", SCROLL_HANDLE),
        "__SCROLL_HANDLE_HOVER__": surface("SCROLL_HANDLE_HOVER", SCROLL_HANDLE_HOVER),
        "__SCROLL_HANDLE_PRESSED__": surface("SCROLL_HANDLE_PRESSED", SCROLL_HANDLE_PRESSED),
        "__PRESSED_FILL__": surface("PRESSED_FILL", PRESSED_FILL),
        "__DISABLED_FILL__": surface("DISABLED_FILL", DISABLED_FILL),
        "__DISABLED_FILL_STRONG__": surface("DISABLED_FILL_STRONG", DISABLED_FILL_STRONG),
        "__READONLY_FILL__": surface("READONLY_FILL", READONLY_FILL),
        "__STATE_HOVER__": surface("STATE_HOVER", STATE_HOVER),
        "__STATE_PRESSED__": surface("STATE_PRESSED", STATE_PRESSED),
        "__STATE_SELECTED__": surface("STATE_SELECTED", STATE_SELECTED),
        "__STATE_SELECTED_HOVER__": surface("STATE_SELECTED_HOVER", STATE_SELECTED_HOVER),
        "__BUTTON_TOP__": surface("BUTTON_TOP", BUTTON_TOP),
        "__BUTTON_HOVER_TOP__": surface("BUTTON_HOVER_TOP", BUTTON_HOVER_TOP),
        "__BUTTON_PRESSED__": surface("BUTTON_PRESSED", BUTTON_PRESSED),
        "__BUTTON_TEXT__": surface("BUTTON_TEXT", BUTTON_TEXT),
        "__BUTTON_TOOL__": surface("BUTTON_TOOL", BUTTON_TOOL),
        "__BUTTON_TOOL_HOVER__": surface("BUTTON_TOOL_HOVER", BUTTON_TOOL_HOVER),
        "__ACCENT_BUTTON__": surface("ACCENT_BUTTON", _darken(accent, 0.85)),
        "__ACCENT_BUTTON_HOVER__": surface("ACCENT_BUTTON_HOVER", _darken(accent, 0.95)),
        "__DANGER_BUTTON_FILL__": surface("DANGER_BUTTON_FILL", DANGER_BUTTON_FILL),
        "__DANGER_BUTTON_HOVER__": surface("DANGER_BUTTON_HOVER", DANGER_BUTTON_HOVER),
        "__DANGER_BUTTON_PRESSED__": surface("DANGER_BUTTON_PRESSED", DANGER_BUTTON_PRESSED),
        "__DANGER_BUTTON_TEXT__": surface("DANGER_BUTTON_TEXT", DANGER_BUTTON_TEXT),
        "__INDICATOR__": str(int(tokens.get("indicator_size", INDICATOR_PX))),
        "__INDICATOR_RADIUS__": str(INDICATOR_RADIUS),
        "__HALF_INDICATOR__": str(INDICATOR_HALF),
        "__RADIUS__": str(radius),
        "__RADIUS_SM__": str(radius_sm),
        "__RADIUS_CHIP__": str(chip_radius),
        "__RADIUS_CONTROL__": str(control_radius),
        "__RADIUS_PANEL__": str(panel_radius),
        "__RADIUS_CARD__": str(card_radius_value),
        "__RADIUS_TILE__": str(tile_radius),
        "__BADGE_RADIUS__": str(badge_radius),
        "__RADIUS_BADGE__": str(badge_radius),
        "__GROUP_PAD__": str(max(10, radius * 2)),
        "__DANGER__": DANGER,
        "__DANGER_WASH__": DANGER_WASH,
        "__DANGER_WASH_STRONG__": DANGER_WASH_STRONG,
        "__DANGER_TEXT__": surface("DANGER_TEXT", DANGER_TEXT),
        "__WARN__": WARN,
        "__WARN_WASH__": WARN_WASH,
        "__WARN_TEXT__": surface("WARN_TEXT", WARN_TEXT),
        "__SUCCESS_WASH__": SUCCESS_WASH,
        "__SUCCESS_TEXT__": surface("SUCCESS_TEXT", SUCCESS_TEXT),
        "__TEXT__": text,
        "__TEXT_MUTED__": muted,
        "__TEXT_SOFT__": surface("TEXT_SOFT", TEXT_SOFT),
        "__TEXT_DISABLED__": surface("TEXT_DISABLED", TEXT_DISABLED),
    }


def render_qss(tokens: dict | None = None) -> str:
    """Render the full sheet, resolving every __TOKEN__ placeholder."""
    sheet = BASE_QSS + CONTROL_QSS + APP_QSS
    for key, value in _substitutions(dict(DEFAULT_TOKENS, **(tokens or {}))).items():
        sheet = sheet.replace(key, value)
    return sheet


def _relative_luminance(color: QColor) -> float:
    def channel(value: float) -> float:
        value = value / 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())


def readable_mark(accent: str) -> str:
    """Ink for text/marks painted on the accent fill (white or near-black)."""
    color = QColor(accent)
    if not color.isValid():
        return "#f7fdff"
    return "#04161c" if _relative_luminance(color) > 0.42 else "#f7fdff"


def resolve_tokens(
    variant: str = "dark",
    accent: str | None = None,
    radius: int | None = None,
    font_family: str | None = None,
    font_size: int | None = None,
    mark: str | None = None,
) -> dict:
    """Single source of truth for the appearance inspector.

    The window no longer hand-derives accent/hover/mark: both the dark and the
    light sheet come from this function, so the inspector, the export and the
    tests can never drift apart.
    """
    tokens = light_tokens() if variant == "light" else dict(DEFAULT_TOKENS)

    base = QColor(accent or tokens["accent"])
    if not base.isValid():
        base = QColor(DEFAULT_TOKENS["accent"])
    if variant == "light":
        # On white the fill and the ink both need to be darker than the bright
        # azure that reads well on navy.
        fill = base.darker(112)
        hover = fill.darker(120)
        tokens["text"] = LIGHT_TOKENS["text"]
        tokens["text_muted"] = LIGHT_TOKENS["text_muted"]
    else:
        fill = base
        hover = _blend(base.name(), "#ffffff", 0.20)
        tokens["text"] = DEFAULT_TOKENS["text"]
        tokens["text_muted"] = DEFAULT_TOKENS["text_muted"]
    tokens["accent"] = fill.name()
    tokens["accent_hover"] = hover.name() if isinstance(hover, QColor) else str(hover)
    tokens["radius"] = int(DEFAULT_TOKENS["radius"] if radius is None else radius)
    tokens["font_family"] = str(font_family or DEFAULT_TOKENS["font_family"])
    tokens["font_size"] = int(font_size or DEFAULT_TOKENS["font_size"])
    tokens["mark"] = str(mark or readable_mark(fill.name()))
    tokens["accent_button"] = _darken(fill.name(), 0.85)
    tokens["accent_button_hover"] = _darken(fill.name(), 0.95)
    return tokens


def log_palette(dark: bool = True) -> dict[str, str]:
    """Ink for the activity console, shared by its HTML rows and stamps."""
    if dark:
        return {
            "info": "#73c9ff",
            "success": SUCCESS_TEXT,
            "warn": WARN_TEXT,
            "danger": DANGER_TEXT,
            "stamp": "rgba(170, 194, 229, 0.62)",
            "message": TEXT_SOFT,
        }
    return {
        "info": "#0a5f96",
        "success": "#1f6b45",
        "warn": "#6f5518",
        "danger": "#8e2a20",
        "stamp": "rgba(24, 46, 78, 0.55)",
        "message": "#12233d",
    }


def tooltip_palette(variant: str = "dark") -> dict[str, str]:
    """Colours for the frameless rich tooltip (a top-level window needs this)."""
    if variant == "light":
        return {
            "background": "rgba(250, 251, 252, 0.98)",
            "text": "#12233d",
            "muted": "#42566f",
            "strong": "#0a4b8f",
            "border": "rgba(24, 56, 104, 0.16)",
        }
    return {
        "background": "rgba(20, 35, 58, 0.97)",
        "text": "#eef5ff",
        "muted": "#a9bede",
        "strong": "#73c9ff",
        "border": "rgba(140, 190, 255, 0.24)",
    }


def panel_palette(variant: str = "dark") -> dict[str, str]:
    """Colours for panels that paint their own rich text (help, diagnostics)."""
    if variant == "light":
        return {
            "text": "#12233d",
            "muted": "#42566f",
            "accent": "#0a4b8f",
            "danger": "#8e2a20",
            "success": "#1f6b45",
        }
    return {
        "text": TEXT,
        "muted": "#a9bede",
        "accent": "#73c9ff",
        "danger": DANGER_TEXT,
        "success": SUCCESS_TEXT,
    }


def full_stylesheet(variant: str = "dark") -> str:
    """Render the default sheet for the requested palette variant."""
    if variant == "light":
        return light_stylesheet()
    return render_qss()


def light_tokens(overrides: dict | None = None) -> dict:
    """Token set for the light palette, merged with the dark defaults.

    Both spellings are published (``CARD`` and ``card``) because the sheet
    resolver checks the lower-case component token first; without the mirror a
    light sheet silently kept the dark card/well fills.
    """
    tokens = dict(DEFAULT_TOKENS)
    tokens.update(LIGHT_TOKENS)
    for name, value in LIGHT_OVERRIDES.items():
        tokens[name] = value
        tokens[name.lower()] = value
    tokens.update(overrides or {})
    return tokens


def light_stylesheet(overrides: dict | None = None) -> str:
    """Render the light sheet.

    The light variant reuses the dark sheet verbatim but re-derives every
    surface token, so the two palettes can never drift apart: a change to the
    layout or a new selector applies to both automatically.
    """
    return render_qss(light_tokens(overrides))


def tokens_to_qss(tokens: dict) -> str:
    """Regenerate the sheet from a token dict (accent, font, radius)."""
    return render_qss(tokens)


def popup_stylesheet(
    variant: str = "dark", radius: int | None = None, accent: str | None = None
) -> str:
    """Style the QComboBox popup container window.

    Qt paints the popup frame around the item view with the platform window
    colour, so the transparent margins around a rounded, dark item view show up
    as white bands. Styling the internal container closes that gap. Tokens are
    resolved the same way as the main sheet, so a light popup and a custom
    accent follow the appearance inspector automatically.
    """
    tokens = resolve_tokens(variant, accent=accent, radius=radius)
    sheet = POPUP_QSS
    for key, value in _substitutions(tokens).items():
        sheet = sheet.replace(key, value)
    return sheet


def save_theme(path: str | Path, extra: str = "", variant: str = "dark") -> Path:
    target = Path(path)
    target.write_text(full_stylesheet(variant) + extra, encoding="utf-8")
    return target


def load_theme(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def export_tokens(path: str | Path, tokens: dict) -> Path:
    target = Path(path)
    target.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    return target


def resolve_font(tokens: dict | None = None) -> tuple[str, int]:
    """Return the (family, point size) a QApplication font should use."""
    merged = dict(DEFAULT_TOKENS, **(tokens or {}))
    return str(merged["font_family"]), int(merged["font_size"])
