"""Native media slot dispatch, without opening a media source or a decoder."""

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication

from gridstudio.media_commands import media_command


@pytest.fixture(scope="module")
def command_application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def empty_media_objects(command_application):
    # Creating these objects is enough to exercise their native meta-object
    # methods. Never set a nonempty URL, connect an output, or open a codec.
    player = QMediaPlayer()
    audio = QAudioOutput()
    yield player, audio
    player.deleteLater()
    audio.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    command_application.processEvents()


def forbidden_direct_calls(monkeypatch, target, methods):
    calls = []

    def direct_call(*arguments):
        calls.append(arguments)
        raise AssertionError("Unsafe Python media wrapper was called")

    for method in methods:
        monkeypatch.setattr(target, method, direct_call, raising=False)
    return calls


def test_audio_slots_bypass_python_setters_and_emit_synchronous_state(empty_media_objects, monkeypatch):
    _, audio = empty_media_objects
    direct = forbidden_direct_calls(monkeypatch, audio, ("setVolume", "setMuted"))
    events = []
    audio.volumeChanged.connect(lambda value: events.append(("volume", value, audio.volume())))
    audio.mutedChanged.connect(lambda value: events.append(("muted", value, audio.isMuted())))

    assert media_command(audio, "setVolume", .37) is None
    assert audio.volume() == pytest.approx(.37, abs=1e-6)
    assert len(events) == 1
    assert events[0][0] == "volume"
    assert events[0][1:] == pytest.approx((.37, .37), abs=1e-6)

    media_command(audio, "setMuted", True)
    assert events[-1] == ("muted", True, True)
    assert audio.isMuted()
    media_command(audio, "setMuted", False)
    assert events[-1] == ("muted", False, False)
    assert not audio.isMuted()
    assert direct == []


def test_player_rate_slot_bypasses_python_override_and_completes_before_return(empty_media_objects, monkeypatch):
    player, _ = empty_media_objects
    direct = forbidden_direct_calls(monkeypatch, player, ("setPlaybackRate",))
    events = []
    player.playbackRateChanged.connect(lambda value: events.append((value, player.playbackRate())))

    media_command(player, "setPlaybackRate", 1.75)

    assert player.playbackRate() == pytest.approx(1.75)
    assert events == [(1.75, 1.75)]
    assert direct == []


def test_empty_player_transport_seek_and_source_use_native_slots_without_loading(empty_media_objects, monkeypatch):
    player, _ = empty_media_objects
    direct = forbidden_direct_calls(monkeypatch, player,
                                    ("play", "pause", "stop", "setPosition", "setSource"))

    # With no source these are intentionally state-preserving no-ops, but
    # invokeMethod must recognize every slot and bypass its Python attribute.
    media_command(player, "setSource", QUrl())
    media_command(player, "setPosition", 3200)
    for method in ("play", "pause", "stop"):
        media_command(player, method)

    assert player.source().isEmpty()
    assert player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia
    assert player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
    assert player.position() == 0
    assert direct == []


@pytest.mark.parametrize("target_name,method,arguments", [
    ("player", "setVolume", (.4,)),
    ("audio", "play", ()),
])
def test_failed_native_slot_never_falls_back_to_python(empty_media_objects, monkeypatch,
                                                      target_name, method, arguments):
    player, audio = empty_media_objects
    target = player if target_name == "player" else audio
    direct = forbidden_direct_calls(monkeypatch, target, (method,))

    with pytest.raises(RuntimeError, match=f"Native media command failed: {method}"):
        media_command(target, method, *arguments)

    assert direct == []
    assert player.source().isEmpty()


def test_cross_thread_command_is_rejected_before_any_media_operation(empty_media_objects, monkeypatch):
    _, audio = empty_media_objects
    initial = audio.volume()
    direct = forbidden_direct_calls(monkeypatch, audio, ("setVolume",))
    events = []
    audio.volumeChanged.connect(events.append)
    failures = []

    def foreign_thread():
        try:
            media_command(audio, "setVolume", .28)
        except BaseException as error:
            failures.append(error)

    worker = threading.Thread(target=foreign_thread)
    worker.start()
    worker.join(timeout=2)

    assert not worker.is_alive(), "Thread ownership rejection must not block"
    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeError)
    assert "Qt thread" in str(failures[0])
    assert audio.volume() == initial
    assert events == []
    assert direct == []


class FakeMediaEngine:
    def __init__(self):
        self.calls = []
        self.position = 0
        self.playing = False

    def setPosition(self, value):
        self.position = value
        self.calls.append(("setPosition", value))

    def setPlaybackRate(self, value):
        self.calls.append(("setPlaybackRate", value))

    def setSource(self, value):
        self.calls.append(("setSource", value))

    def setVolume(self, value):
        self.calls.append(("setVolume", value))

    def setMuted(self, value):
        self.calls.append(("setMuted", value))

    def play(self):
        self.playing = True
        self.calls.append(("play",))

    def pause(self):
        self.playing = False
        self.calls.append(("pause",))

    def stop(self):
        self.playing = False
        self.position = 0
        self.calls.append(("stop",))


def test_python_engine_double_keeps_normal_synchronous_methods_and_conversions():
    engine = FakeMediaEngine()
    source = QUrl()

    media_command(engine, "setPosition", 1234.9)
    assert engine.position == 1234
    media_command(engine, "play")
    assert engine.playing
    media_command(engine, "setPlaybackRate", 2)
    media_command(engine, "setSource", source)
    media_command(engine, "setVolume", 0)
    media_command(engine, "setMuted", 1)
    media_command(engine, "pause")
    assert not engine.playing
    media_command(engine, "stop")
    assert engine.position == 0
    assert engine.calls == [
        ("setPosition", 1234), ("play",), ("setPlaybackRate", 2.0),
        ("setSource", source), ("setVolume", 0.0), ("setMuted", True),
        ("pause",), ("stop",),
    ]


@pytest.mark.parametrize("method,arguments,error_type", [
    ("setPosition", (), TypeError),
    ("setPlaybackRate", (), TypeError),
    ("setVolume", (), TypeError),
    ("setMuted", (), TypeError),
    ("setSource", (), TypeError),
    ("play", (False,), TypeError),
    ("pause", (0,), TypeError),
    ("stop", (None,), TypeError),
    ("setLoops", (-1,), ValueError),
    ("unknown", (), ValueError),
])
def test_invalid_commands_reject_without_calling_the_engine(method, arguments, error_type):
    engine = FakeMediaEngine()
    with pytest.raises(error_type):
        media_command(engine, method, *arguments)
    assert engine.calls == []
