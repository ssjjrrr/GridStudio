"""Canvas padding is empty space; actual video pixels remain opaque layers."""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtTest import QTest

from test_app import drain_events, qapp
from test_free_canvas import canvas_window
from test_seamless import feed_solid, matches


@pytest.fixture
def overlapping_videos(canvas_window, qapp):
    win = canvas_window
    behind = win.active()
    behind.state.fit_mode = "stretch"
    behind.apply_state()
    feed_solid(behind.canvas, "lime", (400, 300))
    win.add_blank()
    front = win.active()
    win.canvas_workspace.set_rect(front.state.id, (.1, .1, .8, .8))
    feed_solid(front.canvas, "red", (400, 100))
    drain_events(qapp)
    assert front.state.fit_mode == "contain"
    yield win, behind, front


def stage_color(win, pane, x, y):
    image = win.stage.grab().toImage()
    local = QPoint(round((pane.width() - 1) * x), round((pane.height() - 1) * y))
    point = pane.mapTo(win.stage, local)
    sx, sy = image.width() / win.stage.width(), image.height() / win.stage.height()
    return image.pixelColor(round(point.x() * sx), round(point.y() * sy))


def assert_horizontal_picture(win, pane, color="red"):
    assert matches(stage_color(win, pane, .5, .05), "lime")
    assert matches(stage_color(win, pane, .5, .95), "lime")
    assert matches(stage_color(win, pane, .5, .5), color)
    assert not pane.mask().contains(QPoint(pane.width() // 2, 3))
    assert pane.mask().contains(pane.rect().center())


def assert_vertical_picture(win, pane, color="red"):
    assert matches(stage_color(win, pane, .05, .5), "lime")
    assert matches(stage_color(win, pane, .95, .5), "lime")
    assert matches(stage_color(win, pane, .5, .5), color)
    assert not pane.mask().contains(QPoint(3, pane.height() // 2))
    assert pane.mask().contains(pane.rect().center())


@pytest.mark.parametrize("editing", [False, True])
def test_contain_padding_reveals_lower_video_and_actual_picture_covers_it(overlapping_videos, qapp, editing):
    win, behind, front = overlapping_videos
    original_rect = front.state.canvas_rect
    win.set_clean_mode(not editing)
    drain_events(qapp)
    assert_horizontal_picture(win, front)
    assert front.state.canvas_rect == original_rect
    # Removing the generated padding must not change the chosen fit or crop.
    assert front.canvas.fill_mode == front.state.fit_mode == "contain"
    assert front.state.crop == (0, 0, 1, 1)


def test_black_pixels_inside_video_are_still_opaque(overlapping_videos, qapp):
    win, behind, front = overlapping_videos
    image = QImage(400, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    painter = QPainter(image)
    painter.fillRect(0, 0, 200, 100, QColor("black"))
    painter.end()
    front.canvas.video_item.videoSink().setVideoFrame(QVideoFrame(image))
    drain_events(qapp)
    assert matches(stage_color(win, front, .25, .5), "black")
    assert matches(stage_color(win, front, .75, .5), "red")
    assert matches(stage_color(win, front, .25, .05), "lime")
    assert front.mask().contains(QPoint(front.width() // 4, front.height() // 2))


@pytest.mark.parametrize("editing", [False, True])
def test_pointer_on_padding_selects_lower_video_without_reordering(overlapping_videos, qapp, editing):
    win, behind, front = overlapping_videos
    win.set_clean_mode(not editing)
    win.select(front.state.id)
    drain_events(qapp)
    order = {pid: pane.state.z_order for pid, pane in win.panes.items()}
    point = front.mapTo(win.stage, QPoint(front.width() // 2, round(front.height() * .08)))
    # Ask Qt to route this point through widget masks, instead of sending an
    # artificial click directly to the front viewport and bypassing hit testing.
    target = win.stage.childAt(point)
    assert target is behind.canvas.viewport()
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.mapFrom(win.stage, point))
    drain_events(qapp)
    assert win.active_id == behind.state.id
    assert {pid: pane.state.z_order for pid, pane in win.panes.items()} == order


def test_mask_follows_crop_rotation_and_mirroring(overlapping_videos, qapp):
    win, behind, front = overlapping_videos
    front.state.crop = (.25, 0, .5, 1)
    front.apply_state()
    drain_events(qapp)
    assert_horizontal_picture(win, front)
    horizontal = front.mask().boundingRect()
    front.state.rotation = 90
    front.state.flip_h = True
    front.state.flip_v = True
    front.apply_state()
    drain_events(qapp)
    assert_vertical_picture(win, front)
    assert front.mask().boundingRect() != horizontal
    front.state.rotation = 270
    front.apply_state()
    drain_events(qapp)
    assert_vertical_picture(win, front)
    front.state.rotation = 180
    front.apply_state()
    drain_events(qapp)
    assert_horizontal_picture(win, front)


def test_mask_updates_when_frame_native_size_changes(overlapping_videos, qapp):
    win, behind, front = overlapping_videos
    assert_horizontal_picture(win, front)
    feed_solid(front.canvas, "red", (100, 400))
    drain_events(qapp)
    assert_vertical_picture(win, front)
    feed_solid(front.canvas, "red", (800, 100))
    drain_events(qapp)
    assert_horizontal_picture(win, front)


def test_mask_updates_after_window_and_layer_resize(overlapping_videos, qapp):
    win, behind, front = overlapping_videos
    original = front.state.canvas_rect
    for width, height in ((1250, 700), (850, 800), (1000, 700)):
        win.resize(width, height)
        drain_events(qapp)
        assert front.state.canvas_rect == original
        assert_horizontal_picture(win, front)
    win.canvas_workspace.set_rect(front.state.id, (.1, .2, .85, .15))
    drain_events(qapp)
    assert_vertical_picture(win, front)
    win.canvas_workspace.set_rect(front.state.id, original)
    drain_events(qapp)
    assert_horizontal_picture(win, front)


@pytest.mark.parametrize("mode", ["cover", "stretch"])
def test_cover_and_stretch_clear_mask_and_fill_the_whole_layer(overlapping_videos, qapp, mode):
    win, behind, front = overlapping_videos
    assert not front.mask().isEmpty()
    win.select(front.state.id)
    win.set_fit_mode(mode)
    drain_events(qapp)
    assert front.mask().isEmpty()
    assert matches(stage_color(win, front, .5, .05), "red")
    assert matches(stage_color(win, front, .05, .5), "red")
    win.set_fit_mode("contain")
    drain_events(qapp)
    assert_horizontal_picture(win, front)


def test_focus_and_grid_keep_normal_letterbox_and_restore_canvas_mask(overlapping_videos, qapp):
    win, behind, front = overlapping_videos
    assert not front.mask().isEmpty()
    win.toggle_focus(front.state.id)
    drain_events(qapp)
    assert front.mask().isEmpty()
    assert matches(stage_color(win, front, .5, .05), "black")
    win.toggle_focus(front.state.id)
    drain_events(qapp)
    assert_horizontal_picture(win, front)
    win.set_layout_mode("grid")
    drain_events(qapp)
    assert all(pane.mask().isEmpty() for pane in win.panes.values())
    assert matches(stage_color(win, front, .5, .05), "black")
    win.set_layout_mode("canvas")
    drain_events(qapp)
    assert_horizontal_picture(win, front)


@pytest.mark.parametrize("state", ["empty", "error"])
def test_empty_and_error_messages_remain_visible_and_interactive(overlapping_videos, qapp, state):
    win, behind, front = overlapping_videos
    assert not front.mask().isEmpty()
    if state == "empty":
        front.canvas.set_has_media(False)
    else:
        front.canvas.set_message("无法播放此视频")
    drain_events(qapp)
    assert front.mask().isEmpty()
    point = front.mapTo(win.stage, QPoint(front.width() // 2, round(front.height() * .08)))
    assert win.stage.childAt(point) is front.canvas.viewport()
    assert not matches(stage_color(win, front, .5, .08), "lime")
    if state == "empty":
        front.canvas.set_has_media(True)
    else:
        front.canvas.set_message("")
    drain_events(qapp)
    assert_horizontal_picture(win, front)


def test_crop_editor_temporarily_uses_full_layer_and_restores_mask(overlapping_videos, qapp):
    win, behind, front = overlapping_videos
    win.set_clean_mode(False)
    front.canvas.start_crop()
    drain_events(qapp)
    assert front.canvas.crop_active
    assert front.mask().isEmpty()
    original_rect = front.state.canvas_rect
    canvas = front.canvas
    start, end = canvas.mapFromScene(QPointF(40, 20)), canvas.mapFromScene(QPointF(360, 80))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, delay=20)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    drain_events(qapp)
    assert not canvas.crop_active
    assert front.state.crop == pytest.approx((.1, .2, .8, .6), abs=.02)
    assert front.state.canvas_rect == original_rect
    assert not front.mask().isEmpty()
    assert_horizontal_picture(win, front)
    crop = front.state.crop
    canvas.start_crop()
    assert front.mask().isEmpty()
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Escape)
    drain_events(qapp)
    assert not canvas.crop_active
    assert front.state.crop == crop
    assert_horizontal_picture(win, front)
