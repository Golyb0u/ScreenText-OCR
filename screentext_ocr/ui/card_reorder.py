"""Drag-to-reorder support for vertical stacks of :class:`widgets.Card`.

The settings pages are built from painted cards inside a :class:`PageScroll`,
and the right rail (:class:`help.HelpPanel`) stacks three cards of its own.
This controller lets the user grab a card by any passive surface - its frame,
margins, header, hint, row containers or preview - and drag it to another slot
in the same list; the resulting order is persisted in ``QSettings`` under
``layout/cards/<key>`` and restored on the next start.

Only whole cards move.  Interactive controls inside ``card.body`` (buttons,
combo boxes, line edits, spin boxes, sliders, text areas, scroll areas and tab
widgets) keep their own mouse handling and are excluded by
:func:`drag_handles`.  The gesture is a press-then-move sequence: a release
without movement stays an ordinary click and is never consumed.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt5 import QtCore, QtGui, QtWidgets

from ..config import APP_NAME, ORG_NAME, env_override
from ..i18n import tr
from . import theme
from .widgets import Card

#: Tooltip shown on a reorderable card's title and hint labels.  Deliberately
#: not set on the card frame: Qt bubbles ``QEvent.ToolTip`` to the parent, so a
#: frame tooltip would also pop over the help browser and the image preview.
DRAG_HINT = "Перетащи карточку, чтобы изменить порядок"

#: ``QSettings`` group for the persisted order of every reorderable list.
SETTINGS_PREFIX = "layout/cards"

#: Manhattan distance in pixels that turns a press into a drag.
DRAG_THRESHOLD = 6

#: Opacity of the floating card preview while dragging.
PREVIEW_OPACITY = 0.72

#: Alpha of the accent wash painted in the drop slot.
PLACEHOLDER_ALPHA = 34

#: Control types that keep their own mouse handling.  Everything else inside a
#: card (labels, plain widgets, frames, row containers, image previews) is a
#: passive surface that may start a reorder drag.
_INTERACTIVE_TYPES = (
    QtWidgets.QAbstractButton,
    QtWidgets.QComboBox,
    QtWidgets.QLineEdit,
    QtWidgets.QAbstractSpinBox,
    QtWidgets.QAbstractSlider,
    QtWidgets.QTextEdit,
    QtWidgets.QAbstractScrollArea,
    QtWidgets.QTabWidget,
)


def _is_passive(widget: QtWidgets.QWidget) -> bool:
    """Whether ``widget`` accepts no input of its own (so it can start a drag)."""
    return not isinstance(widget, _INTERACTIVE_TYPES)


def drag_handles(card: Card) -> list[QtWidgets.QWidget]:
    """The card and every passive descendant, i.e. the surfaces that may drag it.

    Interactive controls and anything nested inside them (a spin box's line
    edit, a tab widget's bar) are left out so clicks keep reaching them.  A
    passive widget that merely *contains* a control (``FormRow``) stays in the
    list: grabbing the row's label or its padding must move the card.
    """
    handles: list[QtWidgets.QWidget] = [card]
    for child in card.findChildren(QtWidgets.QWidget):
        if _is_passive(child) and not _control_between(child, card):
            handles.append(child)
    return handles


def _control_between(widget: QtWidgets.QWidget, stop: QtWidgets.QWidget) -> bool:
    """Whether ``widget`` is or sits inside an interactive control below ``stop``."""
    current: Optional[QtWidgets.QWidget] = widget
    while current is not None and current is not stop:
        if not _is_passive(current):
            return True
        current = current.parentWidget()
    return False


def _accent_color() -> QtGui.QColor:
    """Accent colour from the active palette, with the dark default as fallback."""
    tokens = theme.active_tokens() or theme.DEFAULT_TOKENS
    color = theme._parse_color(tokens.get("accent", theme.DEFAULT_TOKENS["accent"]))
    if not color.isValid():
        color = QtGui.QColor(theme.DEFAULT_TOKENS["accent"])
    return color


def _corner_radius() -> int:
    """Card corner radius from the active palette, clamped to a sane value."""
    tokens = theme.active_tokens() or theme.DEFAULT_TOKENS
    try:
        radius = int(tokens.get("radius", theme.DEFAULT_TOKENS["radius"]))
    except (TypeError, ValueError):
        radius = int(theme.DEFAULT_TOKENS["radius"])
    return max(2, radius)


class DropPlaceholder(QtWidgets.QWidget):
    """Quiet accent wash marking the slot the dragged card will occupy.

    A plain ``QWidget`` is used instead of a ``QFrame`` so the ``role=card``
    stylesheet rules do not add a border or a second fill on top of the wash.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropPlaceholder")
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802 - Qt naming
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setPen(QtCore.Qt.NoPen)
            wash = _accent_color()
            wash.setAlpha(PLACEHOLDER_ALPHA)
            painter.setBrush(wash)
            radius = _corner_radius()
            painter.drawRoundedRect(
                QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1), radius, radius
            )
        finally:
            painter.end()


