"""Small, temporary playback controls painted over each video's picture.

The widgets never participate in a layout and never raise their video layer.
Progress dragging previews locally and commits one native seek on release.
"""
from __future__ import annotations

from .i18n import tr

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSignalBlocker, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QCursor, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QLabel, QSlider, QToolButton, QWidget

from .media_commands import media_command


def _time_text(milliseconds: int) -> str:
    seconds = max(0, int(milliseconds)) // 1000
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"
    return f"{seconds // 60:02}:{seconds % 60:02}"


def _transport_icon(name: str) -> QIcon:
    """Use small painted icons so this module does not import the main UI."""
    image = QPixmap(20, 20)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#f1fbf8")
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    if name == "play":
        painter.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(17, 10), QPointF(6, 17)]))
    elif name == "pause":
        painter.drawRoundedRect(5, 3, 4, 14, 1, 1)
        painter.drawRoundedRect(12, 3, 4, 14, 1, 1)
    else:
        painter.drawPolygon(QPolygonF([QPointF(2, 7), QPointF(6, 7), QPointF(11, 3),
                                      QPointF(11, 17), QPointF(6, 13), QPointF(2, 13)]))
        painter.setPen(QPen(color, 1.7))
        if name == "muted":
            painter.drawLine(14, 7, 19, 13)
            painter.drawLine(19, 7, 14, 13)
        else:
            painter.drawArc(8, 3, 10, 14, -70 * 16, 140 * 16)
    painter.end()
    return QIcon(image)


class _VideoTitle(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("hoverVideoTitle")
        self.setProperty("i18nUserText", True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none; color: white; font-size: 12px;")
        self.setContentsMargins(10, 0, 10, 0)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(0, 0, 0, 175))
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), gradient)
        painter.end()
        super().paintEvent(event)


