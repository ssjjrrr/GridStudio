"""Transient controls on actual video layers, with deterministic seek spies.

Run the real decoder check separately with GRIDSTUDIO_REAL_HOVER_SEEK=1 to keep
its asynchronous FFmpeg lifetime isolated from the synthetic-frame UI checks.
"""

import os

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from gridstudio.app import MainWindow
from test_app import drain_events, qapp
from test_media import has_decoded_frame, load_pane, sample_video, wait_ready, wait_until
from test_seamless import feed_solid


@pytest.fixture
def hover_window(qapp, monkeypatch):
    def unexpected_modal(_parent, title, message, *_args, **_kwargs):
        pytest.fail(f"Unexpected modal dialog: {title}: {message}")

    monkeypatch.setattr(QMessageBox, "warning", unexpected_modal)
    win = MainWindow()
    win.resize(1000, 700)
    win.show()
    win.activateWindow()
    # These tests exercise user gestures, not the independent looping clock.
    win.playback.timer.stop()
    drain_events(qapp)
    yield win
    if shiboken6.isValid(win):
        win.close()
        win.deleteLater()
    drain_events(qapp)


def synthetic_media(pane, monkeypatch, *, name="hover-example.mp4", color="red", size=(640, 360)):
    """Provide a real painted video item without opening a decoder or a file."""
    clock = {"position": 2400, "duration": 12000}
    pane.state.source = name
    pane.state.loop = False
    monkeypatch.setattr(pane.player, "duration", lambda: clock["duration"])
    monkeypatch.setattr(pane.player, "position", lambda: clock["position"])
    feed_solid(pane.canvas, color, size)
    pane.player.durationChanged.emit(clock["duration"])
    pane.player.positionChanged.emit(clock["position"])
    return clock


def controls(pane):
    assert hasattr(pane, "hover_controls"), "VideoPane must own its transient playback controls"
    return pane.hover_controls


def move_into_picture(pane, app, offset=QPoint()):
    rect = pane.canvas.video_content_rect()
    assert rect is not None and not rect.isEmpty()
    target = rect.center() + offset
    target = QPoint(max(rect.left(), min(rect.right(), target.x())),
                    max(rect.top(), min(rect.bottom(), target.y())))
    # The cursor survives between tests. Moving to its existing global pixel
    # correctly generates no activity, so first visit a different picture pixel.
    if rect.width() > 1:
        adjacent = target + QPoint(1 if target.x() < rect.right() else -1, 0)
    else:
        assert rect.height() > 1, "Hover gesture requires two actual picture pixels"
        adjacent = target + QPoint(0, 1 if target.y() < rect.bottom() else -1)
    QTest.mouseMove(pane.canvas.viewport(), adjacent, delay=5)
    QTest.mouseMove(pane.canvas.viewport(), target, delay=5)
    drain_events(app)


def track_point(bar, ratio):
    rect = bar.track_rect()
    return QPoint(round(rect.left() + ratio * rect.width()), round(rect.center().y()))


def assert_controls_hidden(hover):
    assert not hover.isVisible()
    assert hover.title.isHidden()
    assert hover.bar.isHidden()


