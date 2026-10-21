from __future__ import annotations

from . import i18n
from .i18n import tr

import argparse
import json
import os
import sys
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QColor, QDrag, QFont, QIcon, QKeySequence, QPainter, QPalette, QPen, QPixmap, QPolygon, QRegion, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QScrollArea, QSlider, QSplitter, QStyle,
    QToolButton, QVBoxLayout, QWidget,
)

from .canvas import VideoCanvas
from .model import PaneState, decode_session, encode_session, leaf_ids, make_layout, remove_leaf, split_leaf, swap_leaves
from .playback import PlaybackController
from .free_canvas import FreeCanvas
from .hover_controls import HoverControls
from .media_commands import media_command
from . import __version__

VIDEO_FILTER = "视频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.wmv *.m4v *.mpg *.mpeg *.ts *.mts *.m2ts *.flv *.gif);;所有文件 (*)"
SESSION_FILTER = "GridStudio 工作区 (*.gstudio);;JSON (*.json)"
PANE_MIME = "application/x-gridstudio-pane"
FIT_MODES = [("保持原比例（完整显示）", "contain"), ("等比铺满（裁切边缘）", "cover"), ("拉伸填满（不裁切）", "stretch")]

STYLE = """
QWidget { background: #11161d; color: #dbe3ee; font-size: 12px; }
QLabel, QCheckBox { background: transparent; }
QMainWindow { background: #11161d; }
QFrame#top { background: #181f29; border-bottom: 1px solid #2c3644; }
QLabel#brand { font-size: 23px; font-weight: 700; color: #f4f7fb; }
QLabel#sub { color: #8795a9; font-size: 11px; }
QLabel#section { color: #7e91a8; font-size: 11px; font-weight: 600; }
QPushButton, QToolButton { background: #242e3c; border: 1px solid #354153; border-radius: 6px; padding: 6px 11px; }
QPushButton:hover, QToolButton:hover { background: #324156; border-color: #60738f; }
QPushButton:pressed, QToolButton:pressed { background: #1c5960; }
QPushButton#primary { background: #52d3ba; border-color: #52d3ba; color: #0e2624; font-weight: 600; }
QPushButton#primary:hover { background: #7ae4cf; }
QPushButton:disabled, QToolButton:disabled { color: #5d6a7c; background: #1a222c; border-color: #28313e; }
QToolButton { padding: 4px 7px; }
QFrame#pane { background: #0b1017; border: 1px solid #303b4a; border-radius: 6px; }
QFrame#pane[selected="true"] { border: 2px solid #52d3ba; }
QWidget#paneHeader { background: #1b2430; border: none; border-radius: 4px; }
QWidget#paneControls { background: #171e28; border: none; }
QLabel#paneTitle { background: transparent; color: #d4deec; font-weight: 600; }
QLabel#badge { background: #28463f; color: #83e4ce; border-radius: 3px; padding: 2px 5px; font-size: 10px; }
QFrame#inspector { background: #181f29; border: 1px solid #2d3747; border-radius: 8px; }
QComboBox, QDoubleSpinBox { background: #202a37; border: 1px solid #3a475a; border-radius: 5px; padding: 5px 7px; min-height: 20px; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background: #202a37; selection-background-color: #34665f; }
QSlider::groove:horizontal { height: 4px; background: #354153; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #52d3ba; border-radius: 2px; }
QSlider::handle:horizontal { background: #d3fff6; width: 10px; margin: -3px 0; border-radius: 5px; }
QSplitter::handle { background: #202a36; }
QSplitter::handle:hover { background: #52d3ba; }
QCheckBox { spacing: 7px; }
QMenu { background: #202a37; border: 1px solid #3a475a; padding: 5px; }
QMenu::item { padding: 7px 24px 7px 12px; border-radius: 3px; }
QMenu::item:selected { background: #35675f; }
QStatusBar { background: #181f29; color: #95a6bb; }
QStatusBar::item { border: none; }
QToolTip { background: #2b3748; color: #eef5ff; border: 1px solid #506079; padding: 5px; }
QScrollArea { border: none; }
"""


