"""Free positioning and stacking of the existing video pane widgets."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRegion
from PySide6.QtWidgets import QApplication, QWidget


class _SelectionOverlay(QWidget):
    """Paint editing affordances without intercepting playback or crop input."""

    def __init__(self, stage):
        super().__init__(stage)
        self.stage = stage
        self._painted_region = QRegion()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _selection_region(self):
        stage = self.stage
        pane = stage._panes.get(stage._active_id)
        region = QRegion()
        if stage._editing and pane is not None and pane.isVisible():
            rect = pane.geometry()
            outer = rect.adjusted(-6, -6, 6, 6)
            inner = rect.adjusted(7, 7, -7, -7)
            region = QRegion(outer)
            if not inner.isEmpty():
                region -= QRegion(inner)
        return region

    def update_selection(self):
        """Invalidate only old/new outlines, not all the videos beneath us."""
        region = self._selection_region()
        damage = self._painted_region | region
        self._painted_region = region
        if not damage.isEmpty():
            self.update(damage)

    def paintEvent(self, event):
        # The first show can paint before any visible selection was requested.
        # Remember those handles too, so the first move erases their old halo.
        self._painted_region = self._selection_region()
        stage = self.stage
        pane = stage._panes.get(stage._active_id)
        if not stage._editing or pane is None or not pane.isVisible():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = QRectF(pane.geometry()).adjusted(0.75, 0.75, -0.75, -0.75)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#071f1a"), 3))
        painter.drawRect(rect)
        painter.setPen(QPen(QColor("#52d3ba"), 1.5))
        painter.drawRect(rect)
        painter.setBrush(QColor("#d9fff5"))
        painter.setPen(QPen(QColor("#1c8270"), 1))
        for point in stage._handle_points(pane.geometry()).values():
            painter.drawRect(QRectF(point.x() - 4, point.y() - 4, 8, 8))


class FreeCanvas(QWidget):
    """A borderless stage whose layers retain normalized position and size.

    Selecting a layer never changes its stacking order.  Editing uses one
    mouse-transparent overlay; hiding it leaves only the normal video panes.
    The panes and their players are reused rather than recreated.
    """

    contextRequested = Signal(QPoint)
    filesDropped = Signal(list)

    _CURSORS = {
        "nw": Qt.CursorShape.SizeFDiagCursor,
        "se": Qt.CursorShape.SizeFDiagCursor,
        "ne": Qt.CursorShape.SizeBDiagCursor,
        "sw": Qt.CursorShape.SizeBDiagCursor,
        "n": Qt.CursorShape.SizeVerCursor,
        "s": Qt.CursorShape.SizeVerCursor,
        "e": Qt.CursorShape.SizeHorCursor,
        "w": Qt.CursorShape.SizeHorCursor,
    }

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self._panes = {}
        self._filtered = {}
        self._active_id = getattr(owner, "active_id", None)
        self._editing = not getattr(owner, "clean_mode", True)
        self._drag = None
        self.setObjectName("freeCanvas")
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("QWidget#freeCanvas { background: #000000; border: none; }")
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.installEventFilter(self)
        self._overlay = _SelectionOverlay(self)
        self._overlay.setVisible(self._editing)

    def attach_panes(self, panes):
        """Adopt video panes and apply their saved geometry and layer order."""
        self.detach_panes()
        self.sync_panes(panes)

    def sync_panes(self, panes):
        """Update layer membership without hiding/reparenting retained videos.

        A session replacement can reuse an ID with a new QWidget, so identity
        as well as the ID determines whether a pane is retained.
        """
        panes = list(panes)
        incoming = {pane.state.id: pane for pane in panes}
        replaced = {pane_id for pane_id, pane in self._panes.items()
                    if incoming.get(pane_id) is not pane}
        if self._drag is not None and self._drag["id"] in replaced:
            self._finish_drag()
        for target, pane_id in tuple(self._filtered.items()):
            if pane_id not in replaced:
                continue
            try:
                target.removeEventFilter(self)
                target.unsetCursor()
            except RuntimeError:
                pass  # A removed pane may already have reached deleteLater().
            del self._filtered[target]
        for pane_id in replaced:
            old = self._panes.pop(pane_id)
            try:
                if old.parentWidget() is self:
                    old.setParent(self.owner.pane_parking)
            except RuntimeError:
                pass

        for index, pane in enumerate(panes):
            pane_id = pane.state.id
            if self._panes.get(pane_id) is pane:
                continue
            self._panes[pane_id] = pane
            pane.setParent(self)
            pane.setMinimumSize(0, 0)
            if getattr(pane.state, "canvas_rect", None) is None:
                pane.state.canvas_rect = ((0.0, 0.0, 1.0, 1.0) if len(panes) == 1
                                          else (0.08 + index * 0.04,
                                                0.08 + index * 0.04, 0.6, 0.6))
            for target in (pane, pane.canvas, pane.canvas.viewport()):
                target.setMouseTracking(True)
                target.installEventFilter(self)
                self._filtered[target] = pane_id
            pane.show()
        # Preserve the caller's stable ordering when z ranks are equal.
        self._panes = incoming
        active_id = getattr(self.owner, "active_id", self._active_id)
        self._active_id = active_id if active_id in self._panes else next(iter(self._panes), None)
        self.refresh_geometry()
        self._apply_stacking()
        self._overlay.setVisible(self._editing)

    def detach_panes(self):
        """Release panes before the caller disposes of an old workspace."""
        self._finish_drag()
        for target in tuple(self._filtered):
            try:
                target.removeEventFilter(self)
                target.unsetCursor()
            except RuntimeError:
                pass
        self._filtered.clear()
        for pane in tuple(self._panes.values()):
            try:
                pane.setParent(self.owner.pane_parking)
            except RuntimeError:
                pass
        self._panes.clear()
        self._overlay.update_selection()

    def set_editing(self, editing):
        self._editing = bool(editing)
        if not self._editing:
            self._finish_drag()
            self.unsetCursor()
            for target in self._filtered:
                try:
                    target.unsetCursor()
                except RuntimeError:
                    pass
        self._overlay.setVisible(self._editing)
        self._overlay.raise_()
        self._overlay.update_selection()

    def set_active(self, pane_id):
        if self._active_id == pane_id:
            return
        self._active_id = pane_id
        self._overlay.update_selection()

    def refresh_geometry(self):
        width, height = max(1, self.width()), max(1, self.height())
        for pane in self._panes.values():
            rect = getattr(pane.state, "canvas_rect", None) or (0, 0, 1, 1)
            x, y, w, h = rect
            geometry = QRect(round(x * width), round(y * height),
                             max(1, round(w * width)), max(1, round(h * height)))
            if pane.geometry() != geometry:
                pane.setGeometry(geometry)
        if self._overlay.geometry() != self.rect():
            self._overlay.setGeometry(self.rect())
        self._overlay.update_selection()

    def arrange_from_rects(self, rects):
        for pane_id, rect in rects.items():
            if pane_id in self._panes:
                self.set_rect(pane_id, rect)

    def _ordered_ids(self):
        return sorted(self._panes, key=lambda pane_id: getattr(
            self._panes[pane_id].state, "z_order", 0))

    def _apply_stacking(self):
        desired = [self._panes[pane_id] for pane_id in self._ordered_ids()]
        members = set(desired)
        children = self.children()
        actual = [child for child in children if child in members]
        if actual != desired:
            for pane in desired:
                pane.raise_()
        if not children or self.children()[-1] is not self._overlay:
            self._overlay.raise_()

    def move_layer(self, pane_id, action):
        if pane_id not in self._panes:
            return
        order = self._ordered_ids()
        index = order.index(pane_id)
        if action == "front":
            new_index = len(order) - 1
        elif action == "back":
            new_index = 0
        elif action == "forward":
            new_index = min(len(order) - 1, index + 1)
        elif action == "backward":
            new_index = max(0, index - 1)
        else:
            raise ValueError("layer action must be front, back, forward or backward")
        order.pop(index)
        order.insert(new_index, pane_id)
        for z, layer_id in enumerate(order):
            self._panes[layer_id].state.z_order = z
        self._apply_stacking()
        self._overlay.update_selection()

    def set_rect(self, pane_id, rect):
        if pane_id not in self._panes:
            return
        try:
            x, y, w, h = (float(value) for value in rect)
        except (TypeError, ValueError):
            return
        if not all(math.isfinite(value) for value in (x, y, w, h)):
            return
        stage_w, stage_h = max(1, self.width()), max(1, self.height())
        min_w, min_h = min(3.0, max(.02, 80 / stage_w)), min(3.0, max(.02, 45 / stage_h))
        w, h = max(min_w, min(3.0, w)), max(min_h, min(3.0, h))
        visible_w, visible_h = min(16 / stage_w, w, 1), min(16 / stage_h, h, 1)
        x = max(max(-1.0, visible_w - w), min(min(2.0, 1.0 - visible_w), x))
        y = max(max(-1.0, visible_h - h), min(min(2.0, 1.0 - visible_h), y))
        pane = self._panes[pane_id]
        pane.state.canvas_rect = (x, y, w, h)
        geometry = QRect(round(x * stage_w), round(y * stage_h),
                         max(1, round(w * stage_w)), max(1, round(h * stage_h)))
        if pane.geometry() != geometry:
            pane.setGeometry(geometry)
            self._overlay.update_selection()

    def nudge(self, pane_id, dx, dy):
        pane = self._panes.get(pane_id)
        if pane is None:
            return
        x, y, w, h = pane.state.canvas_rect or (0, 0, 1, 1)
        self.set_rect(pane_id, (x + dx / max(1, self.width()),
                                y + dy / max(1, self.height()), w, h))

    @staticmethod
    def _handle_points(rect):
        x, y = rect.x(), rect.y()
        right, bottom = x + rect.width(), y + rect.height()
        center_x, center_y = (x + right) / 2, (y + bottom) / 2
        return {
            "nw": QPointF(x, y), "n": QPointF(center_x, y), "ne": QPointF(right, y),
            "e": QPointF(right, center_y), "se": QPointF(right, bottom),
            "s": QPointF(center_x, bottom), "sw": QPointF(x, bottom),
            "w": QPointF(x, center_y),
        }

    def _handle_at(self, pos):
        pane = self._panes.get(self._active_id)
        if pane is None or not pane.isVisible() or pane.canvas.crop_active:
            return None
        rect = pane.geometry()
        left, top = rect.x(), rect.y()
        width, height = rect.width(), rect.height()
        # Hit testing runs on every editing mouse move. Avoid allocating a
        # dictionary and eight QPointF wrappers until handles need painting.
        for handle, fx, fy in (("nw", 0, 0), ("n", .5, 0), ("ne", 1, 0),
                               ("e", 1, .5), ("se", 1, 1), ("s", .5, 1),
                               ("sw", 0, 1), ("w", 0, .5)):
            if abs(pos.x() - (left + width * fx)) <= 7 and abs(pos.y() - (top + height * fy)) <= 7:
                return handle
        return None

    def _start_drag(self, pane_id, handle, event):
        pane = self._panes[pane_id]
        self.owner.select(pane_id)
        self.set_active(pane_id)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._drag = {"id": pane_id, "handle": handle,
                      "origin": QPointF(event.globalPosition()),
                      "rect": QRectF(pane.geometry()), "started": False}
        self.setCursor(self._CURSORS.get(handle, Qt.CursorShape.ClosedHandCursor))
        self.grabMouse()

    def _finish_drag(self):
        if self._drag is None:
            return
        self._drag = None
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self.unsetCursor()

    def _drag_to(self, event):
        drag = self._drag
        if drag is None or drag["id"] not in self._panes:
            return
        delta = event.globalPosition() - drag["origin"]
        if not drag["started"]:
            if abs(delta.x()) + abs(delta.y()) < QApplication.startDragDistance():
                return
            drag["started"] = True
        rect = QRectF(drag["rect"])
        handle = drag["handle"]
        if handle == "move":
            rect.translate(delta)
        else:
            left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
            min_w, min_h = min(80, 3 * max(1, self.width())), min(45, 3 * max(1, self.height()))
            if "w" in handle:
                left = min(right - min_w, left + delta.x())
            if "e" in handle:
                right = max(left + min_w, right + delta.x())
            if "n" in handle:
                top = min(bottom - min_h, top + delta.y())
            if "s" in handle:
                bottom = max(top + min_h, bottom + delta.y())
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                aspect = max(.001, drag["rect"].width() / max(1, drag["rect"].height()))
                w, h = right - left, bottom - top
                if handle in ("n", "s"):
                    w = max(min_w, h * aspect)
                    h = w / aspect
                elif handle in ("w", "e"):
                    h = max(min_h, w / aspect)
                    w = h * aspect
                elif abs(delta.x()) / drag["rect"].width() >= abs(delta.y()) / drag["rect"].height():
                    h = max(min_h, w / aspect)
                    w = h * aspect
                else:
                    w = max(min_w, h * aspect)
                    h = w / aspect
                if "w" in handle:
                    left = right - w
                elif "e" in handle:
                    right = left + w
                else:
                    left, right = rect.center().x() - w / 2, rect.center().x() + w / 2
                if "n" in handle:
                    top = bottom - h
                elif "s" in handle:
                    bottom = top + h
                else:
                    top, bottom = rect.center().y() - h / 2, rect.center().y() + h / 2
            rect = QRectF(left, top, right - left, bottom - top)
        self.set_rect(drag["id"], (rect.x() / max(1, self.width()),
                                    rect.y() / max(1, self.height()),
                                    rect.width() / max(1, self.width()),
                                    rect.height() / max(1, self.height())))

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonDblClick:
            self._finish_drag()
            return False
        if not self._editing:
            return False
        if event_type not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                              QEvent.Type.MouseButtonRelease):
            return False
        pane_id = self._filtered.get(watched)
        pane = self._panes.get(pane_id)
        if pane is not None and pane.canvas.crop_active:
            return False
        if event_type == QEvent.Type.MouseMove and self._drag is not None:
            self._drag_to(event)
            return True
        if event_type == QEvent.Type.MouseButtonRelease and self._drag is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_to(event)
                self._finish_drag()
                return True
            return False
        pos = self.mapFromGlobal(event.globalPosition().toPoint())
        handle = self._handle_at(pos)
        if event_type == QEvent.Type.MouseMove:
            if pane is not None or handle:
                cursor = self._CURSORS.get(handle, Qt.CursorShape.OpenHandCursor)
                if watched.cursor().shape() != cursor:
                    watched.setCursor(cursor)
            else:
                if watched.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
                    watched.unsetCursor()
            return False
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            target_id = self._active_id if handle else pane_id
            if target_id in self._panes:
                self._start_drag(target_id, handle or "move", event)
                return True
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_geometry()

    def contextMenuEvent(self, event):
        self.contextRequested.emit(event.globalPos())
        event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()