def test_mouse_activity_shows_title_and_bar_then_two_seconds_idle_hides_them(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    synthetic_media(pane, monkeypatch)
    drain_events(qapp)
    hover = controls(pane)
    assert_controls_hidden(hover)
    move_into_picture(pane, qapp)
    assert hover.isVisible()
    assert hover.title.isVisible() and hover.bar.isVisible()
    assert "hover-example.mp4" in hover.title.text()
    assert hover.hide_timer.isSingleShot()
    assert hover.hide_timer.interval() == 2000
    QTest.qWait(2150)
    drain_events(qapp)
    assert_controls_hidden(hover)
    move_into_picture(pane, qapp, QPoint(13, 0))
    assert hover.isVisible()


def test_leaving_actual_picture_hides_controls_and_another_layer_gets_its_own(hover_window, qapp, monkeypatch):
    win = hover_window
    first = win.active()
    synthetic_media(first, monkeypatch, name="first.mp4")
    win.canvas_workspace.set_rect(first.state.id, (.04, .1, .4, .65))
    win.add_blank()
    second = win.active()
    synthetic_media(second, monkeypatch, name="second.mp4", color="blue")
    win.canvas_workspace.set_rect(second.state.id, (.56, .1, .4, .65))
    drain_events(qapp)
    first_hover, second_hover = controls(first), controls(second)
    move_into_picture(first, qapp)
    assert first_hover.isVisible()
    move_into_picture(second, qapp)
    assert_controls_hidden(first_hover)
    assert second_hover.isVisible()
    assert "second.mp4" in second_hover.title.text()
    # Move into empty stage rather than merely sending a Leave with a stale cursor.
    QTest.mouseMove(win.canvas_workspace, QPoint(2, 2), delay=5)
    QApplication.sendEvent(second.canvas.viewport(), QEvent(QEvent.Type.Leave))
    drain_events(qapp)
    assert_controls_hidden(second_hover)


def test_idle_over_bar_stays_hidden_after_synthetic_enter_until_pointer_moves(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    synthetic_media(pane, monkeypatch)
    drain_events(qapp)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    point = track_point(hover.bar, .4)
    QTest.mouseMove(hover.bar, point, delay=5)
    drain_events(qapp)
    assert hover.isVisible()
    pointer = hover.bar.mapToGlobal(point)
    QTest.qWait(2150)
    drain_events(qapp)
    assert_controls_hidden(hover)
    # Hiding the bar exposes the video viewport under the same stationary
    # cursor. Its synthetic Enter must not restart the controls or timer.
    QApplication.sendEvent(pane.canvas.viewport(), QEvent(QEvent.Type.Enter))
    drain_events(qapp)
    QTest.qWait(60)
    assert_controls_hidden(hover)
    moved = pane.canvas.viewport().mapFromGlobal(pointer + QPoint(1, 0))
    QTest.mouseMove(pane.canvas.viewport(), moved, delay=5)
    drain_events(qapp)
    assert hover.isVisible()


def test_title_and_seek_bar_stay_within_actual_video_content_rect(hover_window, qapp, monkeypatch):
    win = hover_window
    pane = win.active()
    synthetic_media(pane, monkeypatch, size=(360, 640))
    win.canvas_workspace.set_rect(pane.state.id, (.1, .1, .8, .8))
    drain_events(qapp)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    content = pane.canvas.video_content_rect().translated(
        pane.canvas.viewport().mapTo(pane, QPoint()))
    assert content.width() < pane.width()  # Large horizontal padding is present.
    for widget in (hover.title, hover.bar):
        actual = QRect(widget.mapTo(pane, QPoint()), widget.size())
        assert content.contains(actual), (content, actual)
    saved_rect = pane.state.canvas_rect
    win.resize(840, 620)
    drain_events(qapp)
    assert pane.state.canvas_rect == saved_rect
    hover.note_activity()
    content = pane.canvas.video_content_rect().translated(
        pane.canvas.viewport().mapTo(pane, QPoint()))
    for widget in (hover.title, hover.bar):
        assert content.contains(QRect(widget.mapTo(pane, QPoint()), widget.size()))


def test_seek_bar_previews_hover_and_drag_then_seeks_target_pane_once_on_release(hover_window, qapp, monkeypatch):
    win = hover_window
    pane = win.active()
    clock = synthetic_media(pane, monkeypatch)
    drain_events(qapp)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    bar = hover.bar
    point = track_point(bar, .35)
    QTest.mouseMove(bar, point, delay=5)
    drain_events(qapp)
    assert bar.hover_position == pytest.approx(bar.position_at(point), abs=1)
    assert bar.hover_position == pytest.approx(4200, abs=120)
    calls = []
    monkeypatch.setattr(win.playback, "seek", lambda pane_id, position: calls.append((pane_id, position)))
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=point)
    assert bar.dragging
    assert not hover.hide_timer.isActive()
    QTest.qWait(2100)
    drain_events(qapp)
    assert bar.dragging and hover.isVisible()
    assert calls == []
    end = track_point(bar, .75)
    QTest.mouseMove(bar, end, delay=5)
    drain_events(qapp)
    assert bar.preview_position == pytest.approx(9000, abs=120)
    assert calls == []
    # Decoder position updates during scrubbing must not replace the preview.
    clock["position"] = 3000
    pane.player.positionChanged.emit(3000)
    drain_events(qapp)
    assert bar.preview_position == pytest.approx(9000, abs=120)
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=end)
    drain_events(qapp)
    assert not bar.dragging
    assert calls == [(pane.state.id, bar.position_at(end))]
    assert hover.hide_timer.isActive()


def test_loop_markers_show_ab_or_full_duration_and_clear_when_disabled(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    synthetic_media(pane, monkeypatch)
    hover = controls(pane)
    pane.state.loop = True
    pane.state.loop_start_ms, pane.state.loop_end_ms = 1500, 8750
    hover.refresh()
    assert hover.bar.loop_bounds() == (1500, 8750)
    pane.state.loop_start_ms, pane.state.loop_end_ms = 0, None
    hover.refresh()
    assert hover.bar.loop_bounds() == (0, 12000)
    pane.state.loop = False
    hover.refresh()
    assert hover.bar.loop_bounds() is None


def test_crop_mode_hides_title_and_bar_until_cropping_finishes(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    synthetic_media(pane, monkeypatch)
    drain_events(qapp)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    assert hover.isVisible()
    pane.canvas.start_crop()
    drain_events(qapp)
    assert_controls_hidden(hover)
    hover.note_activity()
    assert_controls_hidden(hover)
    pane.canvas.cancel_crop()
    drain_events(qapp)
    move_into_picture(pane, qapp, QPoint(17, 0))
    assert hover.isVisible()


@pytest.mark.skipif(os.environ.get("GRIDSTUDIO_REAL_HOVER_SEEK") != "1",
                    reason="Run decoder seek separately with GRIDSTUDIO_REAL_HOVER_SEEK=1")
def test_real_video_hover_seek_updates_paused_decoder_frame(hover_window, qapp, sample_video):
    win = hover_window
    pane = load_pane(win, sample_video)
    wait_ready(pane, position_ms=0)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    bar = hover.bar
    end = track_point(bar, .55)
    target_ms = bar.position_at(end)
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=track_point(bar, .2))
    QTest.mouseMove(bar, end, delay=5)
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=end)
    wait_until(lambda: abs(pane.player.position() - target_ms) <= 50
               and has_decoded_frame(pane, target_ms),
               "paused decoded frame after transient seek bar release", panes=[pane])