class SeekBar(QWidget):
    """A timeline with hover preview, a scrub thumb, and explicit loop bounds."""

    def __init__(self, controls):
        super().__init__(controls.pane)
        self.controls = controls
        self.setObjectName("hoverSeekBar")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dragging = False
        self.preview_position: int | None = None
        self.hover_position: int | None = None
        self._duration = 0
        self._position = 0
        self._hovered = False
        self._loop_state = None
        self._display_dirty = True

    def track_rect(self) -> QRectF:
        margin = min(12.0, max(4.0, self.width() * .055))
        row_height = min(28, max(16, self.height() // 2))
        y = max(6.0, self.height() - row_height - 13.0)
        return QRectF(margin, y - 2.0, max(1.0, self.width() - margin * 2), 4.0)

    def position_at(self, point: QPoint | QPointF) -> int:
        rect = self.track_rect()
        fraction = min(1.0, max(0.0, (point.x() - rect.left()) / rect.width()))
        return round(self._duration * fraction)

    def _x_at(self, position: int) -> float:
        rect = self.track_rect()
        fraction = min(1.0, max(0.0, position / max(1, self._duration)))
        return rect.left() + rect.width() * fraction

    def loop_bounds(self) -> tuple[int, int] | None:
        state = self.controls.pane.state
        if not state.loop or self._duration <= 0:
            return None
        start = min(self._duration, max(0, int(state.loop_start_ms)))
        end = self._duration if state.loop_end_ms is None else min(self._duration, max(0, int(state.loop_end_ms)))
        return start, max(start, end)

    def set_media(self, duration: int, position: int, *, update_widgets: bool = True) -> None:
        duration = max(0, int(duration))
        position = min(duration, max(0, int(position)))
        state = self.controls.pane.state
        loop_state = (state.loop, state.loop_start_ms, state.loop_end_ms)
        if (duration, position, loop_state) != (self._duration, self._position, self._loop_state):
            self._duration, self._position, self._loop_state = duration, position, loop_state
            self._display_dirty = True
        if not self._duration and self.dragging:
            self.cancel_drag()
        if update_widgets and self._display_dirty:
            self._display_dirty = False
            self.controls._refresh_time_label()
            if self.isVisible():
                self.update()

    def cancel_drag(self) -> None:
        if (not self.dragging and self.preview_position is None
                and self.hover_position is None and not self._hovered):
            return
        self.dragging = False
        self.preview_position = None
        self.hover_position = None
        self._hovered = False
        self.controls._refresh_time_label()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(0, 0, 0, 0))
        gradient.setColorAt(.4, QColor(0, 0, 0, 95))
        gradient.setColorAt(1, QColor(0, 0, 0, 185))
        painter.fillRect(self.rect(), gradient)
        track = self.track_rect()
        y = track.center().y()
        active = self._hovered or self.dragging
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 130 if active else 90))
        painter.drawRoundedRect(track, 2, 2)

        bounds = self.loop_bounds()
        if bounds:
            start, end = bounds
            painter.setBrush(QColor(255, 207, 102, 75))
            painter.drawRect(QRectF(self._x_at(start), y - 3, self._x_at(end) - self._x_at(start), 6))

        position = self.preview_position if self.dragging else self._position
        position = self._position if position is None else position
        x = self._x_at(position)
        painter.setBrush(QColor("#71e8ce") if active else QColor("#e9fff8"))
        painter.drawRoundedRect(QRectF(track.left(), track.top(), max(0, x - track.left()), track.height()), 2, 2)
        painter.drawEllipse(QPointF(x, y), 5.0 if active else 3.5, 5.0 if active else 3.5)

        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        if bounds:
            painter.setPen(QColor("#ffdb8e"))
            for label, value in zip(("A", "B"), bounds):
                marker_x = self._x_at(value)
                painter.drawLine(QPointF(marker_x, y - 6), QPointF(marker_x, y + 6))
                # Keep endpoint labels inside the video rather than clipping.
                label_x = min(self.width() - 10.0, max(1.0, marker_x - 4))
                painter.drawText(QRectF(label_x, max(0, y - 20), 10, 12), Qt.AlignmentFlag.AlignCenter, label)

        if active and self.hover_position is not None and self._duration:
            hover_x = self._x_at(self.hover_position)
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
            painter.drawLine(QPointF(hover_x, y - 7), QPointF(hover_x, y + 7))
            text = _time_text(self.hover_position)
            text_width = painter.fontMetrics().horizontalAdvance(text) + 12
            bubble = QRectF(max(1, min(self.width() - text_width - 1, hover_x - text_width / 2)),
                            max(0, y - 29), text_width, 17)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(14, 20, 28, 235))
            painter.drawRoundedRect(bubble, 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)

        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.controls._layout_transport()

    def enterEvent(self, event):
        self._hovered = True
        point = self.mapFromGlobal(QCursor.pos())
        self.hover_position = self.position_at(point)
        self.controls._pointer_activity(QCursor.pos())
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.dragging:
            self._hovered = False
            self.hover_position = None
        self.update()
        self.controls._schedule_leave_check()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if not self.controls._enabled():
            return
        self.controls._pointer_activity(event.globalPosition().toPoint())
        self._hovered = True
        self.hover_position = self.position_at(event.position())
        if self.dragging:
            self.preview_position = self.hover_position
            self.controls._refresh_time_label()
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._duration and self.controls._enabled():
            self.controls.pane.owner.select(self.controls.pane.state.id)
            self.controls.note_activity()
            self.dragging = True
            self._hovered = True
            self.preview_position = self.position_at(event.position())
            self.hover_position = self.preview_position
            self.controls.hide_timer.stop()
            self.controls._refresh_time_label()
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.controls.pane.context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            target = self.position_at(event.position())
            self.dragging = False
            self.preview_position = None
            if self.controls._enabled():
                self._position = target
                self.controls.pane.owner.playback.seek(self.controls.pane.state.id, target)
                self.controls.note_activity()
            self.controls._refresh_time_label()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # A double click on the timeline must not focus/maximize the video.
        event.accept()

    def keyPressEvent(self, event):
        keys = {Qt.Key.Key_Left: -5000, Qt.Key.Key_Right: 5000}
        if self._duration and event.key() in (*keys, Qt.Key.Key_Home, Qt.Key.Key_End):
            target = max(0, min(self._duration, self._position + keys.get(event.key(), 0)))
            if event.key() == Qt.Key.Key_Home:
                target = 0
            elif event.key() == Qt.Key.Key_End:
                target = self._duration
            self.controls.pane.owner.select(self.controls.pane.state.id)
            self.controls.pane.owner.playback.seek(self.controls.pane.state.id, target)
            self.controls.note_activity()
            event.accept()
            return
        super().keyPressEvent(event)


