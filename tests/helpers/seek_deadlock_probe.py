"""Exercise a controlled Qt connection-lock/GIL race with a real decoded seek.

QObject's worker-side destruction holds the receiver's connection mutex while
calling the sender's Python disconnectNotify override. A bounded sleep there
widens that genuine scheduling window. A simultaneous media seek emits
positionChanged and needs the same Qt mutex. The fixed media command must let
the worker reacquire the GIL, complete deletion, and release the mutex.

This is a regression for that controlled lock ordering. It does not prove the
native call stacks behind any separate, historical intermittent application
freeze. Direct mode is available only for explicit supervised diagnosis; the
regular test invokes fixed mode in an externally time-limited subprocess.
"""

import argparse
import faulthandler
import json
import os
from pathlib import Path
import sys
import threading
import time


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixed", "direct", "native-direct"), default="fixed")
    parser.add_argument("--platform", default="offscreen")
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--gate-ms", type=int, default=400)
    return parser.parse_args()


def run(options):
    os.environ["QT_QPA_PLATFORM"] = options.platform
    # Resolve from the checked-out project; never depend on a workspace path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from PySide6.QtCore import QMetaObject, QObject, QThread, QTimer, QUrl, Qt, Q_ARG, SIGNAL, SLOT, qVersion
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
    from PySide6.QtTest import QTest
    import shiboken6
    from gridstudio.media_commands import media_command

    entered = threading.Event()

    class ControlledPlayer(QMediaPlayer):
        armed = False

        def disconnectNotify(self, signal):
            if (self.armed and bytes(signal.name()) == b"positionChanged"
                    and QThread.currentThread() != self.thread()):
                self.armed = False
                print(json.dumps({"event": "worker_disconnect_notify_entered",
                                  "thread": threading.get_native_id()}), flush=True)
                entered.set()
                # Finite delay only: the callback does not await any seek or
                # artificial lock. Qt itself owns the connection mutex here.
                time.sleep(max(1, options.gate_ms) / 1000)
                print(json.dumps({"event": "worker_disconnect_notify_returned"}), flush=True)
            super().disconnectNotify(signal)

    def wait_for(predicate, description, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            QTest.qWait(10)
        raise RuntimeError("Timed out: " + description)

    app = QGuiApplication([])
    player = ControlledPlayer()
    sink = QVideoSink()
    player.setVideoSink(sink)
    media_command(player, "setSource", QUrl.fromLocalFile(str(options.media.resolve())))
    media_command(player, "pause")
    wait_for(lambda: player.duration() > 0 and player.isSeekable()
             and player.playbackState() == QMediaPlayer.PlaybackState.PausedState
             and sink.videoFrame().isValid(), "initial paused decoded frame")

    worker = QThread()
    receiver = QTimer()
    receiver.moveToThread(worker)
    worker.start()
    # Explicit C++ slot names ensure no Python receiver callable replaces the
    # native queued signal activation whose mutex acquisition is under test.
    connection = QObject.connect(player, SIGNAL("positionChanged(qint64)"), receiver,
                                 SLOT("stop()"), Qt.ConnectionType.QueuedConnection)
    if not connection:
        raise RuntimeError("Failed to create native Qt signal connection")
    player.armed = True
    QMetaObject.invokeMethod(receiver, "deleteLater", Qt.ConnectionType.QueuedConnection)
    if not entered.wait(3):
        raise RuntimeError("Native receiver destruction callback was not observed")

    target = min(4000, player.duration() // 2)
    correct_thread = QThread.currentThread() == player.thread()
    if not correct_thread:
        raise RuntimeError("The seek must stay on the player's Qt thread")
    print(json.dumps({"event": "seek_begin", "mode": options.mode,
                      "target": target, "qt": qVersion(),
                      "correct_player_thread": correct_thread}), flush=True)
    faulthandler.dump_traceback_later(3)
    if options.mode == "direct":
        player.setPosition(target)
    elif options.mode == "native-direct":
        if not QMetaObject.invokeMethod(player, "setPosition", Qt.ConnectionType.DirectConnection,
                                       Q_ARG("qint64", target)):
            raise RuntimeError("Native direct seek slot invocation failed")
    else:
        media_command(player, "setPosition", target)
    faulthandler.cancel_dump_traceback_later()
    print(json.dumps({"event": "seek_return"}), flush=True)

    wait_for(lambda: abs(player.position() - target) < 80 and sink.videoFrame().isValid()
             and abs(sink.videoFrame().startTime() / 1000 - target) < 100,
             "decoded frame at seek target")
    position = player.position()
    frame_ms = sink.videoFrame().startTime() / 1000
    wait_for(lambda: not shiboken6.isValid(receiver), "worker receiver deletion")
    worker.quit()
    if not worker.wait(2000):
        raise RuntimeError("Worker thread failed to exit")
    media_command(player, "stop")
    media_command(player, "setSource", QUrl())
    player.setVideoSink(None)
    app.processEvents()
    print(json.dumps({"event": "probe_pass", "target": target, "mode": options.mode,
                      "position_ms": position, "frame_ms": frame_ms,
                      "receiver_destroyed": True, "worker_exited": True}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run(arguments()))