def app_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor("#171f29"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#52d3ba"))
    p.drawRoundedRect(9, 9, 25, 46, 4, 4)
    p.drawRoundedRect(39, 9, 16, 21, 3, 3)
    p.setBrush(QColor("#6f859f"))
    p.drawRoundedRect(39, 35, 16, 20, 3, 3)
    p.end()
    return QIcon(pix)


def media_icon(name):
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#dbe8f6")
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    if name == "play":
        painter.drawPolygon(QPolygon([QPoint(5, 3), QPoint(17, 10), QPoint(5, 17)]))
    elif name == "pause":
        painter.drawRoundedRect(4, 3, 4, 14, 1, 1)
        painter.drawRoundedRect(12, 3, 4, 14, 1, 1)
    else:
        painter.drawPolygon(QPolygon([QPoint(2, 7), QPoint(6, 7), QPoint(11, 3), QPoint(11, 17), QPoint(6, 13), QPoint(2, 13)]))
        painter.setPen(QPen(color, 1.7))
        if name == "muted":
            painter.drawLine(14, 7, 19, 13)
            painter.drawLine(19, 7, 14, 13)
        else:
            painter.drawArc(8, 3, 10, 14, -70 * 16, 140 * 16)
    painter.end()
    return QIcon(pix)


def button(text, callback, tooltip="", primary=False):
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setToolTip(tooltip)
    if primary:
        b.setObjectName("primary")
    b.clicked.connect(callback)
    return b


def time_text(ms):
    seconds = max(0, int(ms)) // 1000
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"
    return f"{seconds // 60:02}:{seconds % 60:02}"


class PaneHeader(QWidget):
    def __init__(self, pane):
        super().__init__(pane)
        self.pane = pane
        self.origin = None
        self.setObjectName("paneHeader")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(tr('拖动标题栏到另一个窗格可交换位置'))
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 6, 5)
        row.setSpacing(5)
        grip = QLabel("⠿")
        grip.setStyleSheet("color: #718198; font-size: 18px;")
        grip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(grip)
        self.title = QLabel(tr('空白窗格'))
        self.title.setProperty("i18nUserText", True)
        self.title.setObjectName("paneTitle")
        self.title.setMinimumWidth(30)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.title, 1)
        self.badge = QLabel("")
        self.badge.setObjectName("badge")
        self.badge.hide()
        row.addWidget(self.badge)
        self.copy_button = QToolButton()
        self.copy_button.setText("⧉")
        self.copy_button.setToolTip(tr('复制窗格，保留进度 / 裁剪 / 旋转（Ctrl+D）'))
        self.copy_button.clicked.connect(lambda: pane.owner.duplicate(pane.state.id))
        row.addWidget(self.copy_button)
        more = QToolButton()
        more.setText("···")
        more.setToolTip(tr('窗格操作'))
        more.clicked.connect(lambda: pane.context_menu(more.mapToGlobal(QPoint(0, more.height()))))
        row.addWidget(more)
        close = QToolButton()
        close.setText("×")
        close.setToolTip(tr('关闭窗格'))
        close.clicked.connect(lambda: pane.owner.remove_pane(pane.state.id))
        row.addWidget(close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.pane.owner.select(self.pane.state.id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self.origin).manhattanLength() >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(PANE_MIME, self.pane.state.id.encode())
                drag.setMimeData(mime)
                drag.setPixmap(self.grab())
                self.origin = None
                drag.exec(Qt.DropAction.MoveAction)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.origin = None
        super().mouseReleaseEvent(event)


class VideoPane(QFrame):
    def __init__(self, owner, state):
        super().__init__(owner.pane_parking)
        self.owner = owner
        self.state = state
        self.setObjectName("pane")
        self.setAcceptDrops(True)
        self.setMinimumSize(220, 180)
        self._restoring = False
        self._pending_restore = False
        self._source_generation = 0
        self._restore_queued = False
        self._disposed = False
        self._duration_ms = 0
        self._time_text = "00:00 / 00:00"
        col = QVBoxLayout(self)
        col.setContentsMargins(2, 2, 2, 2)
        col.setSpacing(0)
        self.header = PaneHeader(self)
        col.addWidget(self.header)
        self.canvas = VideoCanvas()
        col.addWidget(self.canvas, 1)
        self.canvas.contentGeometryChanged.connect(self.update_content_mask)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.canvas.video_item)
        # Native seek/control calls can emit these synchronously. Update Qt
        # widgets after the native command returns, outside its decoder stack.
        self.player.positionChanged.connect(self.on_position, Qt.ConnectionType.QueuedConnection)
        self.player.durationChanged.connect(self.on_duration, Qt.ConnectionType.QueuedConnection)
        self.player.playbackStateChanged.connect(self.on_playback, Qt.ConnectionType.QueuedConnection)
        self.player.mediaStatusChanged.connect(self.on_status)
        self.player.errorOccurred.connect(self.on_error)
        self.canvas.activated.connect(lambda: owner.select(state.id))
        self.canvas.doubleClicked.connect(lambda: owner.toggle_focus(state.id))
        self.canvas.cropSelected.connect(self.on_crop)
        self.canvas.filesDropped.connect(lambda paths: owner.add_files(paths, None if owner.layout_mode == "canvas" else state.id))
        self.canvas.contextRequested.connect(self.context_menu)
        controls = QWidget()
        self.controls = controls
        controls.setObjectName("paneControls")
        controls_col = QVBoxLayout(controls)
        controls_col.setContentsMargins(9, 5, 9, 7)
        controls_col.setSpacing(5)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.setToolTip(tr('拖动定位'))
        self.timeline.sliderReleased.connect(lambda: owner.playback.seek(self.state.id, self.timeline.value()))
        controls_col.addWidget(self.timeline)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.play_button = QToolButton()
        self.play_button.setIcon(media_icon("play"))
        self.play_button.setToolTip(tr('播放 / 暂停（空格）'))
        self.play_button.clicked.connect(self.toggle_play)
        row.addWidget(self.play_button)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #a0afc2; font-size: 11px;")
        row.addWidget(self.time_label)
        row.addStretch()
        self.mute_button = QToolButton()
        self.mute_button.clicked.connect(self.toggle_mute)
        row.addWidget(self.mute_button)
        self.speed_label = QLabel("1×")
        self.speed_label.setStyleSheet("color: #8193aa; font-size: 11px;")
        row.addWidget(self.speed_label)
        controls_col.addLayout(row)
        col.addWidget(controls)
        self.apply_state()
        self.set_clean_mode(owner.clean_mode)
        self.hover_controls = HoverControls(self)
        if state.source:
            self.load_source()

    def set_clean_mode(self, clean):
        floating = self.owner.layout_mode == "canvas"
        video_only = clean or floating
        self.header.setVisible(not video_only)
        self.controls.setVisible(not video_only)
        self.layout().setContentsMargins(*((0, 0, 0, 0) if video_only else (2, 2, 2, 2)))
        if floating:
            self.setMinimumSize(40, 30)
            self.canvas.setMinimumSize(1, 1)
        else:
            self.setMinimumSize(100, 80) if clean else self.setMinimumSize(220, 180)
        self.setStyleSheet('QFrame#pane, QFrame#pane[selected="true"] { border: none; border-radius: 0; background: #000; }' if video_only else "")
        self.canvas.setBackgroundBrush(QColor("#000000" if video_only else "#0b1018"))
        self.canvas.set_fill_mode(self.state.fit_mode)
        self.update_content_mask()
        if controls := getattr(self, "hover_controls", None):
            controls.hide_now()
        if not video_only:
            self.refresh_header(refresh_hover=False)

    def update_content_mask(self):
        """Canvas letterbox is empty space, so it must not cover other layers.

        Masking the whole pane also lets pointer input reach the video below.
        The stored layer geometry and the video's pixels remain unchanged.
        """
        rect = self.canvas.video_content_rect()
        if (self.owner.layout_mode == "canvas" and not self.owner.focus_id
                and self.canvas.fill_mode == "contain" and rect is not None and not rect.isEmpty()):
            origin = self.canvas.viewport().mapTo(self, QPoint(0, 0))
            region = QRegion(rect.translated(origin))
            if self.mask() != region:
                self.setMask(region)
        elif not self.mask().isEmpty():
            self.clearMask()

    def snapshot(self):
        if not self._pending_restore:
            self.state.position_ms = self.player.position()
            self.state.paused = self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        return self.state

    def load_source(self):
        self._source_generation += 1
        self._restore_queued = False
        self._pending_restore = True
        self.owner.playback.refresh_activity()
        src = self.state.source
        self.canvas.set_has_media(True)
        self.canvas.set_message("")
        media_command(self.player, "setSource", QUrl(src) if src.startswith(("http://", "https://", "rtsp://")) else QUrl.fromLocalFile(src))
        # Qt does not re-emit LoadedMedia when the same URL is reopened.
        if self.player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.on_status(self.player.mediaStatus())
        self.refresh_header()

    def on_status(self, status):
        if self._pending_restore and status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if not self._restore_queued:
                self._restore_queued = True
                generation = self._source_generation
                # Leave the decoder's media-status signal before seeking or
                # coordinating other players. Reentrant FFmpeg seeks can lock.
                QTimer.singleShot(0, lambda: self.finish_restore(generation))
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self.state.loop:
            self.state.paused = True
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            QTimer.singleShot(0, self.owner.playback.tick)

    def finish_restore(self, generation):
        if generation != self._source_generation or not self._pending_restore:
            return
        self._restore_queued = False
        self._pending_restore = False
        if self.player.position() != self.state.position_ms:
            media_command(self.player, "setPosition", self.state.position_ms)
        if self.state.paused:
            media_command(self.player, "pause")
        else:
            media_command(self.player, "play")
        self.owner.playback.media_ready(self.state.id)
        self.owner.playback.refresh_activity()

    def on_error(self, _error, message):
        if self.player.error() != QMediaPlayer.Error.NoError:
            self.canvas.set_message(tr('无法播放此视频\n{message}\n可尝试其他编码的视频文件', message=message))
            self.owner.notify(tr('视频打开失败：{message}', message=message))

    def apply_state(self):
        self.canvas.set_transform(self.state.crop, self.state.rotation, self.state.flip_h, self.state.flip_v)
        self.canvas.set_fill_mode(self.state.fit_mode)
        media_command(self.audio, "setVolume", self.state.volume)
        media_command(self.audio, "setMuted", self.state.muted)
        if abs(self.player.playbackRate() - self.state.rate) > 1e-9:
            media_command(self.player, "setPlaybackRate", self.state.rate)
        native_loop = self.state.loop and self.state.loop_start_ms == 0 and self.state.loop_end_ms is None and not self.state.sync_group
        loops = QMediaPlayer.Loops.Infinite if native_loop else QMediaPlayer.Loops.Once
        if self.player.loops() != loops:
            self.player.setLoops(loops)
        self.mute_button.setIcon(media_icon("muted" if self.state.muted else "volume"))
        self.mute_button.setToolTip(tr('取消静音') if self.state.muted else tr('静音'))
        self.speed_label.setText(f"{self.state.rate:g}×")
        self.refresh_header()

    def refresh_header(self, *, refresh_hover=True):
        name = Path(self.state.source).name if self.state.source else tr('空白窗格')
        metrics = self.header.title.fontMetrics()
        self.header.title.setText(metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, max(40, self.header.title.width())))
        self.header.title.setToolTip(self.state.source or tr('双击画面聚焦；右键打开视频'))
        badges = []
        if tuple(self.state.crop) != (0, 0, 1, 1):
            badges.append(tr('裁剪'))
        if self.state.rotation:
            badges.append(f"{self.state.rotation}°")
        if self.state.flip_h or self.state.flip_v:
            badges.append(tr('镜像'))
        if self.state.loop and self.state.loop_end_ms is not None:
            badges.append("A/B")
        if self.state.sync_group:
            badges.append(tr('同步 ') + self.state.sync_group)
        self.header.badge.setText(" · ".join(badges))
        self.header.badge.setVisible(bool(badges))
        if refresh_hover and (controls := getattr(self, "hover_controls", None)):
            controls.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.header.isHidden():
            self.refresh_header(refresh_hover=False)
        # HoverControls already follows pane/viewport resize and video geometry.

    @Slot("qint64")
    def on_position(self, pos):
        if self._disposed:
            return
        if not self.timeline.isSliderDown():
            self.timeline.setValue(pos)
        text = f"{time_text(pos)} / {time_text(self._duration_ms)}"
        if text != self._time_text:
            self._time_text = text
            self.time_label.setText(text)

    @Slot("qint64")
    def on_duration(self, duration):
        if self._disposed:
            return
        self._duration_ms = duration
        self.timeline.setRange(0, duration)
        self.on_position(self.player.position())

    @Slot(QMediaPlayer.PlaybackState)
    def on_playback(self, state):
        if self._disposed:
            return
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(media_icon("pause" if playing else "play"))

    def toggle_play(self):
        self.owner.select(self.state.id)
        if not self.state.source:
            self.owner.open_files(self.state.id)
            return
        playing = self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        self.owner.playback.set_playing(self.state.id, playing)

    def toggle_mute(self):
        self.owner.select(self.state.id)
        self.state.muted = not self.state.muted
        self.apply_state()
        self.owner.refresh_inspector()

    def on_crop(self, crop):
        self.state.crop = tuple(crop)
        self.apply_state()
        self.owner.refresh_inspector()
        self.owner.notify(tr('已裁剪。复制窗格会保留当前裁剪区域。'))

    def context_menu(self, point):
        self.owner.select(self.state.id)
        menu = self.owner.create_context_menu(self.state.id)
        menu.exec(point)
        menu.deleteLater()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PANE_MIME) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat(PANE_MIME):
            other = bytes(mime.data(PANE_MIME)).decode()
            if other in self.owner.panes:
                self.owner.swap(other, self.state.id)
            event.acceptProposedAction()
        elif mime.hasUrls():
            self.owner.add_files([u.toLocalFile() for u in mime.urls() if u.isLocalFile()], None if self.owner.layout_mode == "canvas" else self.state.id)
            event.acceptProposedAction()

    def dispose(self):
        self._disposed = True
        self.owner.playback.refresh_activity()
        self._source_generation += 1
        self.hover_controls.dispose()
        media_command(self.player, "stop")
        media_command(self.player, "setSource", QUrl())
        self.player.setVideoOutput(None)
        self.deleteLater()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        i18n.initialize()
        self.setWindowTitle(tr('GridStudio · 多画面播放器'))
        self.setWindowIcon(app_icon())
        self.resize(1460, 920)
        self.setMinimumSize(1020, 640)
        self.panes = {}
        # Live video widgets always remain children of this window, even while
        # rebuilding a layout or focusing another layer. A parentless show()
        # would create a temporary native window and disrupt its video surface.
        self.pane_parking = QWidget(self)
        self.pane_parking.hide()
        self.tree = None
        self.active_id = None
        self.focus_id = None
        self.root_widget = None
        self.session_path = None
        self._updating = False
        self._inspector_state = None
        self._selected_pane = None
        self._split_nodes = []
        self._layout_generation = 0
        self.clean_mode = True
        self.layout_mode = "canvas"
        self.canvas_workspace = None
        self.playback = PlaybackController(self)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QFrame()
        self.top_panel = top
        top.setObjectName("top")
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(22, 14, 22, 14)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(42, 42))
        top_row.addWidget(logo)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel("GridStudio")
        brand.setObjectName("brand")
        brand_col.addWidget(brand)
        sub = QLabel(tr('每个画面，都有自己的位置'))
        sub.setObjectName("sub")
        brand_col.addWidget(sub)
        top_row.addLayout(brand_col)
        top_row.addStretch()
        top_row.addWidget(button(tr('＋ 添加视频'), self.open_files, tr('打开本地视频，可多选（Ctrl+O）'), True))
        top_row.addWidget(button(tr('打开工作区'), self.load_dialog, tr('恢复保存的布局和视频状态（Ctrl+Shift+O）')))
        top_row.addWidget(button(tr('保存工作区'), self.save_dialog, tr('保存布局、进度和画面变换（Ctrl+S）')))
        help_button = button("？", self.show_help, tr('使用说明和快捷键'))
        help_button.setFixedWidth(35)
        top_row.addWidget(help_button)
        outer.addWidget(top)
        tools = QWidget()
        self.tools_panel = tools
        tools_row = QHBoxLayout(tools)
        tools_row.setContentsMargins(18, 10, 18, 10)
        tools_row.setSpacing(8)
        tools_row.addWidget(QLabel(tr('布局')))
        self.layout_combo = QComboBox()
        self.layout_combo.setMinimumWidth(135)
        for label, key in [(tr('自由画布'), "canvas"), (tr('自定义网格'), "custom"), (tr('等宽竖列'), "columns"), (tr('等高横行'), "rows"), (tr('两列网格'), "grid4"), (tr('三列网格'), "grid9"), (tr('主画面在左'), "focus-left"), (tr('主画面在上'), "focus-top")]:
            self.layout_combo.addItem(label, key)
        self.layout_combo.activated.connect(self.preset_selected)
        tools_row.addWidget(self.layout_combo)
        tools_row.addWidget(button(tr('左右拆分'), lambda: self.add_blank(axis="horizontal"), tr('在选中窗格右侧添加空白窗格')))
        tools_row.addWidget(button(tr('上下拆分'), lambda: self.add_blank(axis="vertical"), tr('在选中窗格下方添加空白窗格')))
        tools_row.addWidget(button(tr('⧉ 复制窗格'), lambda: self.duplicate(), tr('复制当前视频和全部变换（Ctrl+D）')))
        tools_row.addWidget(button(tr('位置 / 大小'), self.layer_rect_dialog, tr('精确设置当前画面的坐标和尺寸')))
        tools_row.addStretch()
        tools_row.addWidget(button(tr('全部播放'), lambda: self.play_all(True)))
        tools_row.addWidget(button(tr('全部暂停'), lambda: self.play_all(False)))
        self.focus_button = button(tr('聚焦'), lambda: self.toggle_focus(), tr('聚焦选中窗格 / 返回布局（F）'))
        tools_row.addWidget(self.focus_button)
        outer.addWidget(tools)
        body = QHBoxLayout()
        self.body_layout = body
        body.setContentsMargins(18, 0, 18, 12)
        body.setSpacing(12)
        self.stage = QWidget()
        self.stage_layout = QVBoxLayout(self.stage)
        self.stage_layout.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.stage, 1)
        self.inspector = self.create_inspector()
        body.addWidget(self.inspector)
        outer.addLayout(body, 1)
        self.count_label = QLabel()
        self.statusBar().addPermanentWidget(self.count_label)
        self.notify(tr('拖入视频开始 · 拖动分隔线调整大小 · 拖动标题栏交换位置'), 0)
        self.install_shortcuts()
        states = [PaneState()]
        for state in states:
            self.panes[state.id] = VideoPane(self, state)
        self.tree = make_layout([s.id for s in states], "grid")
        self.active_id = states[0].id
        self.rebuild()
        self.layout_combo.setCurrentIndex(0)
        self.set_clean_mode(True)
        i18n.events.changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        """Update only presentation; preserve decoder, transform and playback state."""
        i18n.retranslate_widgets(self)
        self._inspector_state = None
        self.refresh_inspector()
        self.count_label.setText(tr('{value0} 个画面  ·  GridStudio {value2}', value0=f'{len(self.panes)}', value2=f'{__version__}'))
        previous_message = self.statusBar().currentMessage()
        message = i18n.translated_existing(previous_message)
        if message != previous_message:
            remaining = (max(1, round((self._notification_deadline - monotonic()) * 1000))
                         if self._notification_deadline is not None else 0)
            self.statusBar().showMessage(message, remaining)
        for pane in self.panes.values():
            pane.refresh_header()
            pane.mute_button.setToolTip(tr('取消静音') if pane.state.muted else tr('静音'))
            pane.hover_controls._transport_state = None
            pane.hover_controls._refresh_transport()
            pane.canvas.retranslate_ui()

    def set_clean_mode(self, clean):
        """Keep playback controls out of the picture until explicitly requested."""
        self.capture_sizes()
        self.clean_mode = bool(clean)
        panels = not clean and self.layout_mode == "grid"
        self.top_panel.setVisible(panels)
        self.tools_panel.setVisible(panels)
        self.inspector.setVisible(panels)
        self.statusBar().setVisible(panels)
        self.body_layout.setContentsMargins(*((18, 0, 18, 12) if panels else (0, 0, 0, 0)))
        self.body_layout.setSpacing(12 if panels else 0)
        self.setMinimumSize(1020, 640) if panels else self.setMinimumSize(480, 270)
        for pane in self.panes.values():
            pane.set_clean_mode(clean)
        for splitter, _node in self._split_nodes:
            self.style_splitter(splitter)
        if self.canvas_workspace:
            self.canvas_workspace.set_editing(not clean)
        self.select(self.active_id)

    def toggle_clean_mode(self):
        self.set_clean_mode(not self.clean_mode)

    def style_splitter(self, splitter):
        splitter.setHandleWidth(0 if self.clean_mode else 7)
        splitter.setStyleSheet("QSplitter::handle, QSplitter::handle:hover { background: #000; }" if self.clean_mode else "")

    def apply_preset(self, index):
        self.layout_combo.setCurrentIndex(index)
        self.preset_selected(index)

    def set_layout_mode(self, mode):
        if mode not in ("canvas", "grid"):
            return
        if mode == self.layout_mode and not self.focus_id:
            return
        if mode == "canvas" and self.layout_mode == "grid" and self.focus_id:
            self.focus_id = None
            self.rebuild()
            self.stage_layout.activate()
            for splitter, node in reversed(self._split_nodes):
                available, total = max(1, sum(splitter.sizes())), sum(node["sizes"])
                splitter.setSizes([max(1, round(available * value / total)) for value in node["sizes"]])
        if mode == "canvas" and self.layout_mode == "grid":
            width, height = max(1, self.stage.width()), max(1, self.stage.height())
            for pane in self.panes.values():
                if pane.state.canvas_rect is None:
                    point = pane.mapTo(self.stage, QPoint(0, 0))
                    pane.state.canvas_rect = (point.x() / width, point.y() / height, pane.width() / width, pane.height() / height)
        self.capture_sizes()
        self.focus_id = None
        self.layout_mode = mode
        self.layout_combo.setCurrentIndex(self.layout_combo.findData("canvas" if mode == "canvas" else "custom"))
        for pane in self.panes.values():
            pane.set_clean_mode(self.clean_mode)
        self.rebuild()
        self.set_clean_mode(self.clean_mode)

    def new_canvas_rect(self, index=None):
        width = .48
        height = min(.65, width * max(1, self.stage.width()) / max(1, self.stage.height()) / (16 / 9))
        step = ((len(self.panes) - 1 if index is None else index) % 6) * .045
        return (.09 + step, .09 + step, width, max(.12, height))

    def raise_new_layer(self, state, original=None):
        # Preserve relative order while keeping serialized layer ranks bounded.
        for rank, pane in enumerate(sorted(self.panes.values(), key=lambda p: p.state.z_order)):
            pane.state.z_order = rank
        state.z_order = len(self.panes)
        if original and original.canvas_rect:
            x, y, width, height = original.canvas_rect
            dx, dy = 24 / max(1, self.stage.width()), 24 / max(1, self.stage.height())
            state.canvas_rect = (min(.95, x + dx), min(.95, y + dy), width, height)
        else:
            state.canvas_rect = self.new_canvas_rect()

    def move_layer(self, action):
        self.ensure_canvas_workspace()
        if self.canvas_workspace and self.active_id:
            self.canvas_workspace.move_layer(self.active_id, action)

    def ensure_canvas_workspace(self):
        if self.layout_mode != "canvas":
            self.set_layout_mode("canvas")
        elif self.focus_id:
            self.focus_id = None
            self.rebuild()

    def fill_canvas(self):
        self.ensure_canvas_workspace()
        if self.canvas_workspace:
            self.canvas_workspace.set_rect(self.active_id, (0, 0, 1, 1))

    def nudge_layer(self, dx, dy):
        if self.canvas_workspace and not self.clean_mode:
            self.canvas_workspace.nudge(self.active_id, dx, dy)

    def layer_rect_dialog(self):
        if not self.active():
            return
        self.ensure_canvas_workspace()
        if not self.canvas_workspace:
            return
        stage = self.canvas_workspace
        width, height = max(1, stage.width()), max(1, stage.height())
        x, y, w, h = self.active().state.canvas_rect
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('画面位置与大小'))
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        fields = []
        for label, value, minimum, maximum in [
            ("X", x * width, -width, 2 * width), ("Y", y * height, -height, 2 * height),
            (tr('宽度'), w * width, 40, 3 * width), (tr('高度'), h * height, 30, 3 * height),
        ]:
            field = QDoubleSpinBox()
            field.setDecimals(1)
            field.setRange(minimum, maximum)
            field.setValue(value)
            field.setSuffix(" px")
            form.addRow(label, field)
            fields.append(field)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = [f.value() for f in fields]
            stage.set_rect(self.active_id, (values[0] / width, values[1] / height, values[2] / width, values[3] / height))

    def create_context_menu(self, pane_id=None):
        if pane_id in self.panes:
            self.select(pane_id)
        pane = self.active()
        menu = QMenu(self)
        # Keep Python wrappers for nested menus alive while the popup is open.
        # Otherwise PySide can delete deeper submenus during wrapper collection.
        menu._submenus = []
        def submenu(parent, title):
            child = parent.addMenu(title)
            menu._submenus.append(child)
            return child
        menu.addAction(tr('添加视频…\tCtrl+O'), self.open_files)
        menu.addAction(tr('替换当前视频…'), lambda: self.open_files(self.active_id))
        menu.addAction(tr('播放 / 暂停\tSpace'), pane.toggle_play)
        menu.addAction(tr('复制窗格\tCtrl+D'), self.duplicate)
        menu.addAction(tr('关闭窗格\tCtrl+W'), lambda: self.remove_pane(self.active_id))
        menu.addSeparator()
        playback = submenu(menu, tr('播放'))
        playback.addAction(tr('全部播放'), lambda: self.play_all(True))
        playback.addAction(tr('全部暂停'), lambda: self.play_all(False))
        mute = playback.addAction(tr('静音\tM'))
        mute.setCheckable(True)
        mute.setChecked(pane.state.muted)
        mute.triggered.connect(pane.toggle_mute)
        speed = submenu(playback, tr('速度'))
        for value in [.25, .5, .75, 1., 1.25, 1.5, 2., 3., 4.]:
            action = speed.addAction(f"{value:g}×")
            action.setCheckable(True)
            action.setChecked(pane.state.rate == value)
            action.triggered.connect(lambda checked=False, rate=value: self.set_playback_rate(rate))
        picture = submenu(menu, tr('画面'))
        fit = submenu(picture, tr('显示方式'))
        for label, mode in FIT_MODES:
            action = fit.addAction(tr(label))
            action.setCheckable(True)
            action.setChecked(pane.state.fit_mode == mode)
            action.triggered.connect(lambda checked=False, mode=mode: self.set_fit_mode(mode))
        fit.addSeparator()
        fit.addAction(tr('将当前方式应用到全部窗格'), lambda: self.set_fit_mode(self.active().state.fit_mode, all_panes=True))
        picture.addSeparator()
        picture.addAction(tr('框选裁剪\tC'), self.start_crop)
        picture.addAction(tr('顺时针旋转 90°\tR'), lambda: self.rotate())
        picture.addAction(tr('逆时针旋转 90°'), lambda: self.rotate(-90))
        for label, field in [(tr('水平镜像'), "flip_h"), (tr('垂直镜像'), "flip_v")]:
            action = picture.addAction(label)
            action.setCheckable(True)
            action.setChecked(getattr(pane.state, field))
            action.triggered.connect(lambda checked=False, field=field: self.toggle_mirror(field))
        picture.addAction(tr('重置画面'), self.reset_transform)
        layers = submenu(menu, tr('图层'))
        layers.addAction(tr('置于顶层\tCtrl+Shift+]'), lambda: self.move_layer("front"))
        layers.addAction(tr('上移一层\tCtrl+]'), lambda: self.move_layer("forward"))
        layers.addAction(tr('下移一层\tCtrl+['), lambda: self.move_layer("backward"))
        layers.addAction(tr('置于底层\tCtrl+Shift+['), lambda: self.move_layer("back"))
        layers.addSeparator()
        layers.addAction(tr('位置与大小…'), self.layer_rect_dialog)
        layers.addAction(tr('铺满整个画布'), self.fill_canvas)
        selection = submenu(layers, tr('选中图层'))
        for index, layer in enumerate(sorted(self.panes.values(), key=lambda p: p.state.z_order, reverse=True)):
            label = f"{index + 1}. " + (Path(layer.state.source).name if layer.state.source else tr('空白画面'))
            action = selection.addAction(label)
            action.setCheckable(True)
            action.setChecked(layer.state.id == self.active_id)
            action.triggered.connect(lambda checked=False, pid=layer.state.id: self.select(pid))
        loops = submenu(menu, tr('循环'))
        loop_switch = loops.addAction(tr('启用循环\tL'))
        loop_switch.setCheckable(True)
        loop_switch.setChecked(pane.state.loop)
        loop_switch.triggered.connect(lambda checked=False: self.toggle_loop())
        loops.addAction(tr('整个视频循环'), lambda: self.playback.set_loop(self.active_id, True, start_ms=0, end_ms=None))
        loops.addAction(tr('设 A 点：当前进度\t['), self.set_loop_a)
        loops.addAction(tr('设 B 点并循环\t]'), self.set_loop_b)
        loops.addAction(tr('设置 A/B 循环区间…'), self.loop_dialog)
        loops.addAction(tr('清除 A/B 标记'), lambda: self.playback.clear_loop(self.active_id))
        info = loops.addAction(f"A {pane.state.loop_start_ms / 1000:.3f}s  /  B " + (f"{pane.state.loop_end_ms / 1000:.3f}s" if pane.state.loop_end_ms is not None else tr('未设置')))
        info.setEnabled(False)
        sync = submenu(menu, tr('同步'))
        sync.addAction(tr('同步全部视频（按时间）\tCtrl+G'), self.sync_all)
        sync.addAction(tr('同步全部视频（按百分比）'), lambda: self.sync_all(mode="percent"))
        sync.addAction(tr('同步全部视频（保留时间差）'), lambda: self.sync_all(preserve_offsets=True))
        sync.addSeparator()
        for group in ("1", "2", "3", "4"):
            action = sync.addAction(tr('加入同步组 ') + group)
            action.setCheckable(True)
            action.setChecked(pane.state.sync_group == group)
            action.triggered.connect(lambda checked=False, group=group: self.join_sync_group(group))
        sync.addAction(tr('退出当前同步组'), lambda: self.playback.leave_group([self.active_id]))
        sync.addAction(tr('取消全部同步'), lambda: self.playback.leave_group(list(self.panes)))
        layout = submenu(menu, tr('布局'))
        for index in range(self.layout_combo.count()):
            action = layout.addAction(self.layout_combo.itemText(index))
            action.triggered.connect(lambda checked=False, index=index: self.apply_preset(index))
        layout.addSeparator()
        layout.addAction(tr('向右拆分'), lambda: self.add_blank(axis="horizontal"))
        layout.addAction(tr('向下拆分'), lambda: self.add_blank(axis="vertical"))
        layout.addAction(tr('复制到下方'), lambda: self.duplicate(axis="vertical"))
        layout.addAction(tr('聚焦 / 返回布局\tF'), self.toggle_focus)
        workspace = submenu(menu, tr('工作区'))
        workspace.addAction(tr('打开…\tCtrl+Shift+O'), self.load_dialog)
        workspace.addAction(tr('保存…\tCtrl+S'), self.save_dialog)
        menu.addSeparator()
        edit = menu.addAction(tr('显示编辑界面\tTab'))
        edit.setCheckable(True)
        edit.setChecked(not self.clean_mode)
        edit.triggered.connect(self.toggle_clean_mode)
        menu.addAction(tr('全屏 / 退出全屏\tF11'), self.toggle_fullscreen)
        menu.addAction(tr('使用说明'), self.show_help)
        languages = submenu(menu, "Language / 语言")
        for label, locale in [("English", "en"), ("简体中文", "zh_CN")]:
            action = languages.addAction(label)
            action.setCheckable(True)
            action.setChecked(i18n.language() == locale and not i18n.follows_system())
            action.triggered.connect(lambda _checked=False, value=locale: i18n.set_language(value, persist=True))
        system = languages.addAction("System default / 跟随系统")
        system.setCheckable(True)
        system.setChecked(i18n.follows_system())
        system.triggered.connect(lambda _checked=False: i18n.use_system_language())
        menu.addAction(tr('退出\tCtrl+Q'), self.close)
        return menu

    def set_playback_rate(self, rate):
        if self.active():
            self.playback.set_rate(self.active_id, rate)
            self.refresh_inspector()

    def set_fit_mode(self, mode, all_panes=False):
        if mode not in ("contain", "cover", "stretch"):
            return
        panes = self.panes.values() if all_panes else [self.active()]
        for pane in panes:
            if pane:
                pane.state.fit_mode = mode
                pane.apply_state()
        self.refresh_inspector()

    def toggle_loop(self):
        if self.active():
            s = self.active().state
            self.playback.set_loop(s.id, not s.loop, start_ms=s.loop_start_ms, end_ms=s.loop_end_ms)
            self.refresh_inspector()

    def set_loop_a(self):
        if self.active():
            self.playback.set_a(self.active_id)
            self.refresh_inspector()

    def set_loop_b(self):
        if self.active():
            if not self.playback.set_b(self.active_id):
                QMessageBox.information(self, tr('A/B 循环'), tr('请先设置 A 点，再将进度移动到 A 点之后设置 B 点。'))
            self.refresh_inspector()

    def loop_dialog(self):
        pane = self.active()
        if not pane or not pane.state.source:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('A/B 区间循环'))
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        start, end = QDoubleSpinBox(), QDoubleSpinBox()
        maximum = max(pane.player.duration() / 1000, 1)
        for field in (start, end):
            field.setDecimals(3)
            field.setRange(0, maximum)
            field.setSuffix(tr(' 秒'))
            field.setSingleStep(.1)
        start.setValue(pane.state.loop_start_ms / 1000)
        end.setValue((pane.state.loop_end_ms or pane.player.duration()) / 1000)
        form.addRow(tr('开始 A'), start)
        form.addRow(tr('结束 B'), end)
        layout.addLayout(form)
        note = QLabel(tr('到达 B 点后返回 A 点。同步组内同时设置并循环。'))
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if not self.playback.set_loop(pane.state.id, True, start_ms=round(start.value() * 1000), end_ms=round(end.value() * 1000)):
                QMessageBox.warning(self, tr('无法设置循环'), tr('结束 B 必须大于开始 A，并且在视频时长之内。'))
            self.refresh_inspector()

    def sync_all(self, preserve_offsets=False, mode="time"):
        ids = [pid for pid, pane in self.panes.items() if pane.state.source]
        if ids:
            leader = self.active_id if self.active_id in ids else ids[0]
            if self.playback.join_group(ids, group="1", leader_id=leader, preserve_offsets=preserve_offsets, mode=mode) is False:
                QMessageBox.information(self, tr('无法同步'), tr('视频时长差异过大，百分比同步需要的播放速度超出支持范围。请使用按时间同步。'))
            self.refresh_inspector()

    def join_sync_group(self, group):
        if not self.active():
            return
        existing = [pid for pid, pane in self.panes.items() if pane.state.sync_group == group and pid != self.active_id]
        mode = self.panes[existing[0]].state.sync_mode if existing else "time"
        if self.playback.join_group([self.active_id], group=group, leader_id=existing[0] if existing else self.active_id, mode=mode) is False:
            QMessageBox.information(self, tr('无法同步'), tr('视频时长差异过大。请使用按时间同步。'))
        self.refresh_inspector()

    def toggle_mirror(self, field):
        if self.active():
            setattr(self.active().state, field, not getattr(self.active().state, field))
            self.active().apply_state()
            self.refresh_inspector()

    def create_inspector(self):
        frame = QFrame()
        frame.setObjectName("inspector")
        frame.setFixedWidth(244)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 16, 15, 14)
        layout.setSpacing(12)
        section = QLabel(tr('当前窗格'))
        section.setObjectName("section")
        layout.addWidget(section)
        self.selected_label = QLabel(tr('空白窗格'))
        self.selected_label.setProperty("i18nUserText", True)
        self.selected_label.setWordWrap(True)
        self.selected_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(self.selected_label)
        self.source_label = QLabel(tr('可拖入视频，或点击添加视频'))
        self.source_label.setProperty("i18nUserText", True)
        self.source_label.setWordWrap(True)
        self.source_label.setObjectName("sub")
        self.source_label.setMaximumHeight(54)
        layout.addWidget(self.source_label)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background: #344050; max-height: 1px;")
        layout.addWidget(line)
        layout.addWidget(QLabel(tr('画面变换')))
        self.fit_mode = QComboBox()
        for label, value in FIT_MODES:
            self.fit_mode.addItem(tr(label), value)
        self.fit_mode.currentIndexChanged.connect(self.inspector_changed)
        layout.addWidget(self.fit_mode)
        row = QHBoxLayout()
        row.addWidget(button("↶ 90°", lambda: self.rotate(-90)))
        row.addWidget(button("↷ 90°", lambda: self.rotate(90)))
        layout.addLayout(row)
        self.rotation_label = QLabel(tr('当前旋转 0°'))
        self.rotation_label.setObjectName("sub")
        layout.addWidget(self.rotation_label)
        mirrors = QHBoxLayout()
        self.flip_h = QCheckBox(tr('水平镜像'))
        self.flip_v = QCheckBox(tr('垂直镜像'))
        self.flip_h.toggled.connect(self.inspector_changed)
        self.flip_v.toggled.connect(self.inspector_changed)
        mirrors.addWidget(self.flip_h)
        mirrors.addWidget(self.flip_v)
        layout.addLayout(mirrors)
        self.crop_button = button(tr('框选裁剪'), self.start_crop, tr('在原始画面上拖出需要保留的区域（C）'))
        layout.addWidget(self.crop_button)
        self.crop_label = QLabel(tr('显示完整画面'))
        self.crop_label.setObjectName("sub")
        self.crop_label.setWordWrap(True)
        layout.addWidget(self.crop_label)
        layout.addWidget(button(tr('重置画面'), self.reset_transform))
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setSpacing(10)
        self.rate = QComboBox()
        for rate in [.25, .5, .75, 1., 1.25, 1.5, 2., 3., 4.]:
            self.rate.addItem(f"{rate:g}×", rate)
        self.rate.currentIndexChanged.connect(self.inspector_changed)
        form.addRow(tr('播放速度'), self.rate)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.valueChanged.connect(self.inspector_changed)
        form.addRow(tr('音量'), self.volume)
        layout.addLayout(form)
        row2 = QHBoxLayout()
        self.muted = QCheckBox(tr('静音'))
        self.loop = QCheckBox(tr('循环播放'))
        self.muted.toggled.connect(self.inspector_changed)
        self.loop.toggled.connect(self.inspector_changed)
        row2.addWidget(self.muted)
        row2.addWidget(self.loop)
        layout.addLayout(row2)
        layout.addWidget(button(tr('设置 A/B 循环区间…'), self.loop_dialog))
        layout.addStretch()
        hint = QLabel(tr('自由组合你的画面\n\n拖动分隔线，调整比例\n拖动标题栏，交换位置\n双击视频，聚焦查看\n\n复制保留变换和当前进度\n复制后可独立播放与调整'))
        hint.setObjectName("sub")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        frame.setMinimumWidth(218)
        frame.setMaximumWidth(244)
        scroll = QScrollArea()
        scroll.setFixedWidth(260)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setWidget(frame)
        return scroll

    def install_shortcuts(self):
        for keys, fn in [
            ("Ctrl+O", self.open_files), ("Ctrl+Shift+O", self.load_dialog),
            ("Ctrl+S", self.save_dialog), ("Ctrl+D", self.duplicate),
            ("Space", lambda: self.active().toggle_play() if self.active() else None),
            ("R", self.rotate), ("C", self.start_crop), ("F", self.toggle_focus),
            ("Escape", self.escape), ("F11", self.toggle_fullscreen),
            ("Tab", self.toggle_clean_mode), ("Ctrl+W", lambda: self.remove_pane(self.active_id)),
            ("Ctrl+Q", self.close), ("M", lambda: self.active().toggle_mute() if self.active() else None),
            ("L", self.toggle_loop), ("[", self.set_loop_a), ("]", self.set_loop_b),
            ("Ctrl+G", self.sync_all),
            ("Ctrl+]", lambda: self.move_layer("forward")), ("Ctrl+[", lambda: self.move_layer("backward")),
            ("Ctrl+Shift+]", lambda: self.move_layer("front")), ("Ctrl+Shift+[", lambda: self.move_layer("back")),
            ("Shift+Left", lambda: self.nudge_layer(-1, 0)), ("Shift+Right", lambda: self.nudge_layer(1, 0)),
            ("Shift+Up", lambda: self.nudge_layer(0, -1)), ("Shift+Down", lambda: self.nudge_layer(0, 1)),
            ("Left", lambda: self.seek(-5000)), ("Right", lambda: self.seek(5000)),
        ]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(fn)

    def active(self):
        return self.panes.get(self.active_id)

    def notify(self, message, timeout=6000):
        self._notification_deadline = monotonic() + timeout / 1000 if timeout else None
        self.statusBar().showMessage(message, timeout)

    def select(self, pane_id):
        if pane_id not in self.panes:
            return
        if self.active_id != pane_id:
            prior = self.active()
            if prior and prior.canvas.crop_active:
                prior.canvas.cancel_crop()
        self.active_id = pane_id
        selected_pane = self.panes[pane_id] if not self.clean_mode and self.layout_mode == "grid" else None
        if self._selected_pane is not selected_pane:
            for pane in (self._selected_pane, selected_pane):
                if pane is not None and self.panes.get(pane.state.id) is pane:
                    selected = pane is selected_pane
                    if bool(pane.property("selected")) != selected:
                        pane.setProperty("selected", selected)
                        pane.style().unpolish(pane)
                        pane.style().polish(pane)
            self._selected_pane = selected_pane
        if self.canvas_workspace:
            self.canvas_workspace.set_active(pane_id)
        self.refresh_inspector()

    def refresh_inspector(self):
        pane = self.active()
        if not pane:
            return
        s = pane.state
        values = {name: getattr(s, name) for name in (
            "source", "rotation", "fit_mode", "flip_h", "flip_v", "rate", "volume", "muted", "loop")}
        values["crop"] = tuple(s.crop)
        previous = self._inspector_state or {}
        if values == previous:
            return
        changed = lambda name: previous.get(name) != values[name]
        self._updating = True
        try:
            if changed("source"):
                self.selected_label.setText(Path(s.source).name if s.source else tr('空白窗格'))
                self.source_label.setText(s.source or tr('拖入视频，或点击添加视频'))
                self.source_label.setToolTip(s.source)
                self.crop_button.setEnabled(bool(s.source))
            if changed("rotation"):
                self.rotation_label.setText(tr('当前旋转 {value1}°', value1=f'{s.rotation}'))
            if changed("fit_mode"):
                self.fit_mode.setCurrentIndex(max(0, self.fit_mode.findData(s.fit_mode)))
            for name in ("flip_h", "flip_v", "muted", "loop"):
                if changed(name):
                    getattr(self, name).setChecked(values[name])
            if changed("rate"):
                rate_index = self.rate.findData(s.rate)
                if rate_index < 0:
                    self.rate.addItem(f"{s.rate:.4g}×", s.rate)
                    rate_index = self.rate.count() - 1
                self.rate.setCurrentIndex(rate_index)
            if changed("volume"):
                self.volume.setValue(round(s.volume * 100))
            if changed("crop"):
                x, y, w, h = s.crop
                self.crop_label.setText(tr('显示完整画面') if tuple(s.crop) == (0, 0, 1, 1) else tr('保留区域 {value1} × {value3}\n起点 X {value5} / Y {value7}', value1=f'{w:.0%}', value3=f'{h:.0%}', value5=f'{x:.0%}', value7=f'{y:.0%}'))
            self._inspector_state = values
        finally:
            self._updating = False

    def inspector_changed(self, *_):
        if self._updating or not self.active():
            return
        # A rejected UI edit must restore the model's value even if unchanged.
        self._inspector_state = None
        s = self.active().state
        old_rate, old_loop = s.rate, s.loop
        s.flip_h, s.flip_v = self.flip_h.isChecked(), self.flip_v.isChecked()
        chosen_rate, chosen_loop = self.rate.currentData(), self.loop.isChecked()
        s.volume, s.muted = self.volume.value() / 100, self.muted.isChecked()
        s.fit_mode = self.fit_mode.currentData()
        self.active().apply_state()
        if chosen_rate != old_rate:
            self.playback.set_rate(s.id, chosen_rate)
        if chosen_loop != old_loop:
            self.playback.set_loop(s.id, chosen_loop, start_ms=s.loop_start_ms, end_ms=s.loop_end_ms)
        self.refresh_inspector()

    def capture_sizes(self):
        if self.focus_id or self.layout_mode == "canvas":
            return
        for splitter, node in self._split_nodes:
            sizes = splitter.sizes()
            if sizes and all(x > 0 for x in sizes):
                node["sizes"] = sizes

    def rebuild(self):
        self._layout_generation += 1
        generation = self._layout_generation
        if (self.layout_mode == "canvas" and not self.focus_id
                and self.canvas_workspace is not None
                and self.root_widget is self.canvas_workspace):
            self.canvas_workspace.sync_panes(list(self.panes.values()))
            self.canvas_workspace.set_editing(not self.clean_mode)
            self.count_label.setText(tr('{value0} 个画面  ·  GridStudio {value2}', value0=f'{len(self.panes)}', value2=f'{__version__}'))
            self.select(self.active_id or next(iter(self.panes)))
            self.playback.refresh_activity()
            return
        self.setUpdatesEnabled(False)
        try:
            if self.canvas_workspace:
                self.canvas_workspace.detach_panes()
                self.canvas_workspace = None
            for pane in self.panes.values():
                pane.setParent(self.pane_parking)
                pane.set_clean_mode(self.clean_mode)
            if self.root_widget:
                self.stage_layout.removeWidget(self.root_widget)
                if isinstance(self.root_widget, (QSplitter, FreeCanvas)):
                    self.root_widget.deleteLater()
                else:
                    self.root_widget.hide()
            self._split_nodes = []
            def build(node):
                if "pane" in node:
                    pane = self.panes[node["pane"]]
                    return pane
                splitter = QSplitter(Qt.Orientation.Horizontal if node["axis"] == "horizontal" else Qt.Orientation.Vertical)
                splitter.setChildrenCollapsible(False)
                self.style_splitter(splitter)
                for child in node["children"]:
                    widget = build(child)
                    splitter.addWidget(widget)
                    widget.show()
                splitter.setSizes([max(1, round(x * 1000)) for x in node["sizes"]])
                self._split_nodes.append((splitter, node))
                return splitter
            if self.focus_id:
                self.root_widget = self.panes[self.focus_id]
            elif self.layout_mode == "canvas":
                for index, pane in enumerate(self.panes.values()):
                    if pane.state.canvas_rect is None:
                        pane.state.canvas_rect = (0, 0, 1, 1) if len(self.panes) == 1 else self.new_canvas_rect(index)
                        pane.state.z_order = index
                self.canvas_workspace = FreeCanvas(self)
                self.canvas_workspace.attach_panes(list(self.panes.values()))
                self.canvas_workspace.set_editing(not self.clean_mode)
                self.canvas_workspace.contextRequested.connect(lambda point: self.active().context_menu(point) if self.active() else None)
                self.canvas_workspace.filesDropped.connect(self.add_files)
                self.root_widget = self.canvas_workspace
            else:
                self.root_widget = build(self.tree)
            self.stage_layout.addWidget(self.root_widget)
            self.root_widget.show()
            self.focus_button.setText(tr('返回布局') if self.focus_id else tr('聚焦'))
            self.count_label.setText(tr('{value0} 个画面  ·  GridStudio {value2}', value0=f'{len(self.panes)}', value2=f'{__version__}'))
            self.select(self.active_id or next(iter(self.panes)))
        finally:
            self.setUpdatesEnabled(True)
        self.playback.refresh_activity()
        def settle_sizes():
            if generation != self._layout_generation or self.focus_id:
                return
            # Apply proportions after parents receive their actual window geometry.
            for splitter, node in reversed(self._split_nodes):
                available = max(1, sum(splitter.sizes()))
                weights = node["sizes"]
                total = sum(weights)
                splitter.setSizes([max(1, round(available * w / total)) for w in weights])
        QTimer.singleShot(0, settle_sizes)

    def prepare_change(self):
        self.capture_sizes()
        self.focus_id = None
        self.layout_combo.setCurrentIndex(self.layout_combo.findData("canvas" if self.layout_mode == "canvas" else "custom"))

    def add_blank(self, pane_id=None, axis="horizontal"):
        if len(self.panes) >= 64:
            self.notify(tr('最多支持 64 个窗格；同时播放数量取决于硬件性能。'))
            return
        self.prepare_change()
        target = pane_id or self.active_id
        state = PaneState()
        self.raise_new_layer(state)
        self.panes[state.id] = VideoPane(self, state)
        self.tree = split_leaf(self.tree, target, state.id, axis)
        self.active_id = state.id
        self.rebuild()

    def duplicate(self, pane_id=None, axis="horizontal"):
        pane_id = pane_id if isinstance(pane_id, str) else self.active_id
        if pane_id not in self.panes or len(self.panes) >= 64:
            return
        self.prepare_change()
        state = self.panes[pane_id].snapshot().clone()
        self.raise_new_layer(state, self.panes[pane_id].state)
        self.panes[state.id] = VideoPane(self, state)
        self.tree = split_leaf(self.tree, pane_id, state.id, axis)
        self.active_id = state.id
        self.rebuild()
        self.notify(tr('已复制窗格，保留进度、裁剪、旋转、镜像、音量和播放速度。两个窗格可独立调整。'))

    def remove_pane(self, pane_id):
        if pane_id not in self.panes:
            return
        self.prepare_change()
        pane = self.panes.pop(pane_id)
        # Detach before rebuilding so the obsolete splitter cannot destroy a live pane.
        pane.setParent(self.pane_parking)
        pane.dispose()
        self.tree = remove_leaf(self.tree, pane_id)
        if not self.panes:
            state = PaneState()
            self.panes[state.id] = VideoPane(self, state)
            self.tree = {"pane": state.id}
        if self.active_id == pane_id:
            self.active_id = leaf_ids(self.tree)[0]
        self.rebuild()

    def swap(self, a, b):
        if a == b:
            return
        self.prepare_change()
        self.tree = swap_leaves(self.tree, a, b)
        self.rebuild()
        self.notify(tr('已交换窗格位置'))

    def preset_selected(self, index):
        key = self.layout_combo.itemData(index)
        if key == "canvas":
            self.set_layout_mode("canvas")
            return
        if key == "custom":
            self.set_layout_mode("grid")
            return
        if self.layout_mode != "grid":
            self.set_layout_mode("grid")
        self.capture_sizes()
        self.focus_id = None
        needed = {"grid4": 4, "grid9": 9, "columns": 2, "rows": 2, "focus-left": 3, "focus-top": 3}[key]
        ids = leaf_ids(self.tree)
        while len(ids) < needed:
            state = PaneState()
            self.panes[state.id] = VideoPane(self, state)
            ids.append(state.id)
        if key.startswith("grid"):
            columns = 2 if key == "grid4" else 3
            rows = [make_layout(ids[i:i + columns], "columns") for i in range(0, len(ids), columns)]
            self.tree = rows[0] if len(rows) == 1 else {"axis": "vertical", "sizes": [1] * len(rows), "children": rows}
        else:
            self.tree = make_layout(ids, key)
        self.rebuild()
        self.notify(tr('已应用布局；现有窗格全部保留。拖动分隔线可继续调整。'))

    def open_files(self, pane_id=None):
        pane_id = pane_id if isinstance(pane_id, str) else None
        files, _ = QFileDialog.getOpenFileNames(self, tr('添加视频（可多选）'), "", tr(VIDEO_FILTER))
        if files:
            self.add_files(files, pane_id)

    def add_files(self, paths, target=None):
        paths = [str(Path(p).resolve()) for p in paths if p and Path(p).is_file()]
        if not paths:
            return
        if len(paths) == 1 and Path(paths[0]).suffix.lower() in (".gstudio", ".json"):
            self.load_session(paths[0])
            return
        auto_grid = self.layout_mode == "grid" and target is None and len(self.panes) == 1 and not self.active().state.source and len(paths) > 1
        self.prepare_change()
        for path in paths:
            empty = next((pid for pid in leaf_ids(self.tree) if not self.panes[pid].state.source), None)
            dest = target or empty
            target = None
            if dest is None:
                if len(self.panes) >= 64:
                    self.notify(tr('最多支持 64 个窗格，超出部分未添加。'))
                    break
                state = PaneState(source=path, paused=False)
                self.raise_new_layer(state)
                dest = state.id
                self.panes[dest] = VideoPane(self, state)
                self.tree = split_leaf(self.tree, self.active_id, dest, "horizontal")
            else:
                pane = self.panes[dest]
                media_command(pane.player, "stop")
                relocating = bool(pane.state.source) and not Path(pane.state.source).is_file()
                pane.state.source = path
                pane.state.position_ms = 0
                pane.state.paused = False
                if not relocating:
                    pane.state.crop = (0, 0, 1, 1)
                    pane.state.rotation = 0
                    pane.state.flip_h = pane.state.flip_v = False
                    pane.state.loop_start_ms = 0
                    pane.state.loop_end_ms = None
                pane.apply_state()
                pane.load_source()
            self.active_id = dest
        if auto_grid:
            self.tree = make_layout(leaf_ids(self.tree), "grid")
        self.rebuild()
        self.notify(tr('已添加 {value1} 个视频。默认静音，按 M 或在右键菜单开启声音。', value1=f'{len(paths)}'))

    def rotate(self, degrees=90):
        if self.active():
            self.active().state.rotation = (self.active().state.rotation + degrees) % 360
            self.active().apply_state()
            self.refresh_inspector()

    def start_crop(self):
        if self.active() and self.active().state.source:
            self.active().canvas.start_crop()
            self.notify(tr('裁剪模式：在原始画面上拖出需要保留的区域，松开应用；Esc 取消。'), 0)

    def reset_transform(self):
        if self.active():
            self.active().canvas.cancel_crop()
            s = self.active().state
            s.crop, s.rotation, s.flip_h, s.flip_v = (0, 0, 1, 1), 0, False, False
            self.active().apply_state()
            self.refresh_inspector()

    def toggle_focus(self, pane_id=None):
        pane_id = pane_id if isinstance(pane_id, str) else self.active_id
        self.capture_sizes()
        self.focus_id = None if self.focus_id else pane_id
        self.active_id = pane_id
        self.rebuild()

    def escape(self):
        if self.active() and self.active().canvas.crop_active:
            self.active().canvas.cancel_crop()
            self.notify(tr('已取消裁剪'))
        elif self.focus_id:
            self.toggle_focus()
        elif self.isFullScreen():
            self.showNormal()
        elif not self.clean_mode:
            self.set_clean_mode(True)

    def seek(self, delta):
        if self.active():
            p = self.active().player
            self.playback.seek(self.active_id, max(0, min(p.duration(), p.position() + delta)))

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def play_all(self, playing):
        groups = set()
        for pane in self.panes.values():
            if pane.state.source:
                if pane.state.sync_group and pane.state.sync_group in groups:
                    continue
                self.playback.set_playing(pane.state.id, playing)
                if pane.state.sync_group:
                    groups.add(pane.state.sync_group)

    def session_data(self, base=None):
        self.capture_sizes()
        data = encode_session([p.snapshot() for p in self.panes.values()], self.tree, layout_mode=self.layout_mode)
        if base:
            # Relative paths keep a workspace portable when media is moved with it.
            for s in data["panes"]:
                if s["source"] and not s["source"].startswith(("http://", "https://", "rtsp://")):
                    try:
                        s["source"] = os.path.relpath(s["source"], base)
                    except ValueError:
                        pass
        return data

    def save_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('保存工作区'), str(self.session_path or tr('我的多画面.gstudio')), tr(SESSION_FILTER))
        if path:
            if not Path(path).suffix:
                path += ".gstudio"
            self.save_session(path)

    def save_session(self, path):
        try:
            target = Path(path)
            data = self.session_data(target.parent)
            temp = target.with_suffix(target.suffix + ".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(target)
            self.session_path = target
            self.notify(tr('工作区已保存：{path}', path=str(target)))
            return True
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr('无法保存'), i18n.error_text(str(e)))
            return False

    def load_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('打开工作区'), "", tr(SESSION_FILTER))
        if path:
            self.load_session(path)

    def load_session(self, path):
        try:
            target = Path(path)
            if target.stat().st_size > 4 * 1024 * 1024:
                raise ValueError(tr('工作区文件过大（上限 4 MB）'))
            data = json.loads(target.read_text(encoding="utf-8-sig"))
            states, tree = decode_session(data)
            if not states or tree is None:
                raise ValueError(tr('工作区至少需要一个窗格'))
            missing = []
            for s in states:
                if s.source and not s.source.startswith(("http://", "https://", "rtsp://")):
                    src = Path(s.source)
                    s.source = str((target.parent / src).resolve()) if not src.is_absolute() else str(src)
                    if not Path(s.source).is_file():
                        missing.append(s.source)
            self.focus_id = None
            self.playback.reset()
            if self.canvas_workspace:
                self.canvas_workspace.detach_panes()
            for pane in self.panes.values():
                pane.setParent(self.pane_parking)
                pane.dispose()
            self.layout_mode = data.get("layout_mode", "grid")
            self.panes = {s.id: VideoPane(self, s) for s in states}
            self.tree = tree
            self.active_id = leaf_ids(tree)[0]
            self.session_path = target
            self.layout_combo.setCurrentIndex(self.layout_combo.findData("canvas" if self.layout_mode == "canvas" else "custom"))
            self.rebuild()
            self.set_clean_mode(self.clean_mode)
            if missing:
                QMessageBox.warning(self, tr('部分视频路径已失效'), tr('布局和变换已恢复。请在对应窗格右键选择「打开 / 替换视频」重新定位。\n\n') + "\n".join(missing[:8]))
            self.notify(tr('已恢复工作区：{name}', name=target.name))
            return True
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as e:
            QMessageBox.warning(self, tr('无法打开工作区'), i18n.error_text(str(e)))
            return False

    def show_help(self):
        QMessageBox.information(self, tr('关于 GridStudio'), tr('GridStudio {value1} · 自由画布播放器\n\n默认只显示视频，不显示工具栏、标题、进度条或侧栏。\n拖入视频即可播放；右键打开操作菜单。\nTab 显示 / 隐藏编辑界面；F11 全屏后只保留画面。\n默认保持原视频比例、完整显示。右键 → 画面 → 显示方式，可选择完整显示、裁切铺满或拉伸填满。\n默认自由画布：Tab 编辑，拖动画面移动，拖动边角改变尺寸。\n保持原比例时，图层补出的留白会透出下方视频。\n移动鼠标显示文件名、进度条、播放/暂停、静音和音量，静止 2 秒后隐藏；拖动时保持显示。\n可拖动进度条定位，A/B 标记显示循环范围。\n右键 → 图层，可置顶、置底、上移或下移一层，以及精确设置坐标和尺寸。\n布局菜单可切换网格分屏。播放时隐藏画布选择框和缩放手柄。\n复制会保留裁剪、旋转、镜像和当前进度。原视频文件不会被修改。\n\n快捷键\nCtrl+O 添加视频  ·  Ctrl+D 复制  ·  Ctrl+S 保存\n空格 播放/暂停  ·  M 静音  ·  ←/→ 后退/前进5秒\nR 旋转  ·  C 裁剪  ·  F 聚焦  ·  Tab 编辑界面  ·  F11 全屏\n\nL 循环开关；[ / ] 设置 A/B 区间；Ctrl+G 同步所有视频。\n同步组联动播放、暂停、定位和速度，并定期校正时间差；不保证硬件逐帧锁定。\n参考 GridPlayer 的多画面理念，以 PySide6 / Qt Multimedia 独立实现。', value1=f'{__version__}'))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        self.playback.shutdown()
        if self.canvas_workspace:
            self.canvas_workspace.detach_panes()
        for pane in self.panes.values():
            # Focus mode parks the other layers out of view. Explicitly release
            # every decoder, including those hidden sibling layers.
            pane.dispose()
        super().closeEvent(event)


