"""Playback and audio controls belong to the hovered video, without layout UI."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QStyle, QStyleOptionSlider

from test_app import drain_events, qapp
from test_hover_controls import controls, hover_window, move_into_picture, synthetic_media
from test_media import load_pane, sample_video, wait_ready, wait_until
from test_seamless import matches


def transport(hover):
    widgets = (hover.play_button, hover.mute_button, hover.volume_slider)
    assert hover.volume_slider.minimum() == 0
    assert hover.volume_slider.maximum() == 100
    return widgets


def handle_center(slider):
    option = QStyleOptionSlider()
    slider.initStyleOption(option)
    return slider.style().subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                         QStyle.SubControl.SC_SliderHandle, slider).center()


def make_pair(win, app, monkeypatch):
    first = win.active()
    synthetic_media(first, monkeypatch, name="first.mp4", color="red")
    win.canvas_workspace.set_rect(first.state.id, (.04, .1, .4, .65))
    win.add_blank()
    second = win.active()
    synthetic_media(second, monkeypatch, name="second.mp4", color="blue")
    win.canvas_workspace.set_rect(second.state.id, (.56, .1, .4, .65))
    drain_events(app)
    return first, second


def test_transport_shows_and_hides_with_title_and_timeline_after_two_seconds(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    synthetic_media(pane, monkeypatch)
    drain_events(qapp)
    hover = controls(pane)
    widgets = transport(hover)
    assert all(not widget.isVisible() for widget in widgets)
    move_into_picture(pane, qapp)
    assert hover.title.isVisible() and hover.bar.isVisible()
    assert all(widget.isVisible() for widget in widgets)
    QTest.qWait(2150)
    drain_events(qapp)
    assert not hover.isVisible()
    assert all(not widget.isVisible() for widget in widgets)
    move_into_picture(pane, qapp, QPoint(11, 0))
    assert all(widget.isVisible() for widget in widgets)
    hover.hide_now()
    assert all(not widget.isVisible() for widget in widgets)


def test_play_pause_button_uses_its_own_pane_even_when_another_is_selected(hover_window, qapp, monkeypatch):
    win = hover_window
    first, second = make_pair(win, qapp, monkeypatch)
    hover = controls(second)
    playback = {"state": QMediaPlayer.PlaybackState.PausedState}
    monkeypatch.setattr(second.player, "playbackState", lambda: playback["state"])
    calls = []

    def set_playing(pane_id, playing):
        calls.append((pane_id, playing))
        playback["state"] = (QMediaPlayer.PlaybackState.PlayingState if playing
                             else QMediaPlayer.PlaybackState.PausedState)
        second.state.paused = not playing
        second.player.playbackStateChanged.emit(playback["state"])

    monkeypatch.setattr(win.playback, "set_playing", set_playing)
    win.select(first.state.id)
    order = {pane.state.id: pane.state.z_order for pane in win.panes.values()}
    move_into_picture(second, qapp)
    QTest.mouseClick(hover.play_button, Qt.MouseButton.LeftButton)
    drain_events(qapp)
    assert calls == [(second.state.id, True)]
    assert "暂停" in hover.play_button.toolTip()
    QTest.mouseClick(hover.play_button, Qt.MouseButton.LeftButton)
    drain_events(qapp)
    assert calls == [(second.state.id, True), (second.state.id, False)]
    assert "播放" in hover.play_button.toolTip()
    assert order == {pane.state.id: pane.state.z_order for pane in win.panes.values()}


def test_mute_button_and_positive_volume_keep_audio_and_saved_state_consistent(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    synthetic_media(pane, monkeypatch)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    assert pane.state.muted and pane.audio.isMuted()
    QTest.mouseClick(hover.mute_button, Qt.MouseButton.LeftButton)
    drain_events(qapp)
    assert not pane.state.muted and not pane.audio.isMuted()
    QTest.mouseClick(hover.mute_button, Qt.MouseButton.LeftButton)
    drain_events(qapp)
    assert pane.state.muted and pane.audio.isMuted()
    hover.volume_slider.setValue(73)
    drain_events(qapp)
    assert pane.state.volume == pytest.approx(.73)
    assert pane.audio.volume() == pytest.approx(.73)
    assert not pane.state.muted and not pane.audio.isMuted()
    assert hover.volume_slider.value() == 73


def test_external_mute_playback_and_audio_changes_refresh_transport_ui(hover_window, qapp, monkeypatch):
    pane = hover_window.active()
    synthetic_media(pane, monkeypatch)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    # This is the same action used by the window's M shortcut.
    pane.toggle_mute()
    drain_events(qapp)
    assert not pane.audio.isMuted()
    assert not hover.mute_button.property("muted")
    pane.toggle_mute()
    drain_events(qapp)
    assert pane.audio.isMuted()
    assert hover.mute_button.property("muted")
    pane.audio.setVolume(.37)
    drain_events(qapp)
    assert hover.volume_slider.value() == 37
    pane.audio.setMuted(False)
    drain_events(qapp)
    assert not hover.mute_button.property("muted")
    state = {"value": QMediaPlayer.PlaybackState.PlayingState}
    monkeypatch.setattr(pane.player, "playbackState", lambda: state["value"])
    pane.player.playbackStateChanged.emit(state["value"])
    drain_events(qapp)
    assert "暂停" in hover.play_button.toolTip()
    state["value"] = QMediaPlayer.PlaybackState.PausedState
    pane.player.playbackStateChanged.emit(state["value"])
    drain_events(qapp)
    assert "播放" in hover.play_button.toolTip()


def test_volume_drag_stays_visible_without_seeking_or_moving_video(hover_window, qapp, monkeypatch):
    win = hover_window
    pane = win.active()
    synthetic_media(pane, monkeypatch)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    slider = hover.volume_slider
    start = handle_center(slider)
    saved_rect = pane.state.canvas_rect
    seek_calls = []
    monkeypatch.setattr(win.playback, "seek", lambda *args: seek_calls.append(args))
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=start)
    assert slider.isSliderDown()
    assert not hover.hide_timer.isActive()
    QTest.qWait(2100)
    drain_events(qapp)
    assert hover.isVisible() and slider.isVisible()
    assert slider.isSliderDown()
    end = QPoint(min(slider.width() - 2, start.x() + max(5, slider.width() // 4)), start.y())
    QTest.mouseMove(slider, end, delay=5)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=end)
    drain_events(qapp)
    assert not slider.isSliderDown()
    assert hover.hide_timer.isActive()
    assert pane.state.volume == pytest.approx(slider.value() / 100)
    assert pane.audio.volume() == pytest.approx(slider.value() / 100)
    assert pane.state.canvas_rect == saved_rect
    assert win.canvas_workspace._drag is None
    assert seek_calls == []


def test_each_pane_keeps_its_own_volume_and_z_order(hover_window, qapp, monkeypatch):
    win = hover_window
    first, second = make_pair(win, qapp, monkeypatch)
    order = {pane.state.id: pane.state.z_order for pane in (first, second)}
    move_into_picture(first, qapp)
    controls(first).volume_slider.setValue(24)
    move_into_picture(second, qapp)
    controls(second).volume_slider.setValue(81)
    drain_events(qapp)
    assert (first.state.volume, second.state.volume) == pytest.approx((.24, .81))
    assert (first.audio.volume(), second.audio.volume()) == pytest.approx((.24, .81))
    assert not first.state.muted and not second.state.muted
    assert order == {pane.state.id: pane.state.z_order for pane in (first, second)}
    assert not controls(first).play_button.isVisible()
    assert controls(second).play_button.isVisible()


def test_narrow_picture_transport_stays_inside_content_and_padding_still_shows_lower_layer(hover_window, qapp, monkeypatch):
    win = hover_window
    bottom = win.active()
    synthetic_media(bottom, monkeypatch, color="lime")
    bottom.state.fit_mode = "stretch"
    bottom.apply_state()
    win.add_blank()
    top = win.active()
    synthetic_media(top, monkeypatch, name="portrait.mp4", size=(160, 640), color="red")
    win.canvas_workspace.set_rect(top.state.id, (.2, .15, .6, .6))
    drain_events(qapp)
    hover = controls(top)
    move_into_picture(top, qapp)
    content = top.canvas.video_content_rect().translated(top.canvas.viewport().mapTo(top, QPoint()))
    assert content.width() < 120
    widget_rects = []
    for widget in transport(hover):
        assert widget.isVisible()
        rect = QRect(widget.mapTo(top, QPoint()), widget.size())
        assert content.contains(rect), (content, rect)
        widget_rects.append(rect)
    for index, rect in enumerate(widget_rects):
        assert all(not rect.intersects(other) for other in widget_rects[index + 1:])
    origin = top.mapTo(win.stage, QPoint())
    padding = origin + QPoint(2, top.height() // 2)
    image = win.stage.grab().toImage()
    assert matches(image.pixelColor(padding), "lime")
    assert win.stage.childAt(padding) is bottom.canvas.viewport()


@pytest.mark.skipif(os.environ.get("GRIDSTUDIO_REAL_HOVER_TRANSPORT") != "1",
                    reason="Run real media transport separately with GRIDSTUDIO_REAL_HOVER_TRANSPORT=1")
def test_real_media_buttons_play_pause_and_volume_update_audio(hover_window, qapp, sample_video):
    win = hover_window
    pane = load_pane(win, sample_video, position_ms=0, paused=True)
    wait_ready(pane, position_ms=0)
    hover = controls(pane)
    move_into_picture(pane, qapp)
    QTest.mouseClick(hover.play_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: pane.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
               and pane.player.position() > 120, "real hover play button", panes=[pane])
    assert "暂停" in hover.play_button.toolTip()
    QTest.mouseClick(hover.play_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: pane.player.playbackState() == QMediaPlayer.PlaybackState.PausedState,
               "real hover pause button", panes=[pane])
    assert "播放" in hover.play_button.toolTip()
    hover.volume_slider.setValue(63)
    drain_events(qapp)
    assert pane.state.volume == pytest.approx(.63)
    assert pane.audio.volume() == pytest.approx(.63)
    assert not pane.state.muted and not pane.audio.isMuted()

