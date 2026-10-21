"""Rendering work budgets and layer lifetime, using synthetic frames only."""

from collections import Counter

import shiboken6
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QImage, QRegion
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gridstudio.app import VideoPane
from gridstudio.model import PaneState
from test_app import drain_events, qapp
from test_free_canvas import canvas_window
from test_hover_controls import controls, hover_window, move_into_picture, synthetic_media
from test_seamless import feed_solid, matches


class WidgetEvents(QObject):
    def __init__(self, widget):
        super().__init__()
        self.counts = Counter()
        self.paints = []
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Hide, QEvent.Type.Show, QEvent.Type.ParentChange,
                            QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.ZOrderChange):
            self.counts[event.type()] += 1
        elif event.type() == QEvent.Type.Paint:
            self.paints.append(QRegion(event.region()))
        return False


def add_without_rebuild(win):
    state = PaneState(canvas_rect=(.55, .1, .35, .4), z_order=len(win.panes))
    pane = VideoPane(win, state)
    win.panes[state.id] = pane
    return pane


def test_sync_adding_and_removing_a_layer_preserves_retained_widget_and_hover(canvas_window, qapp, monkeypatch):
    win = canvas_window
    retained = win.active()
    synthetic_media(retained, monkeypatch)
    stage = win.canvas_workspace
    stage.set_rect(retained.state.id, (.05, .1, .4, .55))
    drain_events(qapp)
    hover = controls(retained)
    move_into_picture(retained, qapp)
    assert hover.isVisible()
    hit = QApplication.widgetAt(QCursor.pos())
    assert hit is retained or (hit is not None and retained.isAncestorOf(hit)), (
        "The lifetime check requires the actual pointer over the retained picture", QCursor.pos(), hit)
    original_rect = QRect(retained.geometry())
    observer = WidgetEvents(retained)
    original_player = retained.player
    added = add_without_rebuild(win)

    stage.sync_panes(win.panes.values())
    drain_events(qapp)
    assert retained.parentWidget() is stage
    assert retained.player is original_player
    assert retained.geometry() == original_rect
    pointer = QCursor.pos()
    hit = QApplication.widgetAt(pointer)
    assert hover.isVisible(), {
        "pointer": pointer, "local": retained.mapFromGlobal(pointer),
        "picture": hover._content_rect, "hit": repr(hit),
        "inside_retained": hit is retained or (hit is not None and retained.isAncestorOf(hit)),
        "active_window": repr(qapp.activeWindow()), "pane_visible": retained.isVisible(),
        "widget_events": observer.counts,
    }
    assert not any(observer.counts[kind] for kind in
                   (QEvent.Type.Hide, QEvent.Type.Show, QEvent.Type.ParentChange, QEvent.Type.Resize))

    win.panes.pop(added.state.id)
    stage.sync_panes(win.panes.values())
    assert added.parentWidget() is win.pane_parking
    added.dispose()
    drain_events(qapp)
    assert hover.isVisible()
    assert retained.geometry() == original_rect
    assert not any(observer.counts[kind] for kind in
                   (QEvent.Type.Hide, QEvent.Type.Show, QEvent.Type.ParentChange, QEvent.Type.Resize))


def test_sync_same_id_replacement_removes_old_filters_and_adopts_new_object(canvas_window, qapp):
    win = canvas_window
    stage = win.canvas_workspace
    old = win.active()
    replacement = VideoPane(win, PaneState(id=old.state.id, canvas_rect=(.1, .1, .7, .6)))
    win.panes[old.state.id] = replacement
    stage.sync_panes(win.panes.values())
    assert stage._panes[replacement.state.id] is replacement
    assert replacement.parentWidget() is stage
    assert old.parentWidget() is win.pane_parking
    assert all(target not in stage._filtered for target in (old, old.canvas, old.canvas.viewport()))
    assert all(target in stage._filtered for target in
               (replacement, replacement.canvas, replacement.canvas.viewport()))
    old.dispose()
    drain_events(qapp)
    assert shiboken6.isValid(replacement)
    assert replacement.isVisible()


def test_sync_tolerates_an_already_deleted_removed_pane(canvas_window, qapp):
    win = canvas_window
    stage = win.canvas_workspace
    removed = win.active()
    win.panes.clear()
    win.active_id = None
    removed.dispose()
    drain_events(qapp)
    assert not shiboken6.isValid(removed)
    stage.sync_panes([])
    assert stage._panes == {}
    assert stage._filtered == {}


