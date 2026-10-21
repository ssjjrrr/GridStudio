"""Visible-correctness regressions around interaction caching and small damage.

Only synthetic QVideoFrames are used, so these checks do not open decoders.
"""

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtTest import QTest

from test_app import drain_events, qapp
from test_hover_controls import controls, hover_window, move_into_picture, synthetic_media, track_point
from test_seamless import feed_solid, matches


def test_cancelled_scrub_restores_actual_time_when_paused_controls_reappear(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    clock = synthetic_media(pane, monkeypatch)
    drain_events(qapp)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    bar = hover.bar
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=track_point(bar, .25))
    try:
        QTest.mouseMove(bar, track_point(bar, .75), delay=5)
        assert hover.time_label.text().startswith("00:09")
        assert bar.dragging
        # Entering crop mode cancels a scrub without changing paused media position.
        pane.canvas.start_crop()
        assert not hover.isVisible()
        assert not bar.dragging
        assert clock["position"] == 2400
        pane.canvas.cancel_crop()
        hover.note_activity()
        assert hover.isVisible()
        assert hover.time_label.text() == "00:02 / 00:12"
    finally:
        # Hiding the grabbed bar cancels the product's scrub, but QtTest keeps
        # its simulated mouse button pressed until an explicit release. Pair
        # the input even if an assertion fails, so later hover gestures move
        # the actual cursor rather than leaking a held-button synthetic drag.
        QTest.mouseRelease(pane.canvas.viewport(), Qt.MouseButton.LeftButton,
                           pos=pane.canvas.viewport().rect().center())


def test_first_shown_selection_move_damages_old_and_new_handles_only(hover_window, qapp, monkeypatch):
    win = hover_window
    pane = win.active()
    pane.state.fit_mode = "stretch"
    pane.apply_state()
    feed_solid(pane.canvas, "red")
    stage = win.canvas_workspace
    stage.set_rect(pane.state.id, (.08, .08, .3, .32))
    win.set_clean_mode(False)
    drain_events(qapp)
    overlay = stage._overlay
    old = QRect(pane.geometry())
    # Force first-show painting before any explicit update_selection call can
    # establish its old outline; this was the source of the first-move halo.
    overlay._painted_region = QRegion()
    overlay.repaint()
    damages = []
    original_update = overlay.update

    def record_damage(*args):
        if args and isinstance(args[0], QRegion):
            damages.append(QRegion(args[0]))
        original_update(*args)

    monkeypatch.setattr(overlay, "update", record_damage)
    stage.set_rect(pane.state.id, (.57, .52, .3, .32))
    new = QRect(pane.geometry())
    assert damages
    damage = QRegion()
    for region in damages:
        damage |= region
    for rect in (old, new):
        for point in stage._handle_points(rect).values():
            assert damage.contains(point.toPoint()), (rect, point, damage)
        assert not damage.contains(rect.center()), "Whole video interiors must not be invalidated"


