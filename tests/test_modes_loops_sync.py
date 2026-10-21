"""User-visible fill choices, saved state, and actual loop/sync playback."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame

from gridstudio.app import FIT_MODES
from test_app import drain_events, qapp, window
from test_clean_mode import assert_video_only, menu_action
from test_media import (current_frame, has_decoded_frame, load_pane, media_app,
                        media_window, sample_video, wait_ready, wait_until)


def feed_corners(canvas):
    """Distinct source corners reveal unwanted cropping or discarded edges."""
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    for x, y, color in ((0, 0, "red"), (200, 0, "lime"),
                        (0, 100, "blue"), (200, 100, "yellow")):
        painter.fillRect(x, y, 200, 100, QColor(color))
    painter.end()
    canvas.set_has_media(True)
    canvas.set_message("")
    canvas.video_item.videoSink().setVideoFrame(QVideoFrame(image))


def assert_corners_visible(canvas):
    capture = canvas.capture_image()
    sx = capture.width() / canvas.viewport().width()
    sy = capture.height() / canvas.viewport().height()
    for x, y, color in ((8, 8, "red"), (392, 8, "lime"),
                        (8, 192, "blue"), (392, 192, "yellow")):
        scene = canvas.video_item.mapToScene(QPointF(x, y))
        viewport = canvas.mapFromScene(scene)
        assert canvas.viewport().rect().contains(viewport)
        actual = capture.pixelColor(round(viewport.x() * sx), round(viewport.y() * sy))
        expected = QColor(color)
        assert max(abs(a - b) for a, b in zip(actual.getRgb()[:3], expected.getRgb()[:3])) <= 3


def test_default_complete_video_keeps_all_source_corners_and_aspect(window, qapp):
    window.resize(601, 601)
    canvas = window.active().canvas
    feed_corners(canvas)
    drain_events(qapp)
    assert canvas.fill_mode == "contain"
    assert canvas.transform().m11() == pytest.approx(canvas.transform().m22())
    assert_corners_visible(canvas)
    assert canvas.capture_image().pixelColor(0, 0) == QColor("black")
    assert_video_only(window)


@pytest.mark.parametrize("rotation", (0, 90, 270))
def test_stretch_fills_mismatched_pane_and_preserves_every_source_corner(window, qapp, rotation):
    window.resize(601, 451)
    pane = window.active()
    pane.state.rotation = rotation
    window.set_fit_mode("stretch")
    feed_corners(pane.canvas)
    drain_events(qapp)
    assert pane.canvas.transform().m11() != pytest.approx(pane.canvas.transform().m22())
    assert_corners_visible(pane.canvas)
    capture = pane.canvas.capture_image()
    # Every viewport edge remains picture; stretch never adds letterbox bars.
    for x, y in ((2, 2), (capture.width() - 3, 2), (2, capture.height() - 3),
                 (capture.width() - 3, capture.height() - 3)):
        assert capture.pixelColor(x, y) != QColor("black")


@pytest.mark.parametrize("label,mode", FIT_MODES)
def test_fit_menu_choice_is_per_pane_and_survives_edit_mode(window, qapp, label, mode):
    original = window.active()
    window.add_blank()
    other = window.active()
    menu = window.create_context_menu(original.state.id)
    menu_action(menu, label).trigger()
    assert original.state.fit_mode == original.canvas.fill_mode == mode
    assert other.state.fit_mode == other.canvas.fill_mode == "contain"
    for clean in (False, True):
        window.set_clean_mode(clean)
        drain_events(qapp)
        assert original.canvas.fill_mode == mode
        assert other.canvas.fill_mode == "contain"
    menu.deleteLater()
    menu = window.create_context_menu(original.state.id)
    for candidate, value in FIT_MODES:
        assert menu_action(menu, candidate).isChecked() is (value == mode)
    menu_action(menu, "将当前方式应用到全部窗格").trigger()
    assert all(pane.state.fit_mode == pane.canvas.fill_mode == mode
               for pane in window.panes.values())
    assert_video_only(window)
    menu.deleteLater()


def test_duplicate_and_workspace_preserve_fit_loop_and_sync_configuration(window, qapp, tmp_path):
    original = window.active()
    original.state.fit_mode = "stretch"
    original.state.loop = True
    original.state.loop_start_ms = 1000
    original.state.loop_end_ms = 2500
    original.state.sync_group = "2"
    original.state.sync_offset_ms = -500
    original.state.sync_mode = "percent"
    original.apply_state()
    window.duplicate()
    drain_events(qapp)
    duplicate = window.active()
    names = ("fit_mode", "loop", "loop_start_ms", "loop_end_ms", "sync_group",
             "sync_offset_ms", "sync_mode")
    expected = {name: getattr(original.state, name) for name in names}
    assert {name: getattr(duplicate.state, name) for name in names} == expected
    saved_ids = set(window.panes)
    session = tmp_path / "playback-options.gstudio"
    assert window.save_session(session)
    assert window.load_session(session)
    drain_events(qapp)
    assert set(window.panes) == saved_ids
    for pane in window.panes.values():
        assert {name: getattr(pane.state, name) for name in names} == expected
        assert pane.canvas.fill_mode == "stretch"
    assert_video_only(window)


def test_custom_sync_rate_survives_unrelated_inspector_edit_and_rejected_rate(window, monkeypatch):
    pane = window.active()
    pane.state.rate = 1.234
    pane.apply_state()
    window.refresh_inspector()
    assert window.rate.currentData() == 1.234
    window.fit_mode.setCurrentIndex(window.fit_mode.findData("stretch"))
    assert pane.state.fit_mode == "stretch"
    assert pane.state.rate == 1.234
    assert pane.player.playbackRate() == pytest.approx(1.234)
    # A percent group can reject a rate if another member would exceed 8x.
    # The inspector must retain the accepted value when the engine refuses it.
    monkeypatch.setattr(window.playback, "set_rate", lambda *_args: False)
    window.rate.setCurrentIndex(window.rate.findData(1.5))
    assert pane.state.rate == 1.234
    assert pane.player.playbackRate() == pytest.approx(1.234)
    assert window.rate.currentData() == 1.234


def duplicate_ready(win, original, position_ms):
    win.duplicate(original.state.id)
    duplicate = win.active()
    wait_ready(duplicate, position_ms=position_ms)
    return duplicate


def test_ab_loop_wraps_real_decoded_video_and_can_be_disabled(media_window, sample_video):
    pane = load_pane(media_window, sample_video, position_ms=1000)
    wait_ready(pane, position_ms=1000)
    playback = media_window.playback
    assert playback.set_loop(pane.state.id, True, start_ms=1000, end_ms=1600)
    playback.set_playing(pane.state.id, True)
    wait_until(lambda: pane.player.position() >= 1400, "first pass towards B", panes=[pane])
    wait_until(lambda: pane.player.position() < 1300 and has_decoded_frame(pane)
               and 900 <= current_frame(pane).startTime() / 1000 <= 1400,
               "A/B wrap returning to A", panes=[pane])
    assert pane.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    assert playback.set_loop(pane.state.id, False, start_ms=1000, end_ms=1600)
    wait_until(lambda: pane.player.position() > 1900, "playback beyond disabled B", panes=[pane])
    assert pane.state.loop_start_ms == 1000 and pane.state.loop_end_ms == 1600
    playback.clear_loop(pane.state.id)
    assert pane.state.loop_start_ms == 0 and pane.state.loop_end_ms is None


def test_whole_video_loop_returns_to_start(media_window, sample_video):
    pane = load_pane(media_window, sample_video, position_ms=11700)
    wait_ready(pane, position_ms=11700)
    assert media_window.playback.set_loop(pane.state.id, True)
    media_window.playback.set_playing(pane.state.id, True)
    wait_until(lambda: 0 < pane.player.position() < 1500
               and has_decoded_frame(pane) and current_frame(pane).startTime() < 1500000,
               "whole video restarting with decoded frames", panes=[pane])
    assert pane.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState


def test_sync_group_links_seek_play_pause_rate_and_survives_leader_close(media_window, sample_video):
    win = media_window
    first = load_pane(win, sample_video, position_ms=2000)
    wait_ready(first, position_ms=2000)
    second = duplicate_ready(win, first, 2000)
    playback = win.playback
    playback.join_group([first.state.id, second.state.id], group="1", leader_id=first.state.id)
    playback.seek(second.state.id, 3000)
    for pane in (first, second):
        wait_ready(pane, position_ms=3000)
    playback.set_rate(second.state.id, 1.5)
    assert first.player.playbackRate() == second.player.playbackRate() == 1.5
    playback.set_playing(second.state.id, True)
    wait_until(lambda: all(p.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                          and p.player.position() > 3400 for p in (first, second)),
               "synchronized players advancing", panes=[first, second])
    playback.set_playing(first.state.id, False)
    wait_until(lambda: all(p.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
                          for p in (first, second)), "group paused", panes=[first, second])
    assert abs(first.player.position() - second.player.position()) <= 150
    # A copy made inside the group must stay linked after the original closes.
    position = second.player.position()
    third = duplicate_ready(win, second, position)
    assert third.state.sync_group == "1"
    win.remove_pane(first.state.id)
    playback.seek(third.state.id, 4500)
    for pane in (second, third):
        wait_ready(pane, position_ms=4500)
    playback.set_playing(third.state.id, True)
    wait_until(lambda: all(p.player.position() > 4800 for p in (second, third)),
               "surviving sync group advancing", panes=[second, third])


def test_sync_groups_and_unlinked_panes_remain_independent(media_window, sample_video):
    win = media_window
    first = load_pane(win, sample_video, position_ms=1000)
    wait_ready(first, position_ms=1000)
    second = duplicate_ready(win, first, 1000)
    third = duplicate_ready(win, first, 1000)
    fourth = duplicate_ready(win, first, 1000)
    playback = win.playback
    playback.join_group([first.state.id, second.state.id], group="1", leader_id=first.state.id)
    playback.join_group([third.state.id], group="2", leader_id=third.state.id)
    playback.seek(first.state.id, 3500)
    playback.set_rate(second.state.id, 1.75)
    for pane in (first, second):
        wait_ready(pane, position_ms=3500)
        assert pane.player.playbackRate() == 1.75
    assert third.player.position() == fourth.player.position() == pytest.approx(1000, abs=50)
    assert third.player.playbackRate() == fourth.player.playbackRate() == 1
    playback.leave_group([second.state.id])
    playback.seek(first.state.id, 5000)
    wait_ready(first, position_ms=5000)
    assert second.player.position() == pytest.approx(3500, abs=50)
    assert second.state.sync_group == ""


def test_loading_workspace_resets_previous_group_playback_intent(media_window, sample_video, tmp_path):
    win = media_window
    first = load_pane(win, sample_video, position_ms=2000)
    wait_ready(first, position_ms=2000)
    second = duplicate_ready(win, first, 2000)
    win.playback.join_group([first.state.id, second.state.id], leader_id=first.state.id)
    session = tmp_path / "paused-sync.gstudio"
    assert win.save_session(session)
    win.playback.set_playing(first.state.id, True)
    wait_until(lambda: first.player.position() > 2200, "old group playing", panes=[first, second])
    assert win.load_session(session)
    for pane in win.panes.values():
        wait_ready(pane, position_ms=2000, paused=True)
        assert pane.state.sync_group == "1"


def test_replacing_media_clears_previous_videos_ab_markers(media_window, sample_video):
    pane = load_pane(media_window, sample_video, position_ms=1000)
    wait_ready(pane, position_ms=1000)
    assert media_window.playback.set_loop(pane.state.id, True, start_ms=1000, end_ms=2000)
    media_window.add_files([str(sample_video)], target=pane.state.id)
    assert pane.state.loop_start_ms == 0
    assert pane.state.loop_end_ms is None
    wait_ready(pane, paused=False)


def test_percent_sync_maps_unequal_durations_and_delivers_frames(media_window, sample_video):
    win = media_window
    long = load_pane(win, sample_video, position_ms=2000)
    wait_ready(long, position_ms=2000)
    win.add_blank()
    short = load_pane(win, sample_video.with_name("sample-short.mp4"), position_ms=1000)
    wait_ready(short, position_ms=1000)
    ratio = short.player.duration() / long.player.duration()
    playback = win.playback
    assert playback.join_group([long.state.id, short.state.id], leader_id=long.state.id, mode="percent")
    playback.seek(long.state.id, 4000)
    wait_ready(long, position_ms=4000)
    wait_ready(short, position_ms=round(4000 * ratio))
    assert long.player.playbackRate() == pytest.approx(1)
    assert short.player.playbackRate() == pytest.approx(ratio)
    frame_times = [current_frame(p).startTime() for p in (long, short)]
    playback.set_playing(long.state.id, True)
    wait_until(lambda: long.player.position() > 4350
               and all(current_frame(p).startTime() > before
                       for p, before in zip((long, short), frame_times)),
               "percent synchronized decoders advancing", panes=[long, short])
    playback.set_playing(short.state.id, False)
    fractions = [p.player.position() / p.player.duration() for p in (long, short)]
    assert abs(fractions[0] - fractions[1]) < .02
