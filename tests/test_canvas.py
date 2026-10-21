"""Pixel and mouse-interaction checks against the actual Qt video renderer."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtTest import QTest
from scripts.qt_test_support import qt_wait
from PySide6.QtWidgets import QApplication

from gridstudio.canvas import VideoCanvas


@pytest.fixture(scope="session")
def canvas_app():
    app = QApplication.instance() or QApplication([])
    yield app


def drain(app):
    app.processEvents()
    qt_wait(5)
    app.processEvents()


@pytest.fixture
def canvas(canvas_app):
    widget = VideoCanvas()
    widget.resize(640, 480)
    widget.show()

    # The crop below selects only the right half.  The excluded red/blue
    # quadrants make leakage from the full video detectable in rendered pixels.
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    painter = QPainter(image)
    painter.fillRect(0, 100, 200, 100, QColor("blue"))
    painter.fillRect(200, 0, 200, 100, QColor("lime"))
    painter.fillRect(200, 100, 200, 100, QColor("yellow"))
    painter.end()
    widget.set_has_media(True)
    widget.video_item.videoSink().setVideoFrame(QVideoFrame(image))
    drain(canvas_app)
    assert widget.source_size().width() == 400
    assert widget.source_size().height() == 200
    yield widget
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    drain(canvas_app)


def pixel(image, x, y):
    """Sample relative to the captured bitmap, independent of Windows DPI."""
    return image.pixelColor(round((image.width() - 1) * x),
                            round((image.height() - 1) * y))


def assert_color(actual, expected):
    target = QColor(expected)
    assert abs(actual.red() - target.red()) <= 3
    assert abs(actual.green() - target.green()) <= 3
    assert abs(actual.blue() - target.blue()) <= 3


@pytest.mark.parametrize("rotation, samples", [
    (0, [(0.5, 0.3, "lime"), (0.5, 0.7, "yellow")]),
    (90, [(0.35, 0.5, "yellow"), (0.65, 0.5, "lime")]),
    (180, [(0.5, 0.3, "yellow"), (0.5, 0.7, "lime")]),
    (270, [(0.35, 0.5, "lime"), (0.65, 0.5, "yellow")]),
])
def test_source_crop_and_rotation_render_the_selected_pixels(canvas, canvas_app, rotation, samples):
    canvas.set_transform((0.5, 0, 0.5, 1), rotation, False, False)
    drain(canvas_app)
    rendered = canvas.capture_image()
    for x, y, expected in samples:
        assert_color(pixel(rendered, x, y), expected)


@pytest.mark.parametrize("flip_h, flip_v, left, right", [
    (True, False, "lime", "yellow"),
    (False, True, "yellow", "lime"),
    (True, True, "lime", "yellow"),
])
def test_mirroring_applies_to_the_displayed_rotated_image(canvas, canvas_app, flip_h, flip_v, left, right):
    canvas.set_transform((0.5, 0, 0.5, 1), 90, flip_h, flip_v)
    drain(canvas_app)
    rendered = canvas.capture_image()
    assert_color(pixel(rendered, 0.35, 0.5), left)
    assert_color(pixel(rendered, 0.65, 0.5), right)


@pytest.mark.parametrize("size", [(640, 480), (300, 600), (760, 260)])
def test_crop_fits_after_resize_without_bleeding_excluded_pixels(canvas, canvas_app, size):
    canvas.set_transform((0.5, 0, 0.5, 1), 90, False, False)
    canvas.resize(*size)
    drain(canvas_app)
    image = canvas.capture_image()
    width, height = image.width(), image.height()
    # Every retained pixel contains full green.  Excluded pure red and blue
    # must not leak out of the clipping parent into the letterbox region.
    for y in range(0, height, 7):
        for x in range(0, width, 7):
            color = image.pixelColor(x, y)
            assert not (color.red() > 220 and color.green() < 30 and color.blue() < 30)
            assert not (color.blue() > 220 and color.red() < 30 and color.green() < 30)
    assert_color(image.pixelColor(0, 0), "#0b1018")
    assert_color(image.pixelColor(width - 1, height - 1), "#0b1018")
    horizontal = [x for x in range(width) if image.pixelColor(x, height // 2).green() > 220]
    vertical = [y for y in range(height) if image.pixelColor(width // 2, y).green() > 220]
    assert horizontal and vertical
    content_width = horizontal[-1] - horizontal[0] + 1
    content_height = vertical[-1] - vertical[0] + 1
    assert abs(content_width - content_height) <= 3  # The cropped source is square.
    assert min(width, height) - 12 <= content_width <= min(width, height)


@pytest.mark.parametrize("reverse", [False, True])
def test_mouse_crop_uses_original_source_coordinates_and_restores_previous_transform(canvas, canvas_app, reverse):
    canvas.set_transform((0.5, 0, 0.5, 1), 90, True, False)
    drain(canvas_app)
    before = canvas.capture_image()
    selected = []
    canvas.cropSelected.connect(selected.append)
    canvas.start_crop()
    drain(canvas_app)
    # The selection view must show the unrotated source, despite the previous
    # crop, rotation and mirror.  Dragging backwards yields the same source box.
    start = canvas.mapFromScene(QPointF(60, 40))
    end = canvas.mapFromScene(QPointF(280, 160))
    if reverse:
        start, end = end, start
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    drain(canvas_app)
    assert len(selected) == 1
    assert selected[0] == pytest.approx((0.15, 0.2, 0.55, 0.6), abs=0.008)
    assert not canvas.crop_active
    # The caller decides whether to adopt the selection; until then the
    # previous rendering is restored exactly.
    assert canvas.capture_image() == before


def test_escape_cancels_a_partially_dragged_crop_without_emitting_selection(canvas, canvas_app):
    canvas.set_transform((0.5, 0, 0.5, 1), 270, False, True)
    drain(canvas_app)
    before = canvas.capture_image()
    selected = []
    canvas.cropSelected.connect(selected.append)
    canvas.start_crop()
    drain(canvas_app)
    start = canvas.mapFromScene(QPointF(20, 20))
    end = canvas.mapFromScene(QPointF(300, 170))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    drain(canvas_app)
    assert not canvas.crop_active
    assert selected == []
    assert canvas.capture_image() == before


def test_tiny_crop_stays_in_selection_mode_until_cancelled(canvas, canvas_app):
    selected = []
    canvas.cropSelected.connect(selected.append)
    canvas.start_crop()
    drain(canvas_app)
    start = canvas.mapFromScene(QPointF(100, 100))
    end = canvas.mapFromScene(QPointF(103, 102))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    drain(canvas_app)
    assert canvas.crop_active
    assert selected == []
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert not canvas.crop_active