def test_repeated_membership_sync_does_not_raise_already_ordered_videos(canvas_window, qapp):
    win = canvas_window
    win.add_blank()
    stage = win.canvas_workspace
    drain_events(qapp)
    observers = [WidgetEvents(pane) for pane in win.panes.values()]
    for _ in range(30):
        stage.sync_panes(win.panes.values())
    assert all(observer.counts[QEvent.Type.ZOrderChange] == 0 for observer in observers)


def test_hidden_hover_position_updates_store_data_without_formatting_or_repaint(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    clock = synthetic_media(pane, monkeypatch)
    drain_events(qapp)
    hover = controls(pane)
    hover.note_activity()
    hover.hide_now()
    calls = Counter()
    original_text = hover._refresh_time_label
    original_update = hover.bar.update

    def record_text():
        calls["text"] += 1
        return original_text()

    def record_update(*args):
        calls["paint_request"] += 1
        return original_update(*args)

    # Restore Qt widget attributes before the window fixture deletes their
    # native objects; undoing a method override on a deleted PySide QWidget
    # can dereference its already-destroyed C++ meta-object.
    with monkeypatch.context() as patch:
        patch.setattr(hover, "_refresh_time_label", record_text)
        patch.setattr(hover.bar, "update", record_update)
        for position in range(2401, 10001):
            clock["position"] = position
            pane.player.positionChanged.emit(position)
        assert hover.bar._position == 10000
        assert calls == {}, calls
        assert not hover.hide_timer.isActive()

        hover.note_activity()
        assert hover.time_label.text() == "00:10 / 00:12"
        assert hover.isVisible()
        assert calls["text"] == 1


def test_repeated_canvas_media_flags_do_not_invalidate_unchanged_picture(canvas_window, qapp, monkeypatch):
    canvas = canvas_window.active().canvas
    feed_solid(canvas, "red")
    drain_events(qapp)
    signals, updates = [], []
    canvas.contentGeometryChanged.connect(lambda: signals.append(True))
    original_update = canvas.viewport().update

    def record_update(*args):
        updates.append(args)
        return original_update(*args)

    with monkeypatch.context() as patch:
        patch.setattr(canvas.viewport(), "update", record_update)
        for _ in range(300):
            canvas.set_has_media(True)
            canvas.set_message("")
        assert signals == []
        assert updates == []
        canvas.set_message("播放错误")
        assert canvas.video_content_rect() is None
        canvas.set_message("")
        assert canvas.video_content_rect() is not None
        assert len(signals) == 2


def test_small_crop_selection_paints_a_bounded_region_without_full_view_redraw(canvas_window, qapp):
    pane = canvas_window.active()
    canvas = pane.canvas
    feed_solid(canvas, "red")
    canvas.start_crop()
    drain_events(qapp)
    observer = WidgetEvents(canvas.viewport())
    start = canvas.mapFromScene(QPointF(120, 120))
    end = start + QPoint(35, 25)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    drain_events(qapp)
    QTest.mouseMove(canvas.viewport(), end, delay=5)
    drain_events(qapp)
    assert observer.paints
    view_area = canvas.viewport().width() * canvas.viewport().height()
    assert all(region.boundingRect().width() * region.boundingRect().height() < view_area / 2
               for region in observer.paints)
    canvas.cancel_crop()
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)


def test_occluded_video_keeps_receiving_frames_and_reveals_latest_without_changing_quality(canvas_window, qapp):
    win = canvas_window
    bottom = win.active()
    win.add_blank()
    top = win.active()
    stage = win.canvas_workspace
    for pane, color in ((bottom, "red"), (top, "blue")):
        pane.state.fit_mode = "stretch"
        pane.apply_state()
        stage.set_rect(pane.state.id, (0, 0, 1, 1))
        feed_solid(pane.canvas, color)
    drain_events(qapp)
    assert top.geometry() == bottom.geometry()
    frame = QImage(640, 360, QImage.Format.Format_RGB32)
    frame.fill(QColor("lime"))
    bottom.canvas.video_item.videoSink().setVideoFrame(QVideoFrame(frame))
    drain_events(qapp)
    assert matches(win.stage.grab().toImage().pixelColor(100, 100), "blue")
    stage.move_layer(bottom.state.id, "front")
    drain_events(qapp)
    assert matches(win.stage.grab().toImage().pixelColor(100, 100), "lime")
    assert bottom.canvas.source_size().width() == 640
    assert bottom.canvas.source_size().height() == 360
