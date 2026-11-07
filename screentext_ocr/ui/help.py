"""Live help panel and rich tooltip renderer."""

from __future__ import annotations

import html
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from ..i18n import tr
from . import theme
from .card_reorder import CardReorder
from .widgets import Card, SoftToolTip


def rich_tooltip(
    title: str,
    description: str,
    best_for: str = "",
    tips: str = "",
    caution: str = "",
    values: str = "",
    dark: bool = True,
    include_title: bool = True,
    palette: Optional[dict[str, str]] = None,
    scale: float = 1.0,
    body_px: Optional[float] = None,
) -> str:
    if palette is None:
        tones = theme.tooltip_palette("dark" if dark else "light")
        palette = {
            "title": tones["strong"],
            "description": tones["text"],
            "label": tones["muted"],
            "text": tones["text"],
        }

    # Identity requests must keep the historical markup byte-for-byte: the
    # floating tooltip renders the very same HTML and must not shrink.
    if scale == 1.0 and body_px is None:
        title_px = "15px"
        label_px = "11px"
        body_rule = ""
        card_rule = ".card { line-height: 1.45; }"
        title_margin = "0 0 7px 0"
        description_margin = "0 0 9px 0"
        section_rule = ".section { margin-top: 11px; }"
        label_margin = "3px"
    else:
        def _px(value: float) -> str:
            return f"{max(8, int(round(value * scale)))}px"

        def _gap(value: float, floor: int) -> str:
            # The vertical rhythm has to shrink with the text, otherwise the
            # fixed gaps eat most of a short rail even at the smallest font.
            return f"{max(floor, int(round(value * scale)))}px"

        title_px = _px(15)
        label_px = _px(11)
        body_rule = f" font-size: {_px(body_px)};" if body_px else ""
        line_height = max(1.24, 1.45 * scale)
        card_rule = f".card {{ line-height: {line_height:.2f}; }}"
        title_margin = f"0 0 {_gap(7, 4)} 0"
        description_margin = f"0 0 {_gap(9, 5)} 0"
        section_rule = f".section {{ margin-top: {_gap(11, 6)}; }}"
        label_margin = _gap(3, 2)

    def text_block(text: str) -> str:
        return html.escape(text).replace("\n", "<br>")

    def section(label: str, text: str) -> str:
        if not text:
            return ""
        return (
            "<div class='section'>"
            f"<div class='section-label'>{html.escape(label)}</div>"
            f"<div class='section-text'>{text_block(text)}</div>"
            "</div>"
        )

    return (
        "<html><head><meta charset='utf-8'><style>"
        "body { margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif;"
        f"{body_rule} color: {palette['text']}; }}"
        f"{card_rule}"
        f".title {{ font-size: {title_px}; font-weight: 700; margin: {title_margin}; color: {palette['title']}; }}"
        f".description {{ margin: {description_margin}; color: {palette['description']}; }}"
        f"{section_rule}"
        f".section-label {{ margin-bottom: {label_margin}; font-size: {label_px}; font-weight: 700; color: {palette['label']};"
        " text-transform: uppercase; letter-spacing: 0.06em; }"
        f".section-text {{ color: {palette['text']}; }}"
        "</style></head><body><div class='card'>"
        + (f"<div class='title'>{html.escape(title)}</div>" if include_title else "")
        + f"<div class='description'>{text_block(description)}</div>"
        +
        f"{section(tr('Когда использовать'), best_for)}"
        f"{section(tr('Значения и варианты'), values)}"
        f"{section(tr('Практика'), tips)}"
        f"{section(tr('Важно'), caution)}"
        "</div></body></html>"
    )


