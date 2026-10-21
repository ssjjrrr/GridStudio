"""Video rendering canvas with independent crop, rotation, and mirror transforms."""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QTransform
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from .i18n import tr, translated_existing


class VideoCanvas(QGraphicsView):
    """A video output whose crop always refers to the original source image.

    Assign ``video_item`` to QMediaPlayer.setVideoOutput().  Rendering transforms
    belong to this canvas and do not modify the player's source or its frames.
    """

    activated = Signal()
    doubleClicked = Signal()
    contextRequested = Signal(QPoint)
    filesDropped = Signal(list)
    cropSelected = Signal(tuple)
    contentGeometryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#0b1018"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # This is a regular raster QWidget viewport. Let Qt restrict paints to
        # changed items (notably the crop selection); a video frame still
        # invalidates the complete video item's visible rectangle.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self._source_size = QSizeF(1280.0, 720.0)
        self._crop = (0.0, 0.0, 1.0, 1.0)
        self._rotation = 0
        self._flip_h = False
        self._flip_v = False
        self._fill_mode = "contain"
        self._has_media = False
        self._message = "拖入视频文件"
        self._crop_active = False
        self._crop_start = None
        self._crop_hint = "拖动框选裁剪区域 · Esc 取消"
        self._fitting = False
        self._last_fit = None

        # The invisible parent clips the source before any rotation/mirroring.
        self._clip_item = QGraphicsRectItem()
        self._clip_item.setPen(QPen(Qt.PenStyle.NoPen))
        self._clip_item.setBrush(Qt.BrushStyle.NoBrush)
        self._clip_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
        self.scene().addItem(self._clip_item)
        self._video_item = QGraphicsVideoItem(self._clip_item)
        self._video_item.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        self._video_item.setSize(self._source_size)
        self._video_item.nativeSizeChanged.connect(self._native_size_changed)
        self._clip_item.setVisible(False)

        self._selection = QGraphicsRectItem()
        selection_pen = QPen(QColor("#fb7185"), 2.0)
        selection_pen.setCosmetic(True)
        self._selection.setPen(selection_pen)
        self._selection.setBrush(QColor(244, 63, 94, 45))
        self._selection.setZValue(100.0)
        self._selection.setVisible(False)
        self.scene().addItem(self._selection)
        self._apply_transform()

    @property
    def video_item(self) -> QGraphicsVideoItem:
        return self._video_item

    @property
    def crop_active(self) -> bool:
        return self._crop_active

    def source_size(self) -> QSizeF:
        return QSizeF(self._source_size)

    def retranslate_ui(self):
        # Keep the empty-picture sentinel independent of the chosen language.
        if self._message != "拖入视频文件":
            self._message = translated_existing(self._message)
        self.viewport().update()

    @property
    def fill_mode(self) -> str:
        return self._fill_mode

    def set_fill_mode(self, mode: str) -> None:
        """Cover the pane without letterboxing, or contain the complete crop."""
        if mode not in ("cover", "contain", "stretch"):
            raise ValueError("fill mode must be cover, contain or stretch")
        if self._fill_mode == mode:
            return
        self._fill_mode = mode
        self._fit_video()
        self.viewport().update()

    def set_has_media(self, has_media: bool) -> None:
        has_media = bool(has_media)
        message = self._message
        if has_media and message == "拖入视频文件":
            message = ""
        elif not has_media and not message:
            message = "拖入视频文件"
        if (has_media, message) == (self._has_media, self._message):
            return
        self._has_media, self._message = has_media, message
        if not self._has_media and self._crop_active:
            self.cancel_crop()
        self._clip_item.setVisible(self._has_media)
        self.viewport().update()
        self.contentGeometryChanged.emit()

    def set_message(self, message: str) -> None:
        message = str(message)
        if self._message == message:
            return
        self._message = message
        self.viewport().update()
        self.contentGeometryChanged.emit()

    def video_content_rect(self) -> QRect | None:
        """Return the visible picture in viewport pixels, excluding letterbox.

        Loading/error messages and crop editing need the complete viewport.
        This uses the current view transform, including crop and rotation,
        rather than inferring an aspect ratio from the original file.
        """
        if not self._has_media or self._message or self._crop_active:
            return None
        scene_rect = self._clip_item.mapRectToScene(self._clip_item.rect())
        rect = self.viewportTransform().mapRect(scene_rect)
        # A widget mask uses integer logical pixels. Round inward so a
        # fractionally covered edge cannot reintroduce a dark border.
        left, top = math.ceil(rect.left() - 1e-6), math.ceil(rect.top() - 1e-6)
        right, bottom = math.floor(rect.right() + 1e-6), math.floor(rect.bottom() + 1e-6)
        return QRect(left, top, max(0, right - left), max(0, bottom - top)).intersected(self.viewport().rect())

    def set_transform(self, crop=(0.0, 0.0, 1.0, 1.0), rotation=0,
                      flip_h=False, flip_v=False) -> None:
        """Apply normalized source crop, clockwise rotation, then mirroring."""
        try:
            x, y, width, height = (float(value) for value in crop)
            x = min(max(x, 0.0), 0.999)
            y = min(max(y, 0.0), 0.999)
            width = min(max(width, 0.001), 1.0 - x)
            height = min(max(height, 0.001), 1.0 - y)
            normalized_crop = (x, y, width, height)
        except (TypeError, ValueError):
            normalized_crop = (0.0, 0.0, 1.0, 1.0)
        rotation = int(rotation) % 360
        flip_h, flip_v = bool(flip_h), bool(flip_v)
        if (normalized_crop, rotation, flip_h, flip_v) == (self._crop, self._rotation, self._flip_h, self._flip_v):
            return
        self._crop, self._rotation = normalized_crop, rotation
        self._flip_h, self._flip_v = flip_h, flip_v
        self._apply_transform()

    def _native_size_changed(self, size: QSizeF) -> None:
        if size.width() > 0 and size.height() > 0 and size != self._source_size:
            self._source_size = QSizeF(size)
            self._video_item.setSize(size)
            self._apply_transform()

    def _source_rect(self) -> QRectF:
        return QRectF(QPointF(0.0, 0.0), self._source_size)

    def _apply_transform(self) -> None:
        width, height = self._source_size.width(), self._source_size.height()
        if self._crop_active:
            rect = self._source_rect()
            transform = QTransform()
        else:
            x, y, crop_width, crop_height = self._crop
            rect = QRectF(x * width, y * height, crop_width * width, crop_height * height)
            center = rect.center()
            transform = QTransform()
            transform.translate(center.x(), center.y())
            transform.scale(-1.0 if self._flip_h else 1.0,
                            -1.0 if self._flip_v else 1.0)
            transform.rotate(self._rotation)
            transform.translate(-center.x(), -center.y())
        self._clip_item.setRect(rect)
        self._clip_item.setTransform(transform)
        self._fit_video()
        self.viewport().update()

    def _fit_video(self) -> None:
        if self._fitting or self.viewport().width() <= 1 or self.viewport().height() <= 1:
            return
        self._fitting = True
        try:
            # Explicit bounds avoid the uncropped child's larger bounding box.
            rect = self._clip_item.mapRectToScene(self._clip_item.rect())
            if rect.width() <= 0 or rect.height() <= 0:
                return
            width = float(self.viewport().width())
            height = float(self.viewport().height())
            fit = (rect.x(), rect.y(), rect.width(), rect.height(), width, height,
                   self._fill_mode, self._crop_active, self.devicePixelRatioF())
            if fit == self._last_fit:
                return
            self._last_fit = fit
            self.scene().setSceneRect(rect)
            if self._fill_mode == "stretch" and not self._crop_active:
                scale_x = width / rect.width()
                scale_y = height / rect.height()
            elif self._fill_mode == "cover" and not self._crop_active:
                # QGraphicsView.fitInView adds an internal safety margin. Use
                # explicit cover scaling instead, with one physical pixel of
                # overscan at each edge to absorb integer scroll/DPI rounding.
                padding = 2.0 / max(1.0, self.devicePixelRatioF())
                scale = max((width + padding) / rect.width(), (height + padding) / rect.height())
                scale_x = scale_y = scale
            else:
                scale = min(width / rect.width(), height / rect.height())
                scale_x = scale_y = scale
            self.setTransform(QTransform.fromScale(scale_x, scale_y))
            self.centerOn(rect.center())
        finally:
            self._fitting = False
        self.contentGeometryChanged.emit()

    def start_crop(self) -> None:
        if not self._has_media:
            return
        self._crop_active = True
        self._crop_start = None
        self._selection.setVisible(False)
        self._crop_hint = "拖动框选裁剪区域 · Esc 取消"
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._apply_transform()

    def cancel_crop(self) -> None:
        if not self._crop_active:
            return
        self._crop_active = False
        self._crop_start = None
        self._selection.setVisible(False)
        self.unsetCursor()
        self._apply_transform()

    def _source_point(self, viewport_point) -> QPointF:
        scene_point = self.mapToScene(viewport_point)
        point = self._video_item.mapFromScene(scene_point)
        return QPointF(min(max(point.x(), 0.0), self._source_size.width()),
                       min(max(point.y(), 0.0), self._source_size.height()))

    def mousePressEvent(self, event) -> None:
        self.activated.emit()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self._crop_active and event.button() == Qt.MouseButton.LeftButton:
            scene_point = self.mapToScene(event.position().toPoint())
            if self._source_rect().contains(self._video_item.mapFromScene(scene_point)):
                self._crop_start = self._source_point(event.position().toPoint())
                self._selection.setRect(QRectF(self._crop_start, self._crop_start))
                self._selection.setVisible(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._crop_active and self._crop_start is not None:
            point = self._source_point(event.position().toPoint())
            self._selection.setRect(QRectF(self._crop_start, point).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._crop_active and event.button() == Qt.MouseButton.LeftButton:
            if self._crop_start is not None:
                point = self._source_point(event.position().toPoint())
                rect = QRectF(self._crop_start, point).normalized().intersected(self._source_rect())
                self._crop_start = None
                width, height = self._source_size.width(), self._source_size.height()
                if rect.width() / width >= 0.02 and rect.height() / height >= 0.02:
                    crop = (rect.x() / width, rect.y() / height,
                            rect.width() / width, rect.height() / height)
                    self.cancel_crop()
                    self.cropSelected.emit(crop)
                else:
                    self._selection.setVisible(False)
                    self._crop_hint = "框选区域太小，请重新拖动 · Esc 取消"
                    self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._crop_active:
            event.accept()
            return
        self.activated.emit()
        self.doubleClicked.emit()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if self._crop_active and event.key() == Qt.Key.Key_Escape:
            self.cancel_crop()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        self.activated.emit()
        self.contextRequested.emit(event.globalPos())
        event.accept()

    @staticmethod
    def _local_paths(event) -> list[str]:
        if not event.mimeData().hasUrls():
            return []
        return [url.toLocalFile() for url in event.mimeData().urls()
                if url.isLocalFile() and url.toLocalFile()]

    def dragEnterEvent(self, event) -> None:
        if self._local_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._local_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = self._local_paths(event)
        if paths:
            self.activated.emit()
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_video()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._has_media and not self._crop_active and not self._message:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._crop_active:
            hint_width = min(self.viewport().width() - 16, 420)
            hint_rect = QRectF((self.viewport().width() - hint_width) / 2, 12, hint_width, 36)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(8, 14, 23, 215))
            painter.drawRoundedRect(hint_rect, 8, 8)
            painter.setPen(QColor("#d8eefb"))
            font = QFont(self.font())
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, tr(self._crop_hint))
        else:
            bounds = self.viewport().rect()
            if self._has_media:
                painter.fillRect(bounds, QColor(11, 16, 24, 238))
            center = bounds.center()
            painter.setPen(QPen(QColor("#334155"), 2))
            painter.drawRoundedRect(QRectF(center.x() - 22, center.y() - 54, 44, 34), 6, 6)
            painter.drawLine(QPointF(center.x() - 7, center.y() - 37), QPointF(center.x() + 7, center.y() - 37))
            painter.drawLine(QPointF(center.x(), center.y() - 44), QPointF(center.x(), center.y() - 30))
            painter.setPen(QColor("#b8c6d9"))
            font = QFont(self.font())
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(QRectF(16, center.y() - 4, max(0, bounds.width() - 32), 54),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                             tr(self._message))
            if self._message == "拖入视频文件":
                painter.setPen(QColor("#64748b"))
                font.setPointSize(9)
                painter.setFont(font)
                painter.drawText(QRectF(12, center.y() + 37, max(0, bounds.width() - 24), 42),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                                 tr("可同时拖入多个视频 · 右键查看更多操作"))
        painter.end()

    def capture_image(self) -> QImage:
        """Capture the visible viewport, including the current transformed frame."""
        return self.viewport().grab().toImage()