def test_selection_switch_erases_old_outline_and_hiding_leaves_video_clean(hover_window, qapp):
    win = hover_window
    first = win.active()
    win.add_blank()
    second = win.active()
    stage = win.canvas_workspace
    for pane, color, rect in ((first, "red", (.08, .1, .35, .4)),
                              (second, "blue", (.55, .45, .35, .4))):
        pane.state.fit_mode = "stretch"
        pane.apply_state()
        feed_solid(pane.canvas, color)
        stage.set_rect(pane.state.id, rect)
    win.set_clean_mode(False)
    win.select(first.state.id)
    drain_events(qapp)
    win.select(second.state.id)
    drain_events(qapp)
    win.set_clean_mode(True)
    drain_events(qapp)
    image = win.stage.grab().toImage()
    for pane, color in ((first, "red"), (second, "blue")):
        origin = pane.mapTo(win.stage, QPoint())
        for x, y in ((2, 2), (pane.width() // 2, 2),
                     (pane.width() - 3, pane.height() // 2),
                     (pane.width() // 2, pane.height() - 3)):
            assert matches(image.pixelColor(origin + QPoint(x, y)), color)


def test_canvas_cached_fit_keeps_rotation_and_mirror_pixel_changes(hover_window, qapp):
    pane = hover_window.active()
    canvas = pane.canvas
    source = QImage(160, 90, QImage.Format.Format_RGB32)
    painter = QPainter(source)
    painter.fillRect(0, 0, 80, 90, QColor("red"))
    painter.fillRect(80, 0, 80, 90, QColor("blue"))
    painter.end()
    canvas.set_has_media(True)
    canvas.set_message("")
    canvas.video_item.videoSink().setVideoFrame(QVideoFrame(source))
    drain_events(qapp)

    def picture_colors():
        image = canvas.capture_image()
        picture = canvas.video_content_rect()
        return (image.pixelColor(picture.x() + picture.width() // 4, picture.center().y()),
                image.pixelColor(picture.x() + picture.width() * 3 // 4, picture.center().y()))

    left, right = picture_colors()
    assert matches(left, "red") and matches(right, "blue")
    canvas.set_transform(rotation=180)
    drain_events(qapp)
    left, right = picture_colors()
    assert matches(left, "blue") and matches(right, "red")
    canvas.set_transform(flip_h=True)
    drain_events(qapp)
    left, right = picture_colors()
    assert matches(left, "blue") and matches(right, "red")
    canvas.set_transform()
    drain_events(qapp)
    left, right = picture_colors()
    assert matches(left, "red") and matches(right, "blue")


def test_canvas_fit_cache_invalidates_for_modes_new_source_size_and_crop(hover_window, qapp):
    pane = hover_window.active()
    canvas = pane.canvas
    feed_solid(canvas, "red", (640, 360))
    drain_events(qapp)
    original = QRect(canvas.video_content_rect())
    assert original.height() < canvas.viewport().height()
    canvas.set_fill_mode("cover")
    assert canvas.video_content_rect() == canvas.viewport().rect()
    canvas.set_fill_mode("stretch")
    assert canvas.video_content_rect() == canvas.viewport().rect()
    assert canvas.transform().m11() != canvas.transform().m22()
    canvas.set_fill_mode("contain")
    assert canvas.video_content_rect() == original
    feed_solid(canvas, "blue", (360, 640))
    drain_events(qapp)
    portrait = QRect(canvas.video_content_rect())
    assert portrait.width() < original.width()
    canvas.set_transform(crop=(0, .1, 1, .4), rotation=90)
    drain_events(qapp)
    cropped = QRect(canvas.video_content_rect())
    canvas.start_crop()
    assert canvas.video_content_rect() is None
    canvas.cancel_crop()
    assert canvas.video_content_rect() == cropped
    canvas.set_transform()
    assert canvas.video_content_rect() == portrait


def test_revealed_grid_header_is_elided_for_the_current_width_after_hidden_resizes(hover_window, qapp):
    win = hover_window
    pane = win.active()
    pane.state.source = "very-long-video-title-" * 12 + ".mp4"
    win.set_layout_mode("grid")
    win.set_clean_mode(True)
    for size in ((700, 400), (1100, 700), (800, 500)):
        win.resize(*size)
        drain_events(qapp)
    win.set_clean_mode(False)
    drain_events(qapp)
    expected = pane.header.title.fontMetrics().elidedText(
        pane.state.source, Qt.TextElideMode.ElideMiddle, max(40, pane.header.title.width()))
    assert pane.header.title.isVisible()
    assert pane.header.title.text() == expected


def test_duration_text_cache_tracks_source_reset_without_duplicate_same_second_updates(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    calls = []
    original_set_text = pane.time_label.setText

    def record_text(text):
        calls.append(text)
        original_set_text(text)

    monkeypatch.setattr(pane.time_label, "setText", record_text)
    pane.on_duration(12000)
    pane.on_position(2100)
    for position in range(2101, 2900):
        pane.on_position(position)
    assert pane.time_label.text() == "00:02 / 00:12"
    assert calls.count("00:02 / 00:12") == 1
    pane.on_duration(0)
    assert pane.time_label.text() == "00:00 / 00:00"
    pane.on_duration(65000)
    pane.on_position(3000)
    assert pane.time_label.text() == "00:03 / 01:05"