class CardReorder(QtCore.QObject):
    """Reorder the :class:`Card` widgets of one vertical card list.

    ``key`` names the persisted list (``"ocr"``, ``"capture"``, ``"help"``,
    ...).  The controller registers the cards that are already in the layout
    when it is created, and :meth:`register_card` makes cards added later part
    of the same list.  Non-card items (trailing stretchers, spacers) are never
    touched and keep their place; the stretch factors of the cards themselves
    are remembered and restored after every reorder.

    Use ``CardReorder(scroll, key)`` for a :class:`PageScroll` page and
    :meth:`for_layout` for any other ``QVBoxLayout`` (the help rail).
    """

    def __init__(
        self,
        scroll: QtWidgets.QScrollArea,
        key: str,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent if parent is not None else scroll)
        self._scroll = scroll
        self._setup(scroll.content_layout, scroll.content, key)

    @classmethod
    def for_layout(
        cls,
        layout: QtWidgets.QVBoxLayout,
        container: QtWidgets.QWidget,
        key: str,
        parent: Optional[QtCore.QObject] = None,
    ) -> "CardReorder":
        """Create a controller for an arbitrary vertical layout and container.

        The public constructor is tied to a :class:`PageScroll`; this variant
        lets a panel stack cards in its own layout (``HelpPanel.layout()``) and
        uses ``container`` for coordinates, parenting and settings lookup.
        """
        controller = cls.__new__(cls)
        QtCore.QObject.__init__(controller, parent or container)
        controller._scroll = None
        controller._setup(layout, container, key)
        return controller

    def _setup(
        self,
        layout: QtWidgets.QVBoxLayout,
        container: QtWidgets.QWidget,
        key: str,
    ) -> None:
        """Wire a freshly initialised object to one layout (see the class docs)."""
        self._layout: QtWidgets.QVBoxLayout = layout
        self._container: QtWidgets.QWidget = container
        self._key = str(key)
        self._own_settings: Optional[QtCore.QSettings] = None

        self._press: Optional[tuple[Card, QtCore.QPoint]] = None
        self._drag_card: Optional[Card] = None
        self._placeholder: Optional[DropPlaceholder] = None
        self._preview: Optional[QtWidgets.QLabel] = None
        self._drag_offset = QtCore.QPoint()
        self._drag_origin_index = -1
        self._drag_origin_order: list[str] = []
        self._reflow_animation: Optional[QtCore.QParallelAnimationGroup] = None
        # Stretch factor each card owned when it was registered.  Qt deletes
        # the layout item (and its stretch) on removeWidget, so every insertion
        # has to pass the factor back explicitly.
        self._stretch: dict[Card, int] = {}

        for card in self._find_cards():
            self.register_card(card)
        self._refresh_hints()

        # The saved order is applied once the page has finished building its
        # cards; a zero-delay child timer cannot outlive the page that owns it.
        self._restore_timer = QtCore.QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self.restore_order)
        self._restore_timer.start(0)

    # --------------------------------------------------------------- public

    @property
    def key(self) -> str:
        """Group name used in ``QSettings`` and in test assertions."""
        return self._key

    def register_card(self, card: Card, card_id: Optional[str] = None) -> Card:
        """Make ``card`` part of the reorderable list.

        The frame and every passive descendant become drag handles; interactive
        controls are skipped so they keep their normal behaviour.  The card's
        current stretch factor is remembered and passed back on every insertion.
        Only the title/hint labels get the drag tooltip: ``QEvent.ToolTip``
        bubbles up to the parent, so a hint on the frame would surface over the
        help browser and the image preview as well.
        """
        card.setProperty("cardReorderable", True)
        if card_id is not None:
            card.setProperty("cardId", str(card_id))
        index = self._layout.indexOf(card)
        if index >= 0:
            self._stretch[card] = max(0, self._layout.stretch(index))
        else:
            self._stretch.setdefault(card, 0)
        for handle in drag_handles(card):
            handle.installEventFilter(self)
        # Reordering stays available, but the surface keeps the normal arrow
        # cursor: the move cursor advertised a gesture the user did not ask for.
        # Controls still explicitly reclaim the arrow in case a parent sets one;
        # line edits already own their I-beam and are left untouched.
        for control in card.findChildren(QtWidgets.QWidget):
            if _is_passive(control) or isinstance(control, QtWidgets.QLineEdit):
                continue
            control.setCursor(
                QtCore.Qt.IBeamCursor
                if isinstance(control, QtWidgets.QTextEdit)
                else QtCore.Qt.ArrowCursor
            )
        self._refresh_hints()
        return card

    def _card_stretch(self, card: Optional[Card]) -> int:
        """Stretch factor remembered for ``card`` (0 while unknown)."""
        return max(0, self._stretch.get(card, 0))

    def _refresh_hints(self) -> None:
        """Advertise dragging on the title/hint labels when two cards exist.

        A single-card page (preprocessing) has nothing to reorder, so showing
        "drag to reorder" there would promise a gesture that cannot happen.
        """
        hint = tr(DRAG_HINT) if len(self._layout_cards()) >= 2 else ""
        for card in self._layout_cards():
            for handle in self._handles(card):
                handle.setToolTip(hint)

    def cards(self) -> list[Card]:
        """Registered cards in their current layout order."""
        return self._layout_cards()

    def order(self) -> list[str]:
        """Stable ids of the registered cards, in layout order."""
        return [self._card_id(card) for card in self._layout_cards()]

    def move(self, source_index: int, target_index: int) -> bool:
        """Move a card by list index, as if it had been dragged there.

        Both indices are relative to :meth:`cards`, so ``move(0, 2)`` puts the
        first card in the last card slot.  The new order is persisted and the
        trailing stretch stays last.
        """
        cards = self._layout_cards()
        if len(cards) < 2 or not 0 <= source_index < len(cards):
            return False
        target_index = max(0, min(target_index, len(cards) - 1))
        if target_index == source_index:
            return False

        card = cards[source_index]
        remaining = [item for item in cards if item is not card]
        self._layout.removeWidget(card)
        position = self._insert_position(remaining, target_index)
        self._layout.insertWidget(position, card, self._card_stretch(card))
        self._layout.activate()
        self._store_order()
        return True

    def restore_order(self) -> None:
        """Apply the persisted order immediately (the timer also calls this)."""
        self._restore_timer.stop()
        self._apply_order(self._saved_order())

    # ------------------------------------------------------ layout helpers
    def _find_cards(self) -> list[Card]:
        """Every :class:`Card` in the layout, registered or not, in order."""
        cards: list[Card] = []
        for index in range(self._layout.count()):
            item = self._layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, Card):
                cards.append(widget)
        return cards

    def _layout_cards(self) -> list[Card]:
        """Every registered card currently in the layout, in layout order."""
        return [card for card in self._find_cards() if card.property("cardReorderable")]

    @staticmethod
    def _handles(card: Card) -> list[QtWidgets.QWidget]:
        """Surfaces that also carry the drag tooltip (title and hint only)."""
        return [card.title_label, card.hint_label]

    @staticmethod
    def _card_id(card: Card) -> str:
        value = card.property("cardId")
        if value:
            return str(value)
        return card.title_label.text() if card.title_label is not None else ""

    def _insert_position(self, remaining: Sequence[Card], index: int) -> int:
        """Layout index that puts a card at card-relative ``index``."""
        index = max(0, min(index, len(remaining)))
        if not remaining:
            return max(0, self._layout.count() - 1)
        if index < len(remaining):
            position = self._layout.indexOf(remaining[index])
        else:
            position = self._layout.indexOf(remaining[-1]) + 1
        return max(0, position)

    def _layout_slots(self) -> list[int]:
        """Gap index (among non-card items) that each card currently sits in.

        Remembering the gaps instead of fixed positions keeps stretchers and
        spacers where the page put them when the cards are reordered.
        """
        slots: list[int] = []
        non_card = 0
        for index in range(self._layout.count()):
            item = self._layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, Card) and widget.property("cardReorderable"):
                slots.append(non_card)
            else:
                non_card += 1
        return slots

    def _apply_order(self, order: Sequence[str]) -> None:
        """Reorder the existing cards to ``order``; unknown ids are appended."""
        cards = self._layout_cards()
        if len(cards) < 2 or not order:
            return
        by_id = {self._card_id(card): card for card in cards}
        ordered: list[Card] = []
        seen: set[Card] = set()
        for item in order:
            card = by_id.get(item)
            if card is None or card in seen:
                # Duplicate ids in the saved string must not swallow a card.
                continue
            ordered.append(card)
            seen.add(card)
        for card in cards:
            if card not in seen:
                ordered.append(card)
                seen.add(card)
        if ordered == cards:
            return

        slots = self._layout_slots()
        for card in ordered:
            self._layout.removeWidget(card)
        for offset, card in enumerate(ordered):
            if offset < len(slots):
                position = slots[offset] + offset
            else:
                position = self._layout.count()
            self._layout.insertWidget(position, card, self._card_stretch(card))
        self._layout.activate()

    # ---------------------------------------------------------- persistence
    def _settings(self) -> QtCore.QSettings:
        """The container window's settings object, or an equivalent standalone one."""
        window = self._container.window()
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
    def _card_for(self, obj: QtCore.QObject) -> Optional[Card]:
        """The reorderable card that ``obj`` is a handle of, if any."""
        current = obj
        while isinstance(current, QtWidgets.QWidget):
            if isinstance(current, Card) and current.property("cardReorderable"):
                return current
            if current is self._container:
                return None
            current = current.parentWidget()
        return None

    @staticmethod
    def _press_on_control(obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Whether a press on handle ``obj`` actually landed on a control."""
        if not isinstance(obj, QtWidgets.QWidget):
            return False
        child = obj.childAt(event.pos())
        return child is not None and _control_between(child, obj)

    def _drop_index_at(self, y: int) -> int:
        """Card-relative slot for a cursor at ``y`` in container coordinates."""
        cards = [card for card in self._layout_cards() if card is not self._drag_card]
        for index, card in enumerate(cards):
            if y < card.geometry().center().y():
                return index
        return len(cards)

    def _placeholder_position(self, index: int) -> int:
        """Layout index for the placeholder, before the trailing stretch."""
        cards = [card for card in self._layout_cards() if card is not self._drag_card]
        index = max(0, min(index, len(cards)))
        if not cards:
            # A card-only layout (the help rail) has no trailing item; appending
            # is correct there, ``count() - 1`` would target the last card.
            return self._layout.count()
        if index < len(cards):
            return self._layout.indexOf(cards[index])
        return self._layout.indexOf(cards[-1]) + 1

    def _show_drop_feedback(self, index: int) -> None:
        placeholder = self._placeholder
        if placeholder is None:
            return
        try:
            current = self._layout.indexOf(placeholder)
            layout_index = self._placeholder_position(index)
            if current < layout_index:
                # Removing the placeholder shifts everything after it left by one.
                layout_index -= 1
            if current != layout_index and current >= 0:
                before = {
                    card: card.geometry().topLeft()
                    for card in self._layout_cards()
                    if card is not self._drag_card and card.isVisible()
                }
                self._layout.removeWidget(placeholder)
                self._layout.insertWidget(
                    layout_index, placeholder, self._card_stretch(self._drag_card)
                )
                self._layout.activate()
                self._animate_reflow(before)

            placeholder.show()
            placeholder.raise_()
        except RuntimeError:
            # The placeholder was deleted by a teardown in the meantime.
            self._placeholder = None

    def _animate_reflow(self, before: dict[Card, QtCore.QPoint]) -> None:
        """Slide neighbouring cards to their new slots instead of jumping."""
        self._stop_reflow_animation()
        group = QtCore.QParallelAnimationGroup(self)
        for card, old_pos in before.items():
            try:
                new_pos = card.geometry().topLeft()
                if old_pos == new_pos:
                    continue
                card.move(old_pos)
                animation = QtCore.QPropertyAnimation(card, b"pos", group)
                animation.setDuration(150)
                animation.setStartValue(old_pos)
                animation.setEndValue(new_pos)
                animation.setEasingCurve(QtCore.QEasingCurve.OutCubic)
                group.addAnimation(animation)
            except RuntimeError:
                # The card was deleted between the two reflow passes.
                continue
        if group.animationCount():
            self._reflow_animation = group
            group.finished.connect(self._clear_reflow_animation)
            group.start()
        else:
            # Nothing to animate (hidden page or unchanged slots). Forget the
            # group before handing it to deleteLater: a reference kept here
            # would point at a dead C++ object once the event loop runs, and
            # stopping it on mouse release raised RuntimeError inside the Qt
            # event filter, which PyQt5 escalates to qFatal.
            self._reflow_animation = None
            group.deleteLater()

    def _clear_reflow_animation(self) -> None:
        """Drop a group that finished on its own."""
        self._stop_reflow_animation()

    def _stop_reflow_animation(self) -> None:
        """Stop and release the current group, even if it is already deleted."""
        animation = self._reflow_animation
        self._reflow_animation = None
        if animation is None:
            return
        try:
            animation.stop()
        except RuntimeError:
            pass
        try:
            animation.deleteLater()
        except RuntimeError:
            pass

    def _start_drag(self, card: Card) -> bool:
        """Begin the gesture; ``False`` means the card cannot be dragged."""
        if self._drag_card is not None:
            return False
        if len(self._layout_cards()) < 2:
            return False
        origin = self._layout.indexOf(card)
        if origin < 0:
            return False
        try:
            pixmap = card.grab()
        except RuntimeError:
            # The page (and the card with it) was torn down mid-gesture.
            return False
        self._drag_card = card
        self._drag_origin_index = origin
        self._drag_origin_order = self.order()

        placeholder = DropPlaceholder(self._container)
        placeholder.setMinimumHeight(max(1, card.height()))
        self._placeholder = placeholder
        self._layout.removeWidget(card)
        self._layout.insertWidget(origin, placeholder, self._card_stretch(card))
        placeholder.show()
        card.hide()

        # ``grab()`` returns device pixels; the label must stay in logical
        # pixels or a 125/150/200 % display scales the ghost above the card.
        preview = QtWidgets.QLabel(self._container)
        preview.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        preview.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        preview.setFixedSize(card.size())
        if not pixmap.isNull():
            preview.setPixmap(pixmap)
        effect = QtWidgets.QGraphicsOpacityEffect(preview)
        effect.setOpacity(PREVIEW_OPACITY)
        preview.setGraphicsEffect(effect)
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
        # Move the placeholder first: it raises itself, so the translucent
        # preview must be raised afterwards to stay above the slot wash.
        local_y = self._container.mapFromGlobal(global_pos).y()
        self._show_drop_feedback(self._drop_index_at(local_y))
        preview = self._preview
        if preview is not None:
            try:
                preview.move(
                    self._container.mapFromGlobal(global_pos - self._drag_offset)
                )
                preview.raise_()
            except RuntimeError:
                self._preview = None

    def _finish_drag(self, commit: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._stop_reflow_animation()

        card = self._drag_card
        if card is None:
            return
        # Clear the gesture state first so a re-entrant release is a no-op.
        self._drag_card = None
        origin_index = self._drag_origin_index
        origin_order = self._drag_origin_order
        self._drag_origin_index = -1
        self._drag_origin_order = []

        placeholder = self._placeholder
        self._placeholder = None
        position = -1
        if placeholder is not None:
            try:
                position = self._layout.indexOf(placeholder)
                placeholder.hide()
                self._layout.removeWidget(placeholder)
                placeholder.deleteLater()
            except RuntimeError:
                position = -1

        preview = self._preview
        self._preview = None
        if preview is not None:
            try:
                preview.deleteLater()
            except RuntimeError:
                pass

        if not commit or position < 0:
            position = max(0, min(origin_index, self._layout.count()))
        try:
            self._layout.insertWidget(position, card, self._card_stretch(card))
            card.show()
            self._layout.activate()
        except RuntimeError:
            # The card (page) was destroyed while it was being dragged.
            return

        if commit and self.order() != origin_order:
            self._store_order()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Track the press/drag/release gesture on registered card handles."""
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
                self._finish_drag(True)
                return True
            if event_type == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
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
            # Qt re-delivers an ignored press to the parent widget, so a press
            # on a combo box also reaches the FormRow/Card filter.  The control
            # under the cursor owns that click; only passive pixels arm a drag.
            if self._press_on_control(obj, event):
                self._press = None
                return False
            self._press = (card, QtCore.QPoint(event.globalPos()))
            # Let the press through: the card/label keeps Qt's implicit mouse
            # grab, which is what makes the gesture survive leaving the card.
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
                # A card that cannot be dragged (single-card page) must not
                # swallow the move; a real drag consumes it as before.
                return started
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            self._press = None
        return False


def attach(
    scroll: QtWidgets.QScrollArea,
    key: str,
    parent: Optional[QtCore.QObject] = None,
) -> CardReorder:
    """Create a controller for ``scroll``; keep the result on the page."""
    return CardReorder(scroll, key, parent)
