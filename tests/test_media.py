"""Real H.264 playback checks for restore, paused seeks and independent copies."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent
from PySide6.QtMultimedia import QMediaFormat, QMediaMetaData, QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from gridstudio.app import MainWindow


@pytest.fixture(scope="session")
def media_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def sample_video():
    path = Path(__file__).parent / "fixtures" / "sample.mp4"
    assert path.is_file(), "The generated 12-second H.264 fixture is required"
    return path.resolve()


@pytest.fixture
def media_window(media_app, monkeypatch):
    def unexpected_modal(_parent, title, message, *_args, **_kwargs):
        pytest.fail(f"Unexpected modal dialog: {title}: {message}")

    monkeypatch.setattr(QMessageBox, "warning", unexpected_modal)
    window = MainWindow()
    window.set_layout_mode("grid")
    window.show()
    media_app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    media_app.processEvents()


def description(pane):
    player = pane.player
    frame = pane.canvas.video_item.videoSink().videoFrame()
    return (f"status={player.mediaStatus().name}, playback={player.playbackState().name}, "
            f"duration={player.duration()}, position={player.position()}, "
            f"pending={pane._pending_restore}, frame={frame.isValid()}, "
            f"frame_ms={frame.startTime() / 1000}, error={player.errorString()!r}")


def wait_until(predicate, message, *, panes=(), timeout_ms=8000):
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < timeout_ms:
        if predicate():
            return
        QTest.qWait(20)
    detail = "; ".join(description(pane) for pane in panes)
    pytest.fail(f"Timed out waiting for {message}: {detail}")


def current_frame(pane):
    return pane.canvas.video_item.videoSink().videoFrame()


def has_decoded_frame(pane, target_ms=None):
    frame = current_frame(pane)
    if not frame.isValid() or frame.toImage().isNull():
        return False
    if target_ms is not None:
        return abs(frame.startTime() / 1000 - target_ms) <= 100
    return True


def wait_ready(pane, *, position_ms=None, paused=True):
    expected = (QMediaPlayer.PlaybackState.PausedState if paused
                else QMediaPlayer.PlaybackState.PlayingState)
    wait_until(lambda: not pane._pending_restore and pane.player.duration() > 0
               and pane.player.playbackState() == expected,
               "restored media and playback state", panes=[pane])
    if paused and position_ms is not None:
        wait_until(lambda: abs(pane.player.position() - position_ms) <= 50
                   and has_decoded_frame(pane, position_ms),
                   f"decoded paused frame at {position_ms} ms", panes=[pane])
    else:
        wait_until(lambda: has_decoded_frame(pane), "decoded video image", panes=[pane])
    assert pane.player.error() == QMediaPlayer.Error.NoError, description(pane)


def load_pane(window, sample, *, position_ms=0, paused=True):
    pane = window.active()
    pane.state.source = str(sample)
    pane.state.position_ms = position_ms
    pane.state.paused = paused
    pane.apply_state()
    pane.load_source()
    return pane


def test_real_h264_opens_paused_with_a_decoded_frame_and_seeks_while_paused(media_window, sample_video):
    pane = load_pane(media_window, sample_video)
    wait_ready(pane, position_ms=0)
    assert pane.player.duration() == pytest.approx(12000, abs=100)
    assert pane.player.metaData().value(QMediaMetaData.Key.VideoCodec) == QMediaFormat.VideoCodec.H264
    frame = current_frame(pane)
    assert frame.width() > 0 and frame.height() > 0
    assert not frame.toImage().isNull()

    media_window.playback.seek(pane.state.id, 3000)
    wait_until(lambda: abs(pane.player.position() - 3000) <= 50
               and has_decoded_frame(pane, 3000),
               "a new decoded frame after a paused seek", panes=[pane])
    assert pane.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    QTest.qWait(150)
    assert pane.player.position() == pytest.approx(3000, abs=50)


def test_paused_duplicate_preserves_actual_position_frame_and_transforms_then_plays_independently(media_window, sample_video):
    original = load_pane(media_window, sample_video)
    wait_ready(original, position_ms=0)
    media_window.playback.seek(original.state.id, 3000)
    wait_until(lambda: has_decoded_frame(original, 3000), "source paused seek", panes=[original])
    original.state.crop = (0.1, 0.15, 0.65, 0.7)
    original.state.rotation = 90
    original.state.flip_h = True
    original.state.flip_v = True
    original.state.rate = 1.25
    original.apply_state()
    original_frame_ms = current_frame(original).startTime() / 1000

    media_window.duplicate(original.state.id)
    duplicate = media_window.active()
    wait_ready(duplicate, position_ms=3000)
    assert duplicate.player is not original.player
    assert duplicate.canvas.video_item is not original.canvas.video_item
    assert duplicate.state.source == original.state.source
    assert duplicate.state.crop == original.state.crop
    assert duplicate.state.rotation == original.state.rotation
    assert duplicate.state.flip_h == original.state.flip_h
    assert duplicate.state.flip_v == original.state.flip_v
    assert duplicate.player.playbackRate() == original.player.playbackRate() == 1.25
    assert duplicate.player.position() == pytest.approx(original.player.position(), abs=50)
    assert current_frame(duplicate).startTime() / 1000 == pytest.approx(original_frame_ms, abs=50)
    assert not current_frame(duplicate).toImage().isNull()
    assert not duplicate.canvas.capture_image().isNull()

    media_window.playback.set_playing(duplicate.state.id, True)
    wait_until(lambda: duplicate.player.position() > 3450
               and current_frame(duplicate).startTime() / 1000 > original_frame_ms + 300,
               "only the duplicate advancing", panes=[original, duplicate])
    assert original.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    assert original.player.position() == pytest.approx(3000, abs=50)
    assert current_frame(original).startTime() / 1000 == original_frame_ms

    media_window.remove_pane(original.state.id)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert shiboken6.isValid(duplicate)
    position_after_close = duplicate.player.position()
    frame_after_close = current_frame(duplicate).startTime()
    wait_until(lambda: duplicate.player.position() > position_after_close + 250
               and current_frame(duplicate).startTime() > frame_after_close + 150000,
               "duplicate frames after original was destroyed", panes=[duplicate])
    assert not current_frame(duplicate).toImage().isNull()


@pytest.mark.parametrize("paused", [True, False])
def test_duplicate_during_loading_keeps_the_pending_seek_and_playback_intent(media_window, sample_video, paused):
    original = load_pane(media_window, sample_video, position_ms=5200, paused=paused)
    # No event-loop turn has happened since setSource: snapshot must keep the
    # requested future seek instead of overwriting it with the stopped player's 0.
    assert original._pending_restore
    assert original.player.mediaStatus() == QMediaPlayer.MediaStatus.LoadingMedia
    assert original.player.position() == 0
    media_window.duplicate(original.state.id)
    duplicate = media_window.active()
    assert duplicate.state.position_ms == original.state.position_ms == 5200
    assert duplicate.state.paused is original.state.paused is paused
    wait_ready(original, position_ms=5200, paused=paused)
    wait_ready(duplicate, position_ms=5200, paused=paused)
    if not paused:
        wait_until(lambda: original.player.position() >= 5200 and duplicate.player.position() >= 5200
                   and current_frame(original).startTime() >= 5100000
                   and current_frame(duplicate).startTime() >= 5100000,
                   "both loading-time copies playing from the pending seek", panes=[original, duplicate])
    assert duplicate.state.position_ms == 5200


def test_play_all_and_pause_all_control_both_real_players(media_window, sample_video):
    original = load_pane(media_window, sample_video, position_ms=2000)
    wait_ready(original, position_ms=2000)
    media_window.duplicate(original.state.id)
    duplicate = media_window.active()
    wait_ready(duplicate, position_ms=2000)
    media_window.play_all(True)
    wait_until(lambda: all(pane.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                          and pane.player.position() > 2350
                          and current_frame(pane).startTime() > 2250000
                          for pane in (original, duplicate)),
               "all players advancing and decoding", panes=[original, duplicate])
    media_window.play_all(False)
    wait_until(lambda: all(pane.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
                          for pane in (original, duplicate)),
               "all players paused", panes=[original, duplicate])
    positions = [pane.player.position() for pane in (original, duplicate)]
    QTest.qWait(150)
    assert [pane.player.position() for pane in (original, duplicate)] == positions
