"""Drag-to-reorder for the fixed 2+1 grid of the workspace preview cards.

:class:`preview_panel.PreviewPanel` keeps three cards in a ``QGridLayout``:
two half-width slots on the top row and one full-width slot below.  This
controller lets the user drag a card onto another card's slot; the two cards
exchange slots and are re-laid out, while the grid geometry itself (column and
row stretches, spans) never changes.

The gesture is a press-then-move sequence like :mod:`card_reorder`, but a grid
slot is a target instead of a gap in a vertical stack, so the dragged card is
*not* removed from the layout: hiding it would collapse its cell and make the
remaining cards jump.  It stays in place under a 0.35 opacity effect while a
ghost label follows the cursor and a :class:`card_reorder.DropPlaceholder`
marks the slot under it.
"""

from __future__ import annotations

import weakref
from typing import Optional, Sequence

from PyQt5 import QtCore, QtWidgets

from ..config import APP_NAME, ORG_NAME, env_override
from .card_reorder import (
    DRAG_THRESHOLD,
    PREVIEW_OPACITY,
    SETTINGS_PREFIX,
    DropPlaceholder,
    drag_handles,
)
from .widgets import Card

#: Opacity of the card that is being dragged, still sitting in its own slot.
SOURCE_OPACITY = 0.35

#: A grid slot as ``(row, column, rowSpan, columnSpan)``.
Slot = tuple[int, int, int, int]