def main():
    language_parser = argparse.ArgumentParser(add_help=False)
    language_parser.add_argument("--language", choices=("en", "zh_CN"))
    language_args, _ = language_parser.parse_known_args()
    i18n.initialize(language_args.language)
    parser = argparse.ArgumentParser(description=tr('GridStudio 多画面播放器'))
    parser.add_argument("--language", choices=("en", "zh_CN"), help="UI language for this launch / 本次启动的界面语言")
    parser.add_argument("files", nargs="*", help=tr('视频文件或 .gstudio 工作区'))
    parser.add_argument("--smoke-test", metavar="PNG", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-hover", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--edit", action="store_true", help=tr('启动时显示画布编辑框'))
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("GridStudio")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("GridStudio")
    app.setDesktopFileName("io.github.ssjjrrr.GridStudio")
    i18n.initialize()
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, "#181f29"), (QPalette.ColorRole.WindowText, "#dbe3ee"),
        (QPalette.ColorRole.Base, "#11161d"), (QPalette.ColorRole.AlternateBase, "#242e3c"),
        (QPalette.ColorRole.Text, "#dbe3ee"), (QPalette.ColorRole.Button, "#242e3c"),
        (QPalette.ColorRole.ButtonText, "#dbe3ee"), (QPalette.ColorRole.Highlight, "#52d3ba"),
        (QPalette.ColorRole.HighlightedText, "#102b27"), (QPalette.ColorRole.Link, "#83e4ce"),
    ]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    if args.files:
        window.add_files(args.files)
    if args.edit:
        window.set_clean_mode(False)
    if args.smoke_test:
        def finish():
            if args.smoke_hover:
                pane = max(window.panes.values(), key=lambda p: p.state.z_order)
                pane.hover_controls.note_activity()
                app.processEvents()
            media = []
            for pane in window.panes.values():
                if pane.state.source:
                    frame = pane.canvas.video_item.videoSink().videoFrame()
                    media.append({"source": Path(pane.state.source).name,
                                  "frame_valid": frame.isValid(),
                                  "frame_us": frame.startTime(),
                                  "duration_ms": pane.player.duration(),
                                  "error": pane.player.error().name})
            decoded = all(item["frame_valid"] and item["error"] == "NoError" for item in media)
            decoded = decoded and (bool(media) or not args.files)
            capture = Path(args.smoke_test)
            saved = window.grab().save(str(capture))
            exit_code = 0 if decoded and saved else 2
            try:
                capture.with_suffix(".json").write_text(json.dumps({
                    "version": __version__, "platform": app.platformName(), "language": i18n.language(),
                    "qt_translation_loaded": i18n.qt_translation_loaded(),
                    "media": media, "capture_saved": saved, "passed": exit_code == 0,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                exit_code = 2
            window.close()
            app.exit(exit_code)
        QTimer.singleShot(3500, finish)
    sys.exit(app.exec())
