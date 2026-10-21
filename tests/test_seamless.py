"""Pixel checks for gapless video, including invisible splitter grab areas."""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QVideoFrame

from test_app import drain_events, qapp, window


COLORS = ("#ff00ff", "#00ffff", "#ffff00")


def feed_solid(canvas, color, size=(640, 360)):
    image = QImage(*size, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    canvas.set_has_media(True)
    canvas.set_message("")
    canvas.video_item.videoSink().setVideoFrame(QVideoFrame(image))


def matches(color, expected):
    target = QColor(expected)
    return all(abs(a - b) <= 3 for a, b in zip(
        (color.red(), color.green(), color.blue()),
        (target.red(), target.green(), target.blue())))


def assert_perimeter(image, expected):
    width, height = image.width(), image.height()
    points = {(x, y) for x in range(width) for y in (0, height - 1)}
    points.update((x, y) for x in (0, width - 1) for y in range(height))
    for x, y in points:
        actual = image.pixelColor(x, y)
        assert matches(actual, expected), (x, y, actual.name(), expected)


def assert_stage_has_no_seams(win):
    """Capture the composed widgets; canvas-only grabs miss overlaid handles."""
    image = win.stage.grab().toImage()
    width, height = image.width(), image.height()
    sx = width / win.stage.width()
    sy = height / win.stage.height()
    columns = {0, width - 1}
    rows = {0, height - 1}
    for pane in win.panes.values():
        start = pane.mapTo(win.stage, QPoint(0, 0))
        for logical_x in (start.x(), start.x() + pane.width()):
            edge = round(logical_x * sx)
            columns.update(x for x in range(edge - 3, edge + 4) if 0 <= x < width)
        for logical_y in (start.y(), start.y() + pane.height()):
            edge = round(logical_y * sy)
            rows.update(y for y in range(edge - 3, edge + 4) if 0 <= y < height)
    points = {(x, y) for x in columns for y in range(height)}
    points.update((x, y) for y in rows for x in range(width))
    for x, y in points:
        actual = image.pixelColor(x, y)
        assert any(matches(actual, color) for color in COLORS), (x, y, actual.name())


@pytest.mark.parametrize("viewport_size", [(513, 281), (281, 513), (641, 361)])
@pytest.mark.parametrize("rotation", [0, 90, 270])
def test_clean_video_covers_every_edge_without_distortion(window, qapp, viewport_size, rotation):
    pane = window.active()
    window.resize(*viewport_size)
    pane.state.fit_mode = "cover"
    pane.state.crop = (0.13, 0.17, 0.73, 0.61)
    pane.state.rotation = rotation
    pane.state.flip_h = True
    pane.apply_state()
    feed_solid(pane.canvas, COLORS[0])
    drain_events(qapp)
    assert pane.canvas.fill_mode == "cover"
    assert_perimeter(pane.canvas.capture_image(), COLORS[0])
    assert_perimeter(pane.canvas.viewport().grab().toImage(), COLORS[0])
    transform = pane.canvas.transform()
    assert transform.m11() == pytest.approx(transform.m22())
    assert transform.m12() == transform.m21() == 0
    assert pane.state.crop == (0.13, 0.17, 0.73, 0.61)
    assert pane.state.rotation == rotation


@pytest.mark.parametrize("axis", ["horizontal", "vertical"])
@pytest.mark.parametrize("nested", [False, True])
def test_adjacent_videos_have_no_gap_in_composed_widget_capture(window, qapp, axis, nested):
    window.resize(795, 447)
    window.add_blank(axis=axis)
    if nested:
        window.add_blank(axis="vertical" if axis == "horizontal" else "horizontal")
    drain_events(qapp)
    for index, pane in enumerate(window.panes.values()):
        pane.state.fit_mode = "cover"
        pane.apply_state()
        feed_solid(pane.canvas, COLORS[index], (321, 179))
    drain_events(qapp)
    for splitter, _ in window._split_nodes:
        splitter.setSizes([211, 457])
    drain_events(qapp)
    assert_stage_has_no_seams(window)
    # Hover must not reveal a divider or paint over either adjacent picture.
    from PySide6.QtTest import QTest
    for splitter, _ in window._split_nodes:
        handle = splitter.handle(1)
        QTest.mouseMove(handle, handle.rect().center())
        drain_events(qapp)
        assert_stage_has_no_seams(window)


def test_duplicate_resize_and_editor_round_trip_restore_gapless_picture(window, qapp):
    original = window.active()
    original.state.fit_mode = "cover"
    original.state.crop = (0.11, 0.23, 0.67, 0.59)
    original.state.rotation = 90
    original.state.flip_h = True
    original.apply_state()
    window.duplicate()
    duplicate = window.active()
    for index, pane in enumerate(window.panes.values()):
        feed_solid(pane.canvas, COLORS[index], (319, 181))
    drain_events(qapp)
    for size in ((797, 449), (643, 713), (1023, 643)):
        window.resize(*size)
        drain_events(qapp)
        for pane in window.panes.values():
            assert pane.state.crop == (0.11, 0.23, 0.67, 0.59)
            assert pane.state.rotation == 90
            assert pane.state.flip_h
        assert_stage_has_no_seams(window)
    window.set_clean_mode(False)
    drain_events(qapp)
    assert original.canvas.fill_mode == duplicate.canvas.fill_mode == "cover"
    window.set_clean_mode(True)
    drain_events(qapp)
    assert original.canvas.fill_mode == duplicate.canvas.fill_mode == "cover"
    assert_stage_has_no_seams(window)
    assert original.state.crop == duplicate.state.crop == (0.11, 0.23, 0.67, 0.59)


def test_crop_selection_shows_full_source_then_restores_cover(window, qapp):
    pane = window.active()
    pane.state.fit_mode = "cover"
    pane.state.crop = (0.2, 0.1, 0.6, 0.7)
    pane.state.rotation = 270
    pane.apply_state()
    feed_solid(pane.canvas, COLORS[0], (640, 180))
    drain_events(qapp)
    before = pane.canvas.capture_image()
    pane.canvas.start_crop()
    drain_events(qapp)
    canvas = pane.canvas
    source = canvas.source_size()
    scale = canvas.transform().m11()
    assert scale * source.width() <= canvas.viewport().width() + 1
    assert scale * source.height() <= canvas.viewport().height() + 1
    canvas.cancel_crop()
    drain_events(qapp)
    assert canvas.fill_mode == "cover"
    assert canvas.capture_image() == before
    assert pane.state.crop == (0.2, 0.1, 0.6, 0.7)