class GridCardReorder(QtCore.QObject):
    """Reorder the :class:`Card` widgets of one fixed grid.

    ``cards`` is the list in current slot order and ``slots`` the fixed list of
    grid positions; ``cards[i]`` always occupies ``slots[i]``.  The order is
    persisted under ``layout/cards/<key>`` in the window's ``QSettings`` and
    restored once the panel has finished building its cards.
    """

    def __init__(
        self,
        panel: QtWidgets.QWidget,
        grid: QtWidgets.QGridLayout,
        cards: Sequence[Card],
        key: str,
        slots: Sequence[Slot],
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent if parent is not None else panel)
        self._panel = panel
        self._grid = grid
        self._cards: list[Card] = list(cards)
        self._slots: list[Slot] = [
            (int(row), int(col), int(row_span), int(col_span))
            for row, col, row_span, col_span in slots
        ]
        self._key = str(key)
        self._own_settings: Optional[QtCore.QSettings] = None

        self._press: Optional[tuple[Card, QtCore.QPoint]] = None
        self._drag_card: Optional[Card] = None
        self._placeholder: Optional[DropPlaceholder] = None
        self._preview: Optional[QtWidgets.QLabel] = None
        self._target: Optional[Card] = None
        self._drag_offset = QtCore.QPoint()
        self._handles: dict[Card, set[QtWidgets.QWidget]] = {
            card: set(drag_handles(card)) for card in self._cards
        }

        self._install_gesture()

        # A drag installs the controller as an application-wide event filter.
        # If the panel is destroyed mid-gesture, Qt would keep that pointer and
        # the next event would hit a dead object.  The hook holds only a weak
        # reference so it can run while the controller itself is torn down.
        app = QtWidgets.QApplication.instance()
        if app is not None:
            controller_ref = weakref.ref(self)

            def detach(*_args, _app=app, _ref=controller_ref):
                controller = _ref()
                if controller is None:
                    return
                try:
                    _app.removeEventFilter(controller)
                except RuntimeError:
                    pass

            panel.destroyed.connect(detach)

        # The saved order is applied once the panel has finished building its
        # cards.  The timer is a child of the controller so it dies with the
        # panel instead of firing into deleted C++ objects.
        self._restore_timer = QtCore.QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self.restore_order)
        self._restore_timer.start(0)

    # --------------------------------------------------------------- public
    @property
    def key(self) -> str:
        """Group name used in ``QSettings`` and in test assertions."""
        return self._key

    def cards(self) -> list[Card]:
        """The cards in their current slot order."""
        return list(self._cards)

    def order(self) -> list[str]:
        """Stable ids of the cards, in current slot order."""
        return [self._card_id(card) for card in self._cards]

    def is_dragging(self) -> bool:
        """Whether a drag gesture is in progress."""
        return self._drag_card is not None

    def move(self, source_index: int, target_index: int) -> bool:
        """Exchange the cards in two slots, as if one had been dragged there.

        The dragged card takes the target's slot and the target takes the
        dragged card's slot; every other card keeps its own.  This is what the
        grid asks for: ``move(2, 0)`` must put the wide output card into the
        first half-width slot and send the source card into the wide bottom
        slot, without a third card hopping rows.  The new order is persisted.
        """
        cards = self._cards
        if len(cards) < 2 or not 0 <= source_index < len(cards):
            return False
        target_index = max(0, min(target_index, len(cards) - 1))
        if target_index == source_index:
            return False

        cards[source_index], cards[target_index] = (
            cards[target_index],
            cards[source_index],
        )
        if not self._apply_slots():
            return False
        self._store_order()
        return True

    def restore_order(self) -> None:
        """Apply the persisted order immediately (the timer also calls this)."""
        self._restore_timer.stop()
        self._apply_order(self._saved_order())

    # --------------------------------------------------------------- layout
    def _apply_slots(self) -> bool:
        """Put ``self._cards[i]`` into ``self._slots[i]``; ``False`` if torn down."""
        try:
            for card in self._cards:
                self._grid.removeWidget(card)
            for slot, card in zip(self._slots, self._cards):
                self._grid.addWidget(card, *slot)
                card.show()
            self._grid.invalidate()
            self._grid.activate()
        except RuntimeError:
            # The panel (and its grid/cards) was destroyed in the meantime.
            return False
        self._panel.updateGeometry()
        return True

    def _apply_order(self, order: Sequence[str]) -> None:
        """Reorder the existing cards to ``order``; unknown ids are appended."""
        if len(self._cards) < 2 or not order:
            return
        by_id = {self._card_id(card): card for card in self._cards}
        ordered: list[Card] = []
        seen: set[Card] = set()
        for item in order:
            card = by_id.get(item)
            if card is None or card in seen:
                # Duplicate ids in the saved string must not swallow a card.
                continue
            ordered.append(card)
            seen.add(card)
        for card in self._cards:
            if card not in seen:
                ordered.append(card)
                seen.add(card)
        if ordered == self._cards:
            return
        self._cards = ordered
        self._apply_slots()

    @staticmethod
    def _card_id(card: Card) -> str:
        value = card.property("cardId")
        if value:
            return str(value)
        return card.title_label.text() if card.title_label is not None else ""

    # ---------------------------------------------------------- persistence
    def _settings(self) -> QtCore.QSettings:
        """The panel's window settings object, or an equivalent standalone one."""
        window = self._panel.window()
        settings = getattr(window, "_qsettings", None)
        if isinstance(settings, QtCore.QSettings):
            return settings
        if self._own_settings is None:
            path = env_override("SETTINGS")
            if path:
                self._own_settings = QtCore.QSettings(
                    path, QtCore.QSettings.IniFormat
                )
            else:
                self._own_settings = QtCore.QSettings(ORG_NAME, APP_NAME)
        return self._own_settings

    def _settings_key(self) -> str:
        return f"{SETTINGS_PREFIX}/{self._key}"

    def _saved_order(self) -> list[str]:
        settings = self._settings()
        settings.sync()
        raw = settings.value(self._settings_key(), "")
        return [item for item in str(raw or "").split("|") if item]

    def _store_order(self) -> None:
        settings = self._settings()
        settings.setValue(self._settings_key(), "|".join(self.order()))
        settings.sync()

    # --------------------------------------------------------------- gesture
    def _install_gesture(self) -> None:
        """Arm every passive surface of every card.

        The drag gesture no longer swaps in a move cursor, so cards and their
        passive labels keep the normal arrow. Controls still reclaim their
        natural cursor in case a parent ever sets one.
        """
        for card in self._cards:
            handles = self._handles.get(card, set())
            for handle in handles:
                handle.installEventFilter(self)
            for control in card.findChildren(QtWidgets.QWidget):
                if control in handles or isinstance(control, QtWidgets.QLineEdit):
                    continue
                control.setCursor(
                    QtCore.Qt.IBeamCursor
                    if isinstance(control, QtWidgets.QTextEdit)
                    else QtCore.Qt.ArrowCursor
                )

    def _card_for(self, obj: QtCore.QObject) -> Optional[Card]:
        """The card that ``obj`` is a handle of, if any."""
        current = obj
        while isinstance(current, QtWidgets.QWidget):
            for card in self._cards:
                if current is card:
                    return card
            if current is self._panel:
                return None
            current = current.parentWidget()
        return None

    def _press_on_control(
        self, card: Card, obj: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        """Whether a press on handle ``obj`` actually landed on a control.

        Qt re-delivers an ignored press to the parent widget, so a press on a
        control can also reach the card frame.  The control under the cursor
        owns that click; only passive pixels arm a drag.
        """
        if not isinstance(obj, QtWidgets.QWidget):
            return False
        child = obj.childAt(event.pos())
        if child is None:
            return False
        handles = self._handles.get(card, set())
        current: Optional[QtWidgets.QWidget] = child
        while current is not None and current is not obj:
            if current not in handles:
                return True
            current = current.parentWidget()
        return False

    def _target_at(self, global_pos: QtCore.QPoint) -> Optional[Card]:
        """The card under the cursor (never the dragged one)."""
        local = self._panel.mapFromGlobal(global_pos)
        dragged = self._drag_card
        for card in self._cards:
            if card is dragged:
                continue
            try:
                if card.isVisible() and card.geometry().contains(local):
                    return card
            except RuntimeError:
                continue
        return None

    def _show_target(self, target: Optional[Card]) -> None:
        """Move the accent wash onto ``target`` (or hide it)."""
        placeholder = self._placeholder
        if placeholder is None:
            return
        if target is None:
            try:
                placeholder.hide()
            except RuntimeError:
                self._placeholder = None
            return
        try:
            placeholder.setGeometry(target.geometry())
            placeholder.show()
            placeholder.raise_()
        except RuntimeError:
            self._placeholder = None

    def _start_drag(self, card: Card) -> bool:
        """Begin the gesture; ``False`` means the card cannot be dragged."""
        if self._drag_card is not None:
            return False
        if len(self._cards) < 2:
            return False
        try:
            if card not in self._cards:
                return False
            # Grab before the opacity effect is installed, so the ghost copy is
            # full strength; the effect only dims the card left in its slot.
            pixmap = card.grab()
        except RuntimeError:
            # The panel (and the card with it) was torn down mid-gesture.
            return False

        self._drag_card = card
        self._target = None

        placeholder = DropPlaceholder(self._panel)
        placeholder.hide()
        self._placeholder = placeholder

        effect = QtWidgets.QGraphicsOpacityEffect(card)
        effect.setOpacity(SOURCE_OPACITY)
        card.setGraphicsEffect(effect)

        # ``grab()`` returns device pixels; the label must stay in logical
        # pixels or a 125/150/200 % display scales the ghost above the card.
        preview = QtWidgets.QLabel(self._panel)
        preview.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        preview.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        preview.setFixedSize(card.size())
        if not pixmap.isNull():
            preview.setPixmap(pixmap)
        preview_effect = QtWidgets.QGraphicsOpacityEffect(preview)
        preview_effect.setOpacity(PREVIEW_OPACITY)
        preview.setGraphicsEffect(preview_effect)
        preview.move(card.geometry().topLeft())
        preview.show()
        preview.raise_()
        self._preview = preview

        if self._press is not None:
            press_global = self._press[1]
        else:
            press_global = card.mapToGlobal(card.rect().center())
        card_global = card.mapToGlobal(QtCore.QPoint(0, 0))
        self._drag_offset = press_global - card_global

        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        return True

    def _drag_to(self, global_pos: QtCore.QPoint) -> None:
        """Follow the cursor with the ghost and wash the slot below it."""
        target = self._target_at(global_pos)
        self._target = target
        # The placeholder raises itself, so the translucent ghost has to be
        # raised afterwards to stay above the slot wash.
        self._show_target(target)
        preview = self._preview
        if preview is not None:
            try:
                preview.move(
                    self._panel.mapFromGlobal(global_pos - self._drag_offset)
                )
                preview.raise_()
            except RuntimeError:
                self._preview = None

    def _finish_drag(
        self, commit: bool, global_pos: Optional[QtCore.QPoint] = None
    ) -> None:
        """End the gesture, cleaning every helper before an optional move."""
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

        card = self._drag_card
        if card is None:
            return
        # Clear the gesture state first so a re-entrant release is a no-op.
        self._drag_card = None
        self._press = None
        target = self._target if commit else None
        if target is not None and global_pos is not None:
            target = self._target_at(global_pos)
        self._target = None

        placeholder = self._placeholder
        self._placeholder = None
        if placeholder is not None:
            try:
                placeholder.hide()
                placeholder.deleteLater()
            except RuntimeError:
                pass

        preview = self._preview
        self._preview = None
        if preview is not None:
            try:
                preview.hide()
                preview.deleteLater()
            except RuntimeError:
                pass

        # ``setGraphicsEffect(None)`` deletes the effect; no Python reference to
        # it is kept, so nothing can point at a dead C++ object afterwards.
        try:
            card.setGraphicsEffect(None)
            card.show()
            card.update()
        except RuntimeError:
            # The card (panel) was destroyed while it was being dragged.
            return

        if target is None:
            return
        try:
            source_index = self._cards.index(card)
            target_index = self._cards.index(target)
        except ValueError:
            return
        if source_index != target_index:
            self.move(source_index, target_index)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Track the press/drag/release gesture on the registered handles.

        A ``RuntimeError`` raised inside this Qt virtual would be escalated to
        ``qFatal`` by PyQt5 and abort the process, so a widget tree that is
        being torn down (deleted C++ wrappers, half-destroyed parents) must
        degrade to "event ignored" instead.
        """
        try:
            return self._handle_event(obj, event)
        except RuntimeError:
            return False
        except AttributeError:
            # Qt keeps calling the filter while the panel is being torn down,
            # at which point CPython has already cleared this object's instance
            # dict.  A Python exception escaping a Qt virtual is escalated to
            # ``qFatal`` (0xC0000409), so a half-finalised filter must simply
            # decline the event.
            return False

    def _handle_event(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if self._drag_card is not None:
            event_type = event.type()
            if (
                event_type == QtCore.QEvent.MouseButtonPress
                and event.button() == QtCore.Qt.LeftButton
            ):
                # A release was lost (capture, lock screen, app switch). A new
                # press cancels the stale drag and is then handled normally.
                self._finish_drag(False)
                return False
            if event_type in (
                QtCore.QEvent.ApplicationDeactivate,
                QtCore.QEvent.WindowDeactivate,
            ):
                self._finish_drag(False)
                return False
            if event_type == QtCore.QEvent.MouseMove:
                self._drag_to(event.globalPos())
                return True
            if (
                event_type == QtCore.QEvent.MouseButtonRelease
                and event.button() == QtCore.Qt.LeftButton
            ):
                self._finish_drag(True, event.globalPos())
                return True
            if (
                event_type == QtCore.QEvent.KeyPress
                and event.key() == QtCore.Qt.Key_Escape
            ):
                self._finish_drag(False)
                return True
            return False

        card = self._card_for(obj)
        if card is None:
            return False
        if (
            event.type() == QtCore.QEvent.MouseButtonPress
            and event.button() == QtCore.Qt.LeftButton
        ):
            if self._press_on_control(card, obj, event):
                self._press = None
                return False
            self._press = (card, QtCore.QPoint(event.globalPos()))
            # Let the press through: the handle keeps Qt's implicit mouse grab,
            # which is what makes the gesture survive leaving the card.
            return False
        if (
            event.type() == QtCore.QEvent.MouseMove
            and self._press is not None
            and event.buttons() & QtCore.Qt.LeftButton
        ):
            pressed, origin = self._press
            if pressed is card and (
                event.globalPos() - origin
            ).manhattanLength() >= DRAG_THRESHOLD:
                started = self._start_drag(card)
                self._press = None
                # A card that cannot be dragged must not swallow the move; a
                # real drag consumes it.
                return started
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            self._press = None
        return False