class HelpPanel(QtWidgets.QFrame):
    """Right rail: live contextual help, diagnostics and small metrics."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "sidePanel")
        self.setMinimumWidth(300)
        self.setMaximumWidth(380)
        self._variant = "dark"
        self._payloads: dict[QtWidgets.QWidget, dict] = {}
        self._current: Optional[dict] = None
        # Autofit state: the last applied text scale, the (content, size) key it
        # was computed for, and a re-entrancy guard.
        self._fit_scale = 1.0
        self._fit_key: Optional[tuple] = None
        self._content_serial = 0
        self._fit_pending = False
        self._fitting = False
        self.soft_tooltip = SoftToolTip()
        self._apply_tooltip_palette("dark")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        help_card = Card(tr("Справка"), tr("Наведи курсор на параметр - здесь появится живое описание."))
        help_card.setProperty("cardId", "help")
        self.help_card = help_card
        self.help_title = QtWidgets.QLabel(tr("Быстрая справка"))

        self.help_title.setProperty("role", "title")
        self.help_title.setWordWrap(True)
        self.help_browser = QtWidgets.QTextBrowser()
        self.help_browser.setObjectName("helpBrowser")
        self.help_browser.setOpenExternalLinks(False)
        self.help_browser.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.help_browser.setReadOnly(True)
        self.help_browser.document().setDocumentMargin(0)
        self.help_browser.setMinimumHeight(250)
        self.help_browser.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.help_browser.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.help_browser.installEventFilter(self)
        self.installEventFilter(self)
        help_card.add(self.help_title)
        help_card.add(self.help_browser, 1)
        root.addWidget(help_card, 1)

        diag_card = Card(tr("Диагностика"), tr("Быстрая проверка путей и рискованных значений."))
        diag_card.setProperty("cardId", "diagnostics")
        self.diag_card = diag_card
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(QtCore.Qt.RichText)
        self.summary.setProperty("role", "hint")
        diag_card.add(self.summary)
        root.addWidget(diag_card)

        stats_card = Card(tr("Текущий кадр"))
        stats_card.setProperty("cardId", "stats")
        self.stats_card = stats_card
        self._stats = {
            "source": "-",
            "processed": "-",
            "ocr": "-",
            "events": "0",
        }
        self.stats_label = QtWidgets.QLabel()
        self.stats_label.setProperty("role", "hint")
        self.stats_label.setWordWrap(True)
        stats_card.add(self.stats_label)
        root.addWidget(stats_card)
        self._refresh_stats()

        # The rail is a card stack like the settings pages: the same gesture,
        # persistence and stretch bookkeeping apply.  Created after all three
        # cards exist so registration sees the real stretch factors.
        self.card_order = CardReorder.for_layout(root, self, "help")

        self.set_default_help()

    # ================================================================== help
    def register(
        self,
        widget: QtWidgets.QWidget,
        title: str,
        description: str,
        best_for: str = "",
        tips: str = "",
        caution: str = "",
        values: str = "",
    ) -> None:
        payload = {
            "title": title,
            "description": description,
            "best_for": best_for,
            "tips": tips,
            "caution": caution,
            "values": values,
        }
        self._payloads[widget] = payload
        widget.setToolTip("")
        widget.installEventFilter(self)

    def update_payload(self, widget: QtWidgets.QWidget, **changes: str) -> None:
        payload = self._payloads.get(widget)
        if payload is None:
            return
        payload.update(changes)
        # A queued payload change can arrive after the watched widget's C++
        # object was destroyed; touching it would raise into the caller.
        try:
            if self._current is payload and (
                QtWidgets.QApplication.focusWidget() is widget or widget.underMouse()
            ):
                self.set_help_content(payload)
                self._ensure_tooltip().show_tooltip(widget, self._html(payload))
        except RuntimeError:
            return

    def set_help_content(self, payload: dict) -> None:
        self._current = payload
        self._content_serial += 1
        self.help_title.setText(tr(payload["title"]))
        self._render_help()
        self._schedule_fit()

    def set_default_help(self) -> None:
        self.set_help_content(
            {
                "title": "Быстрая справка",
                "description": "Наведи курсор на параметр или сфокусируй поле - здесь появится живое описание настройки.",
                "best_for": "Начни с пресета, затем подгони PSM, бинаризацию и whitelist под конкретный кадр.",
                "tips": "Сначала зафиксируй кадр, затем сравнивай настройки через F5.",
                "caution": "",
                "values": "",
            }
        )

    # ================================================================= fitting
    FIT_MIN_SCALE = 0.5
    FIT_STEP = 0.05
    # Sub-pixel layout noise: a document that overflows by a pixel or two does
    # not clip a line, so it must not raise the emergency scrollbar.
    FIT_TOLERANCE_PX = 2

    def _fit_scales(self) -> list[float]:
        """Candidate scales from 1.0 down to ``FIT_MIN_SCALE`` inclusive."""
        steps = int(round((1.0 - self.FIT_MIN_SCALE) / self.FIT_STEP))
        return [round(1.0 - index * self.FIT_STEP, 2) for index in range(steps + 1)]

    def _body_px(self) -> float:
        """Resolve the browser's inherited body font size in device pixels.

        The QSS sets the help browser font in points, so the rich-text body has
        no explicit pixel size of its own. Scaling from the actual font keeps
        the fitted text uniform with the rest of the panel.
        """
        info = QtGui.QFontInfo(self.help_browser.font())
        size = float(info.pixelSize())
        if size <= 0:
            size = info.pointSizeF() * 96.0 / 72.0
        if size <= 0:
            # Some styles leave ``QWidget.font()`` unresolved; the document
            # default font is the one the text is actually laid out with.
            info = QtGui.QFontInfo(self.help_browser.document().defaultFont())
            size = float(info.pixelSize())
            if size <= 0:
                size = info.pointSizeF() * 96.0 / 72.0
        if size <= 0:
            size = 12.0
        return size

    def _scaled_html(self, scale: float) -> str:
        if self._current is None:
            return ""
        return self._html(self._current, scale=scale, body_px=self._body_px())

    def _render_help(self) -> None:
        """Paint the current payload with the last applied scale (cheap)."""
        if self._current is None:
            return
        self.help_browser.setHtml(self._scaled_html(self._fit_scale))

    def _schedule_fit(self) -> None:
        """Queue a refit outside the current layout pass."""
        if self._fit_pending:
            return
        self._fit_pending = True
        QtCore.QTimer.singleShot(0, self._run_fit)

    def _run_fit(self) -> None:
        self._fit_pending = False
        if self._current is None or self._fitting:
            return
        try:
            browser = self.help_browser
            # Geometry comes from the widget, never from the viewport: when an
            # emergency scrollbar is still visible the viewport is a bar
            # narrower than the area the fit is about to use.
            frame = 2 * browser.frameWidth()
            width = browser.width() - frame
            height = browser.height() - frame
            if width <= 0 or height <= 0:
                # Not laid out yet; Show/Resize will queue another attempt.
                return
            if (self._content_serial, browser.width(), browser.height()) == self._fit_key:
                return
            self._fit_html(self._current, width, height)
            self._fit_key = (self._content_serial, browser.width(), browser.height())
        except RuntimeError:
            # Shutdown can delete the panel while a queued fit is in flight.
            return

    def _fit_html(self, payload: dict, width: int, height: int) -> None:
        """Shrink the document until it fits, or fall back to a scrollbar."""
        browser = self.help_browser
        self._fitting = True
        try:
            # Measuring must not be perturbed by a bar that steals width.
            browser.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            browser.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            frame = 2 * browser.frameWidth()
            available_w = browser.width() - frame
            available_h = browser.height() - frame
            if available_w <= 0 or available_h <= 0:
                return
            # The widget itself is the upper bound; an explicit caller may ask
            # for a tighter box (tests, screenshots), but a width read while an
            # emergency bar was visible must not survive.
            width = min(width if width > 0 else available_w, available_w)
            height = min(height if height > 0 else available_h, available_h)
            body_px = self._body_px()
            fits = False
            scale = 1.0
            for candidate in self._fit_scales():
                scale = candidate
                browser.setHtml(
                    self._html(payload, scale=candidate, body_px=body_px)
                )
                document = browser.document()
                document.setTextWidth(width)
                if document.size().height() <= height + self.FIT_TOLERANCE_PX:
                    fits = True
                    break
            self._fit_scale = scale
            if fits:
                browser.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
                browser.document().setTextWidth(width)
            else:
                # Even the smallest legible size overflows: scrolling is the
                # only way to reach the rest of the text.
                browser.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
                reserved = browser.verticalScrollBar().sizeHint().width()
                browser.document().setTextWidth(max(80, width - reserved))
        finally:
            self._fitting = False

    def _html(
        self,
        payload: dict,
        *,
        scale: float = 1.0,
        body_px: Optional[float] = None,
    ) -> str:
        localized = {
            key: tr(value) if isinstance(value, str) else value
            for key, value in payload.items()
        }
        tones = theme.panel_palette(self._variant)
        return rich_tooltip(
            localized["title"],
            localized["description"],
            localized["best_for"],
            localized["tips"],
            localized["caution"],
            localized["values"],
            dark=self._variant != "light",
            include_title=False,
            palette={
                "title": tones["accent"],
                "description": tones["text"],
                "label": tones["muted"],
                "text": tones["text"],
            },
            scale=scale,
            body_px=body_px,
        )

    def _apply_tooltip_palette(self, variant: str) -> None:
        tones = theme.tooltip_palette(variant)
        self._ensure_tooltip().set_palette_colors(
            tones["background"], tones["text"], tones["border"]
        )

    # ================================================================ tooltip
    def _tooltip_alive(self) -> bool:
        """Whether the top-level tooltip still owns a live C++ object.

        The tooltip is deliberately parentless so it can float over the whole
        window. That also means the C++ side can be destroyed during shutdown or
        a language restart while a queued Enter/Leave event is still on its way;
        touching the wrapper then raises ``RuntimeError`` into the event loop.
        """
        try:
            self.soft_tooltip.objectName()
        except RuntimeError:
            return False
        return True

    def _ensure_tooltip(self) -> SoftToolTip:
        """Return a usable tooltip, recreating the window if Qt destroyed it."""
        if not self._tooltip_alive():
            self.soft_tooltip = SoftToolTip()
            tones = theme.tooltip_palette(self._variant)
            self.soft_tooltip.set_palette_colors(
                tones["background"], tones["text"], tones["border"]
            )
        return self.soft_tooltip

    def hide_tooltip(self) -> None:
        """Hide the floating tooltip; a dead wrapper is simply ignored."""
        if not self._tooltip_alive():
            return
        self.soft_tooltip.hide_tooltip()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        # Palette *and* the QSS font may have changed, so both the markup and
        # its fitted scale are stale.
        self._content_serial += 1
        self._render_help()
        self._schedule_fit()
        # Re-ink only a tooltip that already exists: a palette change must not
        # pop one. Its HTML was rendered with the previous variant's inks, so
        # hiding it is cleaner than showing stale colours; it returns on the
        # next Enter. ``_ensure_tooltip`` is deliberately not used here.
        if self._tooltip_alive():
            tones = theme.tooltip_palette(self._variant)
            self.soft_tooltip.set_palette_colors(
                tones["background"], tones["text"], tones["border"]
            )
            self.hide_tooltip()

    # ============================================================= diagnostics
    def set_diagnostics(self, html_text: str) -> None:
        self.summary.setText(html_text)

    def set_stat(self, key: str, value: str) -> None:
        if key in self._stats:
            self._stats[key] = value
            self._refresh_stats()

    def _refresh_stats(self) -> None:
        self.stats_label.setText(
            tr(
                "Исходник: {source}   ·   Обработка: {processed}\n"
                "OCR: {ocr}   ·   Событий: {events}",
                source=self._stats["source"],
                processed=self._stats["processed"],
                ocr=self._stats["ocr"],
                events=self._stats["events"],
            )
        )

    # ================================================================== events
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        # A queued Enter/Leave can arrive after the C++ tooltip (or the watched
        # widget) was destroyed during shutdown or a language restart. Such an
        # event must never raise into the Qt event loop.
        try:
            # The browser and the panel itself are only watched for geometry:
            # every other event keeps its normal path to the payload branch.
            if watched is self.help_browser or watched is self:
                if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
                    self._schedule_fit()
                return super().eventFilter(watched, event)
            payload = self._payloads.get(watched)
            if payload is not None:
                if event.type() in (QtCore.QEvent.Enter, QtCore.QEvent.FocusIn):
                    self.set_help_content(payload)
                    self._ensure_tooltip().show_tooltip(watched, self._html(payload))
                elif event.type() in (
                    QtCore.QEvent.Leave,
                    QtCore.QEvent.FocusOut,
                    QtCore.QEvent.Hide,
                ):
                    self.hide_tooltip()
            return super().eventFilter(watched, event)
        except RuntimeError:
            return False
