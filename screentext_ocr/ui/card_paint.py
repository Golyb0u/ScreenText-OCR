"""Painted floating cards (flatuiux 2.1.0 "navy board" language).

The stylesheet makes ``QFrame[role="card"]`` transparent, because a flat QSS
fill cannot express the soft ambient shadow that makes a card float over the
board.  This module draws the card itself: a graded tile with a 1 px hairline
and, underneath it, a stack of translucent rounded rectangles that reads as a
shadow.

Painting is only active while a token palette has been published by the theme
engine.  In native/system mode :func:`theme.active_tokens` returns ``None`` and
:func:`paint_card` returns ``False`` without touching the widget, so the
platform style keeps owning the frame.
"""

from __future__ import annotations

from PyQt5 import QtCore, QtGui, QtWidgets

from . import theme

# The card is inset so the painted shadow has room inside the widget bounds:
# Qt clips every widget's painting to its own rectangle, so a shadow that
# overhangs the widget would simply be cut off.
SHADOW_INSET = 10.0
FLAT_INSET = 2.0
SHADOW_SPREAD = 8

TONES = ("card", "well", "panel", "accent")

_FALLBACKS = {
    "card": "#111e34",
    "card_border": "#76a8f2",
    "card_shadow": "#000000",
    "well": "#10213a",
    "panel": "#5682cd",
    "accent": "#0b6ee8",
    "accent_hover": "#3d8bfd",
}


def _color(value, name: str = "") -> QtGui.QColor:
    """Resolve one palette entry to a valid QColor.

    The CSS form of the surface tokens (``rgba(r, g, b, 0.48)``) is parsed by
    the theme engine; this wrapper only supplies a tone-appropriate fallback so
    a broken token can never paint an opaque black rectangle over the board.
    """
    fallback = _FALLBACKS.get(name, "#000000")
    color = theme._parse_color(value)
    return color if color.isValid() else QtGui.QColor(fallback)


def _paint_shadow(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    radius: float,
    base: QtGui.QColor,
    spread: int = SHADOW_SPREAD,
) -> None:
    """Layered rounded rects approximate a soft ambient shadow in QPainter.

    Each layer is offset two pixels down and grows by one pixel, so the stack
    is densest under the card and fades towards its top edge.
    """
    painter.setPen(QtCore.Qt.NoPen)
    for index in range(spread, 0, -1):
        weight = (spread - index + 1) / spread
        layer = QtGui.QColor(base)
        layer.setAlpha(max(2, int(base.alpha() * weight * 0.16)))
        painter.setBrush(layer)
        painter.drawRoundedRect(
            rect.adjusted(-index, -index + 2, index, index + 2),
            radius + index,
            radius + index,
        )


def _board_light(tokens: dict) -> bool:
    """True when the active board (shell surface) is a light one."""
    board = _color(tokens.get("surface", ""), "")
    return board.isValid() and board.lightness() >= 160


def paint_card(widget: QtWidgets.QWidget, event, tone: str = "card") -> bool:
    """Paint one card surface; return ``False`` when the native style owns it."""
    tokens = theme.active_tokens()
    if tokens is None:
        return False
    if tone not in TONES:
        tone = "card"

    palette = theme.painted_palette(tokens)
    fill = _color(palette["card"], "card")
    border = _color(palette["card_border"], "card_border")
    shadow = _color(palette["card_shadow"], "card_shadow")
    well = _color(palette["well"], "well")
    panel = _color(palette["panel"], "panel")
    accent = _color(palette["accent"], "accent")
    accent_hover = _color(palette["accent_hover"], "accent_hover")
    radius = float(palette["card_radius"])
    shadowed = tone in ("card", "accent")
    light_board = _board_light(tokens)

    if light_board:
        # The light variant is "white tiles on a pale azure sky". If the
        # token dict still carries the dark surface ramp for the card/well
        # entries, re-read it as the light one instead of dropping a dark
        # slab onto a bright board.
        if fill.lightness() < 128:
            fill = QtGui.QColor(255, 255, 255, 238)
        if well.lightness() < 128:
            well = QtGui.QColor(230, 239, 251, 246)
        if shadow.lightness() < 128:
            shadow = QtGui.QColor(20, 45, 85, 96)

    painter = QtGui.QPainter(widget)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        clip = event.rect() if event is not None else widget.rect()
        if clip.isValid():
            painter.setClipRect(clip)

        inset = SHADOW_INSET if shadowed else FLAT_INSET
        card = QtCore.QRectF(widget.rect()).adjusted(inset, inset, -inset, -inset)
        if card.width() <= 0 or card.height() <= 0:
            return True

        if shadowed:
            _paint_shadow(painter, card, radius, shadow)

        if tone == "panel":
            painter.setBrush(panel)
            painter.setPen(QtCore.Qt.NoPen)
        elif tone == "well":
            painter.setBrush(well)
            painter.setPen(QtGui.QPen(border, 1))
        elif tone == "accent":
            gradient = QtGui.QLinearGradient(card.topLeft(), card.bottomRight())
            gradient.setColorAt(0.0, QtGui.QColor(accent).lighter(108))
            gradient.setColorAt(1.0, accent_hover)
            painter.setBrush(gradient)
            painter.setPen(QtCore.Qt.NoPen)
        else:
            # Normal cards stay in the same navy family as the shell: a quiet
            # gradient so translucent edges let the board glow through. On the
            # light board the far stop is a pale azure instead of neutral grey,
            # so the tile reads as part of the blue theme rather than beige.
            gradient = QtGui.QLinearGradient(card.topLeft(), card.bottomRight())
            gradient.setColorAt(0.0, fill)
            if light_board:
                gradient.setColorAt(
                    1.0, QtGui.QColor(226, 236, 250, min(255, fill.alpha()))
                )
            else:
                gradient.setColorAt(1.0, QtGui.QColor(fill).darker(118))
            painter.setBrush(gradient)
            painter.setPen(QtGui.QPen(border, 1))

        painter.drawRoundedRect(card, radius, radius)
    finally:
        painter.end()
    return True