class HoverControls(QObject):
    """Manage a pane's hover title/timeline with a two-second inactivity timer.

    ``note_activity`` shows and restarts the timer; ``hide_now`` hides both.
    ``refresh`` synchronizes the source name, duration, position, and loop data.
    The parent should call refresh when its state changes; player signals and
    picture geometry changes are observed automatically.
    """

    def __init__(self, pane):
        super().__init__(pane)
        self.pane = pane
        self._disposed = False
        self._last_global: QPoint | None = None
        self._content_rect = QRect()
        self._visible = False
        self._title_key = None
        self._transport_state = None
        self._time_text_cache = None
        self._time_width = 95
        self._transport_layout_key = None
        self.title = _VideoTitle(pane)
        self.bar = SeekBar(self)
        self._held_controls = set()
        self._icons = {name: _transport_icon(name) for name in ("play", "pause", "volume", "muted")}
        self.play_button = QToolButton(self.bar)
        self.play_button.setObjectName("hoverPlayButton")
        self.play_button.setAccessibleName(tr('播放或暂停视频'))
        self.mute_button = QToolButton(self.bar)
        self.mute_button.setObjectName("hoverMuteButton")
        self.mute_button.setAccessibleName(tr('静音或取消静音'))
        for button in (self.play_button, self.mute_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            button.setStyleSheet("QToolButton { background: transparent; color: white; border: none; "
                                "border-radius: 4px; padding: 1px; } "
                                "QToolButton:hover { background: rgba(255,255,255,40); } "
                                "QToolButton:pressed { background: rgba(113,232,206,65); }")
            button.pressed.connect(lambda button=button: self._begin_interaction(button))
            button.released.connect(lambda button=button: self._end_interaction(button))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self.bar)
        self.volume_slider.setObjectName("hoverVolumeSlider")
        self.volume_slider.setAccessibleName(tr('视频音量'))
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume_slider.setStyleSheet(
            "QSlider { background: transparent; border: none; } "
            "QSlider::groove:horizontal { height: 3px; background: rgba(255,255,255,90); border-radius: 1px; } "
            "QSlider::sub-page:horizontal { background: #71e8ce; border-radius: 1px; } "
            "QSlider::handle:horizontal { background: white; width: 8px; margin: -3px 0; border-radius: 4px; }")
        self.volume_label = QLabel(self.bar)
        self.volume_label.setObjectName("hoverVolumeLabel")
        self.time_label = QLabel(self.bar)
        self.time_label.setObjectName("hoverTimeLabel")
        for label in (self.volume_label, self.time_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            label.setStyleSheet("background: transparent; border: none; color: #f1f7fc; font-size: 10px;")
        self.play_button.clicked.connect(self._toggle_play)
        self.mute_button.clicked.connect(self._toggle_mute)
        self.volume_slider.valueChanged.connect(self._volume_changed)
        self.volume_slider.sliderPressed.connect(lambda: self._begin_interaction(self.volume_slider))
        self.volume_slider.sliderReleased.connect(lambda: self._end_interaction(self.volume_slider))
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(2000)
        self.hide_timer.timeout.connect(self._timeout)
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self._check_pointer_outside)
        self._transport_widgets = (self.play_button, self.mute_button, self.volume_slider)
        self._targets = (pane, pane.canvas, pane.canvas.viewport(), *self._transport_widgets)
        for target in self._targets:
            target.setMouseTracking(True)
            target.installEventFilter(self)
        self.title.installEventFilter(self)
        self.time_label.installEventFilter(self)
        # Keep Python/QtWidgets work out of synchronous native media commands.
        # Slots are bound to this QObject, so deletion also cancels queued work.
        queued = Qt.ConnectionType.QueuedConnection
        pane.player.positionChanged.connect(self._position_changed, queued)
        pane.player.durationChanged.connect(self._duration_changed, queued)
        pane.player.playbackStateChanged.connect(self._refresh_transport, queued)
        pane.audio.volumeChanged.connect(self._refresh_transport, queued)
        pane.audio.mutedChanged.connect(self._refresh_transport, queued)
        pane.canvas.contentGeometryChanged.connect(self.refresh_geometry)
        self.title.hide()
        self.bar.hide()
        self.refresh()

    def _enabled(self) -> bool:
        return (not self._disposed and bool(self.pane.state.source)
                and not self.pane.canvas.crop_active and self.pane.isVisible())

    def isVisible(self) -> bool:
        return self._visible and self.bar.isVisible()

    def refresh(self) -> None:
        if self._disposed:
            return
        self.bar.set_media(self.pane.player.duration(), self.pane.player.position())
        self._refresh_transport()
        self.refresh_geometry()

    def _refresh_title(self) -> None:
        source = self.pane.state.source
        key = (source, self.title.width())
        if key == self._title_key:
            return
        previous = self._title_key
        self._title_key = key
        name = Path(source).name if source else ""
        text = self.title.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideMiddle, max(1, self.title.width() - 20))
        if self.title.text() != text:
            self.title.setText(text)
        if previous is None or source != previous[0]:
            self.title.setToolTip(source)

    def _refresh_time_label(self) -> None:
        if not hasattr(self, "time_label"):
            return
        position = self.bar.preview_position if self.bar.dragging else self.bar._position
        position = self.bar._position if position is None else position
        text = f"{_time_text(position)} / {_time_text(self.bar._duration)}"
        if text == self._time_text_cache:
            return
        self._time_text_cache = text
        self.time_label.setText(text)
        width = max(95, self.time_label.fontMetrics().horizontalAdvance(text) + 4)
        if width != self._time_width:
            self._time_width = width
            self._layout_transport()

    @Slot()
    def _refresh_transport(self, *_args) -> None:
        if self._disposed:
            return
        playing = self.pane.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        muted = self.pane.audio.isMuted()
        volume = round(self.pane.audio.volume() * 100)
        state = (playing, muted, volume)
        previous = self._transport_state
        if state == previous:
            return
        self._transport_state = state
        if previous is None or playing != previous[0]:
            self.play_button.setIcon(self._icons["pause" if playing else "play"])
            self.play_button.setToolTip(tr('暂停（空格）') if playing else tr('播放（空格）'))
            self.play_button.setProperty("playing", playing)
        if previous is None or (muted, volume == 0) != (previous[1], previous[2] == 0):
            self.mute_button.setIcon(self._icons["muted" if muted or volume == 0 else "volume"])
            self.mute_button.setToolTip(tr('取消静音') if muted else tr('静音'))
            self.mute_button.setProperty("muted", muted)
        if previous is None or volume != previous[2]:
            with QSignalBlocker(self.volume_slider):
                self.volume_slider.setValue(volume)
            self.volume_label.setText(f"{volume}%")
        if previous is None or (muted, volume) != previous[1:]:
            self.volume_slider.setToolTip(tr('音量 {value1}%', value1=f'{volume}') + (tr('（已静音）') if muted else ""))

    def _layout_transport(self) -> None:
        if not hasattr(self, "volume_slider"):
            return
        width, height = self.bar.width(), self.bar.height()
        key = (width, height, self._time_width)
        if key == self._transport_layout_key:
            return
        # Child setGeometry/show calls can generate more resize/show events.
        # Publish the key first so those events cannot recursively relayout.
        self._transport_layout_key = key
        margin = min(12, max(3, round(width * .055)))
        row_height = min(28, max(16, height // 2))
        row_y = max(0, height - row_height - 3)
        button_width = 28 if width >= 140 else 18
        gap = 4 if width >= 140 else 2
        x = margin
        for button in (self.play_button, self.mute_button):
            self._set_geometry(button, QRect(x, row_y, button_width, row_height))
            x += button_width + gap
        show_time = width >= 300
        show_percent = width >= 215
        time_width = self._time_width
        percent_width = 31 if show_percent else 0
        reserved = (time_width + 10 if show_time else 0) + percent_width + (5 if show_percent else 0)
        slider_width = max(8, min(94, width - margin - x - reserved))
        self._set_geometry(self.volume_slider, QRect(x, row_y, slider_width, row_height))
        x += slider_width + 5
        self._set_geometry(self.volume_label, QRect(x, row_y, percent_width, row_height))
        if self.volume_label.isHidden() == show_percent:
            self.volume_label.setVisible(show_percent)
        if show_percent:
            x += percent_width + 10
        self._set_geometry(self.time_label, QRect(x, row_y, max(0, width - margin - x), row_height))
        if self.time_label.isHidden() == show_time:
            self.time_label.setVisible(show_time)

    @staticmethod
    def _set_geometry(widget, rect: QRect) -> None:
        if widget.geometry() != rect:
            widget.setGeometry(rect)

    def _interaction_active(self) -> bool:
        return self.bar.dragging or bool(self._held_controls)

    def _begin_interaction(self, control) -> None:
        if not self._enabled():
            return
        self._held_controls.add(control)
        self.pane.owner.select(self.pane.state.id)
        self.note_activity()
        self.hide_timer.stop()

    def _end_interaction(self, control) -> None:
        self._held_controls.discard(control)
        if self._enabled():
            self.note_activity()
            if not self._interaction_active():
                self.hide_timer.start()

    def _toggle_play(self) -> None:
        if self._enabled():
            self.pane.toggle_play()
            self._refresh_transport()
            self.note_activity()

    def _toggle_mute(self) -> None:
        if self._enabled():
            self.pane.toggle_mute()
            self._refresh_transport()
            self.note_activity()

    def _volume_changed(self, value: int) -> None:
        if self._disposed or not self._enabled():
            return
        self.pane.owner.select(self.pane.state.id)
        self.pane.state.volume = value / 100
        media_command(self.pane.audio, "setVolume", value / 100)
        if value > 0:
            self.pane.state.muted = False
            media_command(self.pane.audio, "setMuted", False)
        self.pane.owner.refresh_inspector()
        self._refresh_transport()
        self.note_activity()

    def refresh_geometry(self) -> None:
        if self._disposed:
            return
        canvas = self.pane.canvas
        rect = canvas.video_content_rect()
        if rect is None:
            rect = canvas.viewport().rect()
        origin = canvas.viewport().mapTo(self.pane, QPoint(0, 0))
        picture = rect.translated(origin).intersected(self.pane.rect())
        if picture != self._content_rect:
            self._content_rect = picture
            title_height = min(30, max(16, picture.height() // 3))
            bar_height = min(74, max(20, picture.height() - title_height))
            self._set_geometry(self.title, QRect(picture.x(), picture.y(), picture.width(), title_height))
            self._set_geometry(self.bar, QRect(picture.x(), picture.bottom() - bar_height + 1,
                                               picture.width(), bar_height))
            if (self.bar.width(), self.bar.height(), self._time_width) != self._transport_layout_key:
                self._layout_transport()
        self._refresh_title()
        if not self._enabled() or picture.isEmpty():
            self.hide_now()

    def note_activity(self) -> None:
        if not self._enabled():
            self.hide_now()
            return
        # Once shown, pointer motion is only an inactivity update. Media
        # signals and explicit state refreshes already keep the widgets current.
        if not self._visible:
            self.refresh()
            if self._content_rect.isEmpty():
                return
            self._visible = True
            self.title.show()
            self.bar.show()
            self.title.raise_()
            self.bar.raise_()
        if not self._interaction_active():
            self.hide_timer.start()

    def _pointer_activity(self, global_point: QPoint) -> None:
        # Showing or hiding a child creates synthetic Enter events. A stationary
        # pointer must not resurrect the controls immediately after timeout.
        if self._last_global is not None and global_point == self._last_global:
            return
        self._last_global = QPoint(global_point)
        self.note_activity()

    def hide_now(self) -> None:
        self.hide_timer.stop()
        self._leave_timer.stop()
        if not self._visible and self.title.isHidden() and self.bar.isHidden():
            return
        self._visible = False
        self._held_controls.clear()
        self.bar.cancel_drag()
        self.title.hide()
        self.bar.hide()

    def _timeout(self) -> None:
        if not self._interaction_active():
            self.hide_now()

    @Slot("qint64")
    def _position_changed(self, position: int) -> None:
        if not self._disposed:
            # Hidden controls retain the clock but need no time formatting,
            # font measurement, QLabel mutation, or paint request. The next
            # explicit refresh/show flushes the latest data before painting.
            self.bar.set_media(self.bar._duration, position, update_widgets=self._visible)

    @Slot("qint64")
    def _duration_changed(self, duration: int) -> None:
        if not self._disposed:
            self.bar.set_media(duration, self.pane.player.position(), update_widgets=self._visible)

    def _schedule_leave_check(self) -> None:
        if not self._disposed:
            self._leave_timer.start(0)

    def _check_pointer_outside(self) -> None:
        if self._disposed or self._interaction_active():
            return
        position = QCursor.pos()
        hit = QApplication.widgetAt(position)
        in_picture = self._content_rect.contains(self.pane.mapFromGlobal(position))
        in_pane = hit is self.pane or (hit is not None and self.pane.isAncestorOf(hit))
        if not in_picture or not in_pane:
            self.hide_now()
            # A later real entry may occur at the exact pixel of the last
            # visit. Only an actual leave clears this guard; timeout does not.
            self._last_global = None

    def eventFilter(self, watched, event):
        if self._disposed:
            return False
        kind = event.type()
        if kind in (QEvent.Type.Enter, QEvent.Type.MouseMove):
            point = (event.globalPosition().toPoint() if hasattr(event, "globalPosition")
                     else QCursor.pos())
            if self._content_rect.contains(self.pane.mapFromGlobal(point)):
                self._pointer_activity(point)
            if watched in self._transport_widgets:
                # Hovering transport controls is separate from timeline seek
                # preview; child mouse input must not bubble into the layer.
                self.bar._hovered = False
                self.bar.hover_position = None
                self.bar.update()
        elif kind == QEvent.Type.MouseButtonPress and watched in self._transport_widgets:
            if event.button() == Qt.MouseButton.LeftButton:
                self._begin_interaction(watched)
        elif kind == QEvent.Type.MouseButtonRelease and watched in self._transport_widgets:
            if event.button() == Qt.MouseButton.LeftButton:
                self._end_interaction(watched)
        elif kind == QEvent.Type.Leave:
            self._schedule_leave_check()
        elif (kind in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Move)
              and watched in self._targets[:3] and not (kind == QEvent.Type.Move and watched is self.pane)):
            self.refresh_geometry()
        elif kind in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            if watched is self.title:
                self._title_key = None
                self._refresh_title()
            elif watched is self.time_label:
                self._time_text_cache = None
                self._refresh_time_label()
        elif kind == QEvent.Type.Hide and watched is self.pane:
            self.hide_now()
        return False

    def dispose(self) -> None:
        self.hide_now()
        self._disposed = True
        for target in self._targets:
            target.removeEventFilter(self)
        self.title.deleteLater()
        self.bar.deleteLater()

