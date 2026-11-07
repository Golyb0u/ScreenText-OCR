"""Small hand-painted line icons.

The source GUI avoids native icon themes; the same approach is kept here so the
toolbar stays flat and monochrome like the rest of the interface.
"""

from __future__ import annotations

from PyQt5 import QtCore, QtGui


def _icon_painter(size: int, color: str) -> tuple[QtGui.QPixmap, QtGui.QPainter]:
    pixmap = QtGui.QPixmap(size * 2, size * 2)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.scale(2.0, 2.0)
    pen = QtGui.QPen(QtGui.QColor(color))
    pen.setWidthF(1.55)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)
    return pixmap, painter


def make_icon(kind: str, color: str = "#9fb6d8", size: int = 20) -> QtGui.QIcon:
    pixmap, p = _icon_painter(size, color)
    s = float(size)

    if kind == "region":
        pen = p.pen()
        pen.setStyle(QtCore.Qt.DashLine)
        p.setPen(pen)
        p.drawRect(QtCore.QRectF(s * 0.18, s * 0.22, s * 0.64, s * 0.56))
        p.setPen(QtGui.QPen(QtGui.QColor(color), 1.55))
        for x1, y1, x2, y2 in (
            (0.09, 0.32, 0.09, 0.20),
            (0.09, 0.20, 0.22, 0.20),
            (0.78, 0.20, 0.91, 0.20),
            (0.91, 0.20, 0.91, 0.32),
            (0.09, 0.68, 0.09, 0.80),
            (0.09, 0.80, 0.22, 0.80),
            (0.78, 0.80, 0.91, 0.80),
            (0.91, 0.80, 0.91, 0.68),
        ):
            p.drawLine(
                QtCore.QPointF(s * x1, s * y1), QtCore.QPointF(s * x2, s * y2)
            )
    elif kind == "capture":
        p.drawRoundedRect(QtCore.QRectF(s * 0.12, s * 0.30, s * 0.76, s * 0.50), 3, 3)
        p.drawEllipse(QtCore.QRectF(s * 0.34, s * 0.42, s * 0.32, s * 0.26))
        p.drawLine(QtCore.QPointF(s * 0.28, s * 0.30), QtCore.QPointF(s * 0.35, s * 0.20))
        p.drawLine(QtCore.QPointF(s * 0.35, s * 0.20), QtCore.QPointF(s * 0.55, s * 0.20))
    elif kind == "open":
        path = QtGui.QPainterPath()
        path.moveTo(s * 0.12, s * 0.30)
        path.lineTo(s * 0.12, s * 0.78)
        path.lineTo(s * 0.88, s * 0.78)
        path.lineTo(s * 0.88, s * 0.38)
        path.lineTo(s * 0.46, s * 0.38)
        path.lineTo(s * 0.38, s * 0.28)
        path.lineTo(s * 0.18, s * 0.28)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "paste":
        p.drawRoundedRect(QtCore.QRectF(s * 0.22, s * 0.18, s * 0.56, s * 0.68), 2, 2)
        p.drawRoundedRect(QtCore.QRectF(s * 0.35, s * 0.10, s * 0.30, s * 0.14), 2, 2)
        for y in (0.40, 0.52, 0.64):
            p.drawLine(QtCore.QPointF(s * 0.33, s * y), QtCore.QPointF(s * 0.67, s * y))
    elif kind == "scan":
        p.drawLine(QtCore.QPointF(s * 0.12, s * 0.34), QtCore.QPointF(s * 0.12, s * 0.16))
        p.drawLine(QtCore.QPointF(s * 0.12, s * 0.16), QtCore.QPointF(s * 0.30, s * 0.16))
        p.drawLine(QtCore.QPointF(s * 0.70, s * 0.16), QtCore.QPointF(s * 0.88, s * 0.16))
        p.drawLine(QtCore.QPointF(s * 0.88, s * 0.16), QtCore.QPointF(s * 0.88, s * 0.34))
        p.drawLine(QtCore.QPointF(s * 0.12, s * 0.66), QtCore.QPointF(s * 0.12, s * 0.84))
        p.drawLine(QtCore.QPointF(s * 0.12, s * 0.84), QtCore.QPointF(s * 0.30, s * 0.84))
        p.drawLine(QtCore.QPointF(s * 0.70, s * 0.84), QtCore.QPointF(s * 0.88, s * 0.84))
        p.drawLine(QtCore.QPointF(s * 0.88, s * 0.84), QtCore.QPointF(s * 0.88, s * 0.66))
        for y in (0.38, 0.50, 0.62):
            p.drawLine(QtCore.QPointF(s * 0.30, s * y), QtCore.QPointF(s * 0.70, s * y))
    elif kind == "theme":
        p.drawEllipse(QtCore.QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56))
        p.setBrush(QtGui.QColor(color))
        path = QtGui.QPainterPath()
        path.moveTo(s * 0.50, s * 0.22)
        path.arcTo(QtCore.QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56), 90, -180)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "settings":
        for index, y in enumerate((0.30, 0.50, 0.70)):
            p.drawLine(QtCore.QPointF(s * 0.14, s * y), QtCore.QPointF(s * 0.86, s * y))
            x = (0.34, 0.66, 0.46)[index]
            p.setBrush(QtGui.QColor(color))
            p.drawEllipse(QtCore.QRectF(s * (x - 0.07), s * (y - 0.07), s * 0.14, s * 0.14))
            p.setBrush(QtCore.Qt.NoBrush)
    elif kind == "log":
        p.drawRoundedRect(QtCore.QRectF(s * 0.14, s * 0.16, s * 0.72, s * 0.68), 2, 2)
        for y, width in ((0.34, 0.40), (0.50, 0.50), (0.66, 0.30)):
            p.drawLine(
                QtCore.QPointF(s * 0.26, s * y),
                QtCore.QPointF(s * (0.26 + width), s * y),
            )
    elif kind == "copy":
        p.drawRoundedRect(QtCore.QRectF(s * 0.30, s * 0.28, s * 0.48, s * 0.54), 2, 2)
        p.drawRoundedRect(QtCore.QRectF(s * 0.20, s * 0.16, s * 0.48, s * 0.54), 2, 2)
    elif kind == "save":
        p.drawLine(QtCore.QPointF(s * 0.50, s * 0.14), QtCore.QPointF(s * 0.50, s * 0.58))
        p.drawLine(QtCore.QPointF(s * 0.34, s * 0.44), QtCore.QPointF(s * 0.50, s * 0.60))
        p.drawLine(QtCore.QPointF(s * 0.66, s * 0.44), QtCore.QPointF(s * 0.50, s * 0.60))
        p.drawLine(QtCore.QPointF(s * 0.18, s * 0.70), QtCore.QPointF(s * 0.18, s * 0.84))
        p.drawLine(QtCore.QPointF(s * 0.18, s * 0.84), QtCore.QPointF(s * 0.82, s * 0.84))
        p.drawLine(QtCore.QPointF(s * 0.82, s * 0.84), QtCore.QPointF(s * 0.82, s * 0.70))
    elif kind == "trash":
        p.drawLine(QtCore.QPointF(s * 0.22, s * 0.28), QtCore.QPointF(s * 0.78, s * 0.28))
        p.drawLine(QtCore.QPointF(s * 0.40, s * 0.20), QtCore.QPointF(s * 0.60, s * 0.20))
        p.drawRoundedRect(QtCore.QRectF(s * 0.28, s * 0.32, s * 0.44, s * 0.50), 2, 2)
        p.drawLine(QtCore.QPointF(s * 0.42, s * 0.42), QtCore.QPointF(s * 0.42, s * 0.70))
        p.drawLine(QtCore.QPointF(s * 0.58, s * 0.42), QtCore.QPointF(s * 0.58, s * 0.70))
    elif kind == "play":
        path = QtGui.QPainterPath()
        path.moveTo(s * 0.32, s * 0.18)
        path.lineTo(s * 0.82, s * 0.50)
        path.lineTo(s * 0.32, s * 0.82)
        path.closeSubpath()
        p.setBrush(QtGui.QColor(color))
        p.drawPath(path)
    elif kind == "stop":
        p.setBrush(QtGui.QColor(color))
        p.drawRoundedRect(QtCore.QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44), 2, 2)
    elif kind == "info":
        p.drawEllipse(QtCore.QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        p.drawLine(QtCore.QPointF(s * 0.50, s * 0.46), QtCore.QPointF(s * 0.50, s * 0.70))
        p.setBrush(QtGui.QColor(color))
        p.drawEllipse(QtCore.QRectF(s * 0.46, s * 0.30, s * 0.08, s * 0.08))
    elif kind == "clear":
        p.drawLine(QtCore.QPointF(s * 0.26, s * 0.26), QtCore.QPointF(s * 0.74, s * 0.74))
        p.drawLine(QtCore.QPointF(s * 0.74, s * 0.26), QtCore.QPointF(s * 0.26, s * 0.74))
    elif kind == "sliders":
        for y, knob in ((0.28, 0.62), (0.50, 0.36), (0.72, 0.56)):
            p.drawLine(QtCore.QPointF(s * 0.18, s * y), QtCore.QPointF(s * 0.82, s * y))
            p.setBrush(QtGui.QColor(color))
            p.drawEllipse(
                QtCore.QPointF(s * knob, s * y), s * 0.09, s * 0.09
            )
            p.setBrush(QtCore.Qt.NoBrush)
    elif kind == "profiles":
        p.drawRoundedRect(QtCore.QRectF(s * 0.30, s * 0.16, s * 0.54, s * 0.52), 2, 2)
        p.drawRoundedRect(QtCore.QRectF(s * 0.20, s * 0.28, s * 0.54, s * 0.52), 2, 2)
        p.drawRoundedRect(QtCore.QRectF(s * 0.10, s * 0.40, s * 0.54, s * 0.42), 2, 2)
    elif kind == "globe":
        # Circle plus one meridian and the equator stay readable at 14 px; extra
        # latitude arcs turn into mush at that size.
        p.drawEllipse(QtCore.QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72))
        p.drawEllipse(QtCore.QRectF(s * 0.30, s * 0.14, s * 0.40, s * 0.72))
        p.drawLine(QtCore.QPointF(s * 0.15, s * 0.50), QtCore.QPointF(s * 0.85, s * 0.50))
    elif kind == "check":
        # Same stroked checkmark as the checkbox indicator, drawn on the action
        # canvas so the active language row keeps the icon column of the globe.
        path = QtGui.QPainterPath()
        path.moveTo(QtCore.QPointF(s * 0.24, s * 0.52))
        path.lineTo(QtCore.QPointF(s * 0.43, s * 0.71))
        path.lineTo(QtCore.QPointF(s * 0.78, s * 0.30))
        p.drawPath(path)

    p.end()
    pixmap.setDevicePixelRatio(2.0)
    return QtGui.QIcon(pixmap)


def app_icon(size: int = 64) -> QtGui.QIcon:
    """Brand mark: navy board tile with an azure OCR grid.

    Every measurement is a float derived from ``size`` so the grid stays
    pixel-symmetric: the same padding and gap sit on the left/right and
    top/bottom edges, and all nine cells share one width and height.
    """
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor("#0a1224"))
    painter.drawRoundedRect(
        QtCore.QRectF(2.0, 2.0, size - 4.0, size - 4.0), size * 0.22, size * 0.22
    )
    pad = round(size * 0.156)
    gap = max(1, round(size * 0.0625))
    cell = (size - 2 * pad - 2 * gap) / 3.0
    for row in range(3):
        for column in range(3):
            painter.setBrush(
                QtGui.QColor("#0b6ee8" if (row + column) % 2 == 0 else "#095ec5")
            )
            painter.drawRoundedRect(
                QtCore.QRectF(
                    pad + column * (cell + gap),
                    pad + row * (cell + gap),
                    cell,
                    cell,
                ),
                max(1.0, cell * 0.18),
                max(1.0, cell * 0.18),
            )
    painter.end()
    return QtGui.QIcon(pixmap)
