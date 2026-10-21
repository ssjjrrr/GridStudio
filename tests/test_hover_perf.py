"""Bound work caused by pointer motion, layer translation, and media signals.

These count expensive UI/native operations instead of measuring noisy wall time.
Synthetic video frames keep the decoder out of the rendering hot-path checks.
"""

from collections import Counter

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from test_app import drain_events, qapp
from test_hover_controls import controls, hover_window, synthetic_media


def prepared_hover(win, app, monkeypatch):
    pane = win.active()
    clock = synthetic_media(pane, monkeypatch)
    drain_events(app)
    hover = controls(pane)
    hover.note_activity()
    drain_events(app)
    assert hover.isVisible()
    return pane, hover, clock


def count_calls(monkeypatch, counts, target, name, key=None):
    original = getattr(target, name)

    def counted(*args, **kwargs):
        counts[key or name] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, counted)


def watch_expensive_ui(monkeypatch, hover):
    counts = Counter()
    count_calls(monkeypatch, counts, hover, "_layout_transport", "layout")
    count_calls(monkeypatch, counts, hover, "_refresh_transport", "transport")
    count_calls(monkeypatch, counts, hover.title, "fontMetrics", "title_metrics")
    for label, widget in (("title", hover.title), ("bar", hover.bar),
                          ("play", hover.play_button), ("mute", hover.mute_button),
                          ("volume", hover.volume_slider)):
        for method in ("show", "raise_", "setGeometry"):
            count_calls(monkeypatch, counts, widget, method, f"{label}.{method}")
    return counts


def test_a_thousand_visible_mouse_moves_do_not_rebuild_controls_or_read_player(hover_window, qapp, monkeypatch):
    pane, hover, _ = prepared_hover(hover_window, qapp, monkeypatch)
    counts = watch_expensive_ui(monkeypatch, hover)
    count_calls(monkeypatch, counts, hover, "refresh", "refresh")
    count_calls(monkeypatch, counts, pane.player, "duration", "native_duration")
    count_calls(monkeypatch, counts, pane.player, "position", "native_position")
    viewport = pane.canvas.viewport()
    center = pane.canvas.video_content_rect().center()

    for index in range(1000):
        point = center + QPoint(index % 31, (index // 31) % 17)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point),
                            QPointF(viewport.mapToGlobal(point)), Qt.MouseButton.NoButton,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(viewport, event)

    assert hover.isVisible()
    assert hover.hide_timer.isActive()
    assert counts == {}, counts


def test_translating_a_layer_keeps_overlay_geometry_and_does_not_relayout(hover_window, qapp, monkeypatch):
    win = hover_window
    pane = win.active()
    win.canvas_workspace.set_rect(pane.state.id, (.1, .1, .65, .65))
    pane, hover, _ = prepared_hover(win, qapp, monkeypatch)
    counts = watch_expensive_ui(monkeypatch, hover)
    title_rect, bar_rect = QRect(hover.title.geometry()), QRect(hover.bar.geometry())
    original = pane.pos()

    for index in range(400):
        pane.move(original + QPoint(index % 37, index % 19))

    assert hover.title.geometry() == title_rect
    assert hover.bar.geometry() == bar_rect
    assert counts == {}, counts


def test_redundant_picture_geometry_notifications_do_not_mutate_widgets(hover_window, qapp, monkeypatch):
    pane, hover, _ = prepared_hover(hover_window, qapp, monkeypatch)
    counts = watch_expensive_ui(monkeypatch, hover)

    for _ in range(500):
        pane.canvas.contentGeometryChanged.emit()

    assert counts == {}, counts
    assert hover.isVisible()


def test_real_resize_and_source_change_still_refresh_picture_aligned_controls(hover_window, qapp, monkeypatch):
    win = hover_window
    pane, hover, _ = prepared_hover(win, qapp, monkeypatch)
    previous = QRect(hover.bar.geometry())
    win.canvas_workspace.set_rect(pane.state.id, (.1, .1, .55, .8))
    drain_events(qapp)
    assert hover.bar.geometry() != previous
    picture = pane.canvas.video_content_rect().translated(pane.canvas.viewport().mapTo(pane, QPoint()))
    for widget in (hover.title, hover.bar):
        assert picture.contains(QRect(widget.mapTo(pane, QPoint()), widget.size()))

    counts = watch_expensive_ui(monkeypatch, hover)
    pane.state.source = "renamed-video-with-a-distinct-title.mp4"
    hover.refresh()
    assert hover.title.toolTip() == pane.state.source
    assert "renamed" in hover.title.text()
    assert counts["title_metrics"] == 1
    assert counts["layout"] == 0
    assert not any(counts[f"{name}.show"] or counts[f"{name}.raise_"]
                   for name in ("title", "bar", "play", "mute", "volume"))

    pane.canvas.set_transform(rotation=90)
    drain_events(qapp)
    picture = pane.canvas.video_content_rect().translated(pane.canvas.viewport().mapTo(pane, QPoint()))
    assert picture.contains(hover.title.geometry())
    assert picture.contains(hover.bar.geometry())


def test_position_updates_only_update_timeline_and_changed_time_text(hover_window, qapp, monkeypatch):
    pane, hover, _ = prepared_hover(hover_window, qapp, monkeypatch)
    # Measure this overlay's signal consumer independently of the permanent
    # grid inspector, which owns a separate positionChanged connection.
    pane.player.positionChanged.disconnect(pane.on_position)
    counts = watch_expensive_ui(monkeypatch, hover)
    count_calls(monkeypatch, counts, pane.player, "duration", "native_duration")
    count_calls(monkeypatch, counts, hover.time_label, "setText", "time_text")
    count_calls(monkeypatch, counts, hover.time_label, "fontMetrics", "time_metrics")

    for position in range(2401, 2801):
        pane.player.positionChanged.emit(position)
    drain_events(qapp)

    assert hover.bar._position == 2800
    assert hover.time_label.text() == "00:02 / 00:12"
    assert counts == {}, counts
    pane.player.positionChanged.emit(3000)
    drain_events(qapp)
    assert hover.time_label.text() == "00:03 / 00:12"
    assert counts["time_text"] == 1
    assert counts["time_metrics"] == 1
    assert counts["layout"] == 0
    assert counts["transport"] == 0
    assert counts["title_metrics"] == 0


def test_programmatic_refreshes_do_not_reveal_hidden_controls_or_start_idle_timer(hover_window, qapp, monkeypatch):
    pane, hover, _ = prepared_hover(hover_window, qapp, monkeypatch)
    hover.hide_now()
    counts = watch_expensive_ui(monkeypatch, hover)

    for _ in range(100):
        hover.refresh()
        pane.player.positionChanged.emit(2500)
        pane.canvas.contentGeometryChanged.emit()

    assert not hover.isVisible()
    assert not hover.hide_timer.isActive()
    assert hover.title.isHidden() and hover.bar.isHidden()
    assert counts["layout"] == 0
    assert counts["title_metrics"] == 0
    assert not any(counts[f"{name}.show"] or counts[f"{name}.raise_"]
                   for name in ("title", "bar", "play", "mute", "volume"))
