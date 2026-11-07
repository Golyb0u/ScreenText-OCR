"""Reusable widgets for the ScreenText OCR shell."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from ..i18n import tr
from ..imaging import numpy_to_pixmap
from . import theme
from .card_paint import paint_card

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


def repolish(widget: QtWidgets.QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class PopupThemeFilter(QtCore.QObject):
    """Keep QComboBox popup containers on the active palette.

    The popup container is a hidden Qt class that is not covered by the main
    stylesheet, so without this it paints the platform's white window colour
    around the dark rounded list. The filter restyles it every time it is shown.
    """

    def __init__(self, app: QtWidgets.QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._variant = "dark"
        self._radius = int(theme.DEFAULT_TOKENS["radius"])
        self._accent: Optional[str] = None
        app.installEventFilter(self)

    def set_theme(
        self, variant: str, radius: int, accent: Optional[str] = None
    ) -> None:
        self._variant = "light" if variant == "light" else "dark"
        self._radius = int(radius)
        self._accent = accent
        sheet = theme.popup_stylesheet(self._variant, self._radius, self._accent)
        for widget in self._app.allWidgets():
            if widget.metaObject().className() == "QComboBoxPrivateContainer":
                widget.setStyleSheet(sheet)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            event.type() == QtCore.QEvent.Show
            and obj.metaObject().className() == "QComboBoxPrivateContainer"
        ):
            popup = obj
            popup.setStyleSheet(
                theme.popup_stylesheet(self._variant, self._radius, self._accent)
            )
        return False


class Card(QtWidgets.QFrame):
    """Painted floating surface with a title, optional hint and a body layout.

    The card owns its own background: QSS keeps the frame transparent, and
    :func:`card_paint.paint_card` draws the gradient, hairline and ambient
    shadow. Content margins therefore include the 10 px inset that the painted
    shadow occupies inside the widget bounds.
    """

    def __init__(
        self,
        title: str = "",
        hint: str = "",
        parent: Optional[QtWidgets.QWidget] = None,
        tone: str = "",
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        if tone:
            self.setProperty("tone", tone)
        # The QSS surface is transparent; letting Qt also fill the styled
        # background would paint a flat rectangle over the gradient.
        self.setAttribute(QtCore.Qt.WA_StyledBackground, False)
        self._root = QtWidgets.QVBoxLayout(self)
        self._root.setContentsMargins(20, 17, 20, 19)
        self._root.setSpacing(10)

        self.header = QtWidgets.QHBoxLayout()
        self.header.setContentsMargins(0, 0, 0, 0)
        self.header.setSpacing(8)
        # The header layout has to be attached to the card before widgets are
        # put into it: a parentless widget that is shown becomes a floating
        # top-level window, and a detached layout does not reparent on
        # addWidget. Without this ordering the card labels flashed a dozen
        # empty windows on screen while the UI was built.
        self._root.addLayout(self.header)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setProperty("role", "cardTitle")
        self.header.addWidget(self.title_label)
        self.title_label.setVisible(bool(title))
        self.header.addStretch(1)

        self.hint_label = QtWidgets.QLabel(hint)
        self.hint_label.setProperty("role", "cardHint")
        self.hint_label.setWordWrap(True)
        self._root.addWidget(self.hint_label)
        self.hint_label.setVisible(bool(hint))

        self.body = QtWidgets.QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(9)
        self._root.addLayout(self.body)

    def add(self, widget: QtWidgets.QWidget, stretch: int = 0) -> QtWidgets.QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout: QtWidgets.QLayout) -> QtWidgets.QLayout:
        self.body.addLayout(layout)
        return layout

    def add_separator(self) -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setProperty("role", "separator")
        line.setFixedHeight(1)
        self.body.addWidget(line)
        return line

    def badge(self, text: str, tone: str = "accent") -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setProperty("role", "chip")
        label.setProperty("tone", tone)
        self.header.addWidget(label)
        return label

    # ------------------------------------------------------------- painting
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802 - Qt naming
        if not paint_card(self, event, self.property("tone") or "card"):
            # Native/system mode: the platform frame paints itself.
            super().paintEvent(event)

    def refresh_theme(self) -> None:
        """Repaint with the tokens published by the current theme pass."""
        self.update()


class FormRow(QtWidgets.QWidget):
    """Label on the left, control on the right, consistent across pages."""

    def __init__(
        self,
        title: str,
        control: QtWidgets.QWidget,
        parent: Optional[QtWidgets.QWidget] = None,
        label_width: int = 132,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.label = QtWidgets.QLabel(title)
        self.label.setMinimumWidth(label_width)
        self.label.setWordWrap(True)
        self.control = control
        layout.addWidget(self.label)
        layout.addWidget(control, 1)


class HintLabel(QtWidgets.QLabel):
    def __init__(self, text: str = "", parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "hint")
        self.setWordWrap(True)


class ImagePreview(QtWidgets.QLabel):
    """Scales a numpy image to the available label area and accepts drops."""

    fileDropped = QtCore.pyqtSignal(str)

    def __init__(
        self,
        placeholder: str = "",
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        placeholder = placeholder or tr("Нет изображения\nПеретащите файл сюда")
        super().__init__(placeholder, parent)
        self.setObjectName("previewLabel")
        self.setProperty("hasImage", False)
        self.setAlignment(QtCore.Qt.AlignCenter)
        # Enough to stay usable in a half-width cell; the real height in the
        # normal layout is far larger, so this only relaxes the floor.
        self.setMinimumHeight(160)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setWordWrap(True)
        self.setAcceptDrops(True)
        self._pixmap: Optional[QtGui.QPixmap] = None
        self._placeholder = placeholder

    def set_numpy_image(self, image) -> None:
        self._pixmap = numpy_to_pixmap(image)
        self.setProperty("hasImage", True)
        repolish(self)
        self.setText("")
        self._update_scaled_pixmap()

    def clear_preview(self, text: Optional[str] = None) -> None:
        self._pixmap = None
        self.setProperty("hasImage", False)
        repolish(self)
        self.clear()
        self.setWordWrap(True)
        self.setText(text or self._placeholder)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        available = self.contentsRect().size() - QtCore.QSize(20, 20)
        if available.width() <= 0 or available.height() <= 0:
            return
        self.setPixmap(
            self._pixmap.scaled(
                available, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
        )

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if Path(path).suffix.lower() in IMAGE_SUFFIXES:
                    self.fileDropped.emit(path)
                    event.acceptProposedAction()
                    return
        event.ignore()


class SoftToolTip(QtWidgets.QFrame):
    """Frameless tooltip with the same glass language as the cards."""

    def __init__(self) -> None:
        super().__init__(
            None,
            QtCore.Qt.ToolTip
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setObjectName("SoftToolTip")
        self.setStyleSheet("QFrame#SoftToolTip { background: transparent; border: none; }")

        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(26)
        self.shadow.setOffset(0, 9)
        self.shadow.setColor(QtGui.QColor(0, 0, 0, 120))

        self.animation = QtCore.QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self.animation.finished.connect(self._handle_animation_finished)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QtWidgets.QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(QtCore.Qt.RichText)
        self.label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.label.setGraphicsEffect(self.shadow)
        self.set_palette_colors("#0f1722", "#eef2ff", "rgba(148, 163, 184, 72)")
        layout.addWidget(self.label)

    def set_palette_colors(self, background: str, text: str, border: str) -> None:
        self.label.setStyleSheet(
            "QLabel {"
            f"background: {background}; color: {text};"
            f"border: 1px solid {border}; border-radius: 12px;"
            "padding: 13px 15px 14px 15px; font-size: 12px;"
            "}"
        )

    def show_tooltip(self, anchor_widget: QtWidgets.QWidget, html: str) -> None:
        width = 330
        self.label.setText(html)
        self.label.setFixedWidth(width)
        self.label.adjustSize()
        height = max(96, self.label.sizeHint().height() + 2)
        self.resize(width, height)

        anchor_global = anchor_widget.mapToGlobal(QtCore.QPoint(0, 0))
        pos = QtCore.QPoint(
            anchor_global.x() + anchor_widget.width() + 12, anchor_global.y() + 6
        )
        screen = QtWidgets.QApplication.screenAt(pos) or QtWidgets.QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            if pos.x() + self.width() > available.right() - 8:
                pos.setX(anchor_global.x() - self.width() - 12)
            x = min(max(pos.x(), available.left() + 8), available.right() - self.width() - 8)
            y = min(max(pos.y(), available.top() + 8), available.bottom() - self.height() - 8)
            pos = QtCore.QPoint(max(x, available.left() + 8), y)
        self.move(pos)
        self.show()
        self.raise_()
        self.animation.stop()
        self.opacity_effect.setOpacity(0.0)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(0.88)
        self.animation.start()

    def hide_tooltip(self) -> None:
        if not self.isVisible():
            return
        self.animation.stop()
        self.animation.setStartValue(self.opacity_effect.opacity())
        self.animation.setEndValue(0.0)
        self.animation.start()

    def _handle_animation_finished(self) -> None:
        if self.opacity_effect.opacity() <= 0.01:
            self.hide()


class NavTabBar(QtWidgets.QTabBar):
    """Compact, icon-less tab bar that measures its plain bold labels.

    Qt's stylesheet-driven tab size hint ignores the bold font weight used for
    painted tab labels, so long labels such as "Обработка" were clipped at both
    edges. Measuring with the same bold metrics fixes the width instead of
    relying on the default hint. The row has to fit all four translated
    captions without spilling into the overflow scroll buttons, so the paddings
    stay tight and the icons (when present) only add their own allowance.

    The bar also spans the settings panel: leftover width is handed out in equal
    slices on top of each label's own width. QTabBar's own ``expanding`` layout
    would instead equalise every tab, which clips the widest caption as soon as
    the user raises the font size in the appearance inspector.
    """

    H_PADDING = 6
    V_PADDING = 7
    ICON_GAP = 4
    SAFETY = 2
    MARGIN_H = 6  # QTabBar::tab margin-right in the sheet; it insets the label
    MIN_WIDTH = 0
    MIN_HEIGHT = 32

    def _measure(self) -> tuple[QtGui.QFontMetrics, list[int], int]:
        """Bold metrics, the natural width of every tab and their sum."""
        font = QtGui.QFont(self.font())
        font.setWeight(QtGui.QFont.DemiBold)
        metrics = QtGui.QFontMetrics(font)
        widths: list[int] = []
        for index in range(self.count()):
            text = self.tabText(index).replace("&", "")
            width = (
                metrics.horizontalAdvance(text)
                + self.H_PADDING * 2
                + self.MARGIN_H
                + self.SAFETY
            )
            if not self.tabIcon(index).isNull():
                width += self.iconSize().width() + self.ICON_GAP
            widths.append(max(self.MIN_WIDTH, width))
        return metrics, widths, sum(widths)

    def _extra_share(self, index: int) -> int:
        """Equal slice of the unused row width, zero when the row is full.

        The remainder of the integer division goes to the leading tabs so the
        four rects add up to the panel width exactly and no dead sliver is left
        at the right edge.
        """
        count = self.count()
        if count <= 0:
            return 0
        parent = self.parentWidget()
        if parent is None or parent.width() <= 0:
            return 0
        _metrics, _widths, natural = self._measure()
        extra = parent.width() - natural
        if extra <= 0:
            return 0
        return extra // count + (1 if index < extra % count else 0)

    def tabSizeHint(self, index: int) -> QtCore.QSize:
        base = super().tabSizeHint(index)
        metrics, widths, _natural = self._measure()
        width = widths[index] + self._extra_share(index)
        height = max(self.MIN_HEIGHT, metrics.height() + self.V_PADDING * 2 + 4)
        return QtCore.QSize(width, max(base.height(), height))

    def sizeHint(self) -> QtCore.QSize:
        """Span the settings panel instead of hugging the labels.

        QTabWidget gives the bar its own size hint, which after the icons were
        dropped left the four pills huddled in the left third of a much wider
        panel. Asking for the parent width makes the row read as one segmented
        control; the natural hint stays the floor, so a narrow window elides
        instead of squeezing the pills below their labels.
        """
        hint = super().sizeHint()
        parent = self.parentWidget()
        if parent is not None and parent.width() > 0:
            hint.setWidth(max(hint.width(), parent.width()))
        return hint


class PageScroll(QtWidgets.QScrollArea):
    """Scrollable settings page with cards stacked inside."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(12)
        self.setWidget(self.content)

    def add(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        self.content_layout.addWidget(widget)
        return widget

    def finish(self) -> None:
        self.content_layout.addStretch(1)


def button_row(*buttons: QtWidgets.QWidget) -> QtWidgets.QWidget:
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for button in buttons:
        layout.addWidget(button)
    return widget


class ResponsiveButtonRow(QtWidgets.QWidget):
    """Row of buttons that folds into two columns, then one, as it narrows.

    The workspace grid can put the OCR card into a half-width slot, where a
    three-button row used to crush the captions down to their icons.  This
    container keeps the same buttons (and therefore their icons, tooltips and
    clicks) and re-flows them:

    * wide: one row, equal columns;
    * medium: two columns, an odd last button spanning both columns;
    * narrow: a single column.

    The width that decides the mode is the widget's own width, so the layout
    must be allowed to shrink below the width the current arrangement needs;
    otherwise the parent would never hand it a narrow size and the fold could
    not happen.  ``QLayout.SetNoConstraint`` plus the narrow
    :meth:`minimumSizeHint` provide that room.  The height, on the other hand,
    must follow the *current* arrangement: a three-row minimum would keep two
    empty rows reserved even while the buttons sit in one row.
    """

    #: Below this share of the two-column width the buttons stack in one column.
    TWO_COLUMN_FLOOR = 0.6

    def __init__(
        self,
        *buttons: QtWidgets.QWidget,
        spacing: int = 8,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._buttons = [button for button in buttons]
        self._spacing = max(0, int(spacing))
        self._mode = ""
        self._reflow_pending = False

        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self._spacing)
        self._layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

        policy = self.sizePolicy()
        policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Preferred)
        policy.setVerticalPolicy(QtWidgets.QSizePolicy.Preferred)
        self.setSizePolicy(policy)

        # A child timer dies with the widget.  ``QTimer.singleShot(0, ...)``
        # would still hold a bound method if the row is destroyed before the
        # event loop runs, and PyQt aborts the process when that call lands on
        # a deleted C++ object.
        self._reflow_timer = QtCore.QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.timeout.connect(self._reflow)
        self._apply_mode("row")

    # --------------------------------------------------------------- public
    def buttons(self) -> list[QtWidgets.QWidget]:
        """The buttons this row manages, in their original order."""
        return list(self._buttons)

    def rows(self) -> int:
        """How many button rows the current arrangement uses."""
        count = len(self._buttons)
        if self._mode == "two":
            return (count + 1) // 2
        if self._mode == "column":
            return count
        return 1

    # ---------------------------------------------------------------- hints
    def sizeHint(self) -> QtCore.QSize:
        """The single-row arrangement: every button side by side."""
        hints = [button.sizeHint() for button in self._buttons]
        if not hints:
            return QtCore.QSize(0, 0)
        width = sum(hint.width() for hint in hints)
        width += self._spacing * (len(hints) - 1)
        height = max(hint.height() for hint in hints)
        return QtCore.QSize(width, height)

    def minimumSizeHint(self) -> QtCore.QSize:
        """The narrowest arrangement: one column of buttons.

        The width is the widest single button, which lets the parent squeeze
        the row (and so trigger a fold).  The height follows the mode that is
        currently applied, because reserving a three-row minimum in the wide
        layout would leave two empty rows under the buttons.
        """
        hints = [button.sizeHint() for button in self._buttons]
        if not hints:
            return QtCore.QSize(0, 0)
        width = max(hint.width() for hint in hints)
        height = self._mode_height(self._mode or "row")
        return QtCore.QSize(width, height)

    # --------------------------------------------------------------- layout
    def _mode_height(self, mode: str) -> int:
        hints = [button.sizeHint().height() for button in self._buttons]
        if not hints:
            return 0
        row_height = max(hints)
        if mode == "row":
            rows = 1
        elif mode == "two":
            rows = (len(hints) + 1) // 2
        else:
            rows = len(hints)
        return rows * row_height + max(0, rows - 1) * self._spacing

    def _two_column_width(self) -> int:
        """Natural width of the two-column arrangement."""
        hints = [button.sizeHint().width() for button in self._buttons]
        width = 0
        index = 0
        while index < len(hints):
            if index + 1 < len(hints):
                width = max(width, hints[index] + self._spacing + hints[index + 1])
                index += 2
            else:
                width = max(width, hints[index])
                index += 1
        return width

    def _mode_for_width(self, width: int) -> str:
        if len(self._buttons) <= 1:
            return "row"
        one_row = self.sizeHint().width()
        if width >= one_row:
            return "row"
        if len(self._buttons) == 2:
            return "column"
        two_columns = self._two_column_width()
        floor = int(two_columns * self.TWO_COLUMN_FLOOR)
        if width >= max(1, floor):
            return "two"
        return "column"

    def _apply_mode(self, mode: str) -> None:
        """Re-place the existing buttons for ``mode`` (never recreates them)."""
        if (
            mode == self._mode
            and self._layout.count() == len(self._buttons)
            and self._layout.count() > 0
        ):
            self.updateGeometry()
            return

        for column in range(len(self._buttons) + 1):
            self._layout.setColumnStretch(column, 0)
        for button in self._buttons:
            self._layout.removeWidget(button)

        if mode == "row":
            for index, button in enumerate(self._buttons):
                self._layout.addWidget(button, 0, index)
                self._layout.setColumnStretch(index, 1)
        elif mode == "two" and len(self._buttons) > 2:
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 1)
            row = 0
            index = 0
            while index < len(self._buttons):
                if index + 1 < len(self._buttons):
                    self._layout.addWidget(self._buttons[index], row, 0)
                    self._layout.addWidget(self._buttons[index + 1], row, 1)
                    index += 2
                else:
                    self._layout.addWidget(self._buttons[index], row, 0, 1, 2)
                    index += 1
                row += 1
        else:
            for index, button in enumerate(self._buttons):
                self._layout.addWidget(button, index, 0)
            self._layout.setColumnStretch(0, 1)

        self._mode = mode
        self._layout.invalidate()
        self._layout.activate()
        self.updateGeometry()

    def _schedule_reflow(self) -> None:
        if self._reflow_pending:
            return
        self._reflow_pending = True
        self._reflow_timer.start(0)

    def _reflow(self) -> None:
        """Pick the arrangement that fits the current width."""
        self._reflow_pending = False
        try:
            self._apply_mode(self._mode_for_width(self.width()))
        except RuntimeError:
            # The row (and its buttons) was destroyed before the timer ran.
            pass

    # ---------------------------------------------------------------- events
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._schedule_reflow()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        # Re-flow before the first paint so the buttons are never displayed in
        # the previous width's arrangement.
        self._reflow()

