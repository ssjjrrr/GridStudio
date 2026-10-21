"""Bounded-process regression for event-loop waiting during native deletion."""

import faulthandler
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, QThread, QTimer, Qt, Signal, SIGNAL, SLOT
import shiboken6

from scripts.qt_test_support import qt_wait


def main():
    app = QCoreApplication([])
    entered = threading.Event()
    release = threading.Event()
    returned = threading.Event()
    gate_expired = threading.Event()

    class Sender(QObject):
        ping = Signal()
        armed = False

        def disconnectNotify(self, signal):
            if self.armed and QThread.currentThread() != self.thread():
                self.armed = False
                entered.set()
                # Receiver destruction owns Qt's connection mutex. The wait
                # releases the GIL; the GUI event pump opens this finite gate.
                # Resuming the worker's Python callback needs the GIL again.
                if not release.wait(3):
                    gate_expired.set()
                returned.set()
            super().disconnectNotify(signal)

    sender = Sender()
    worker = QThread()
    receiver = QTimer()
    receiver.moveToThread(worker)
    worker.start()
    connection = QObject.connect(sender, SIGNAL("ping()"), receiver, SLOT("stop()"),
                                 Qt.ConnectionType.QueuedConnection)
    assert connection
    sender.armed = True
    QMetaObject.invokeMethod(receiver, "deleteLater", Qt.ConnectionType.QueuedConnection)
    assert entered.wait(3), "Worker did not enter native disconnection"
    sender.deleteLater()
    QTimer.singleShot(0, release.set)
    faulthandler.dump_traceback_later(3)
    qt_wait(20)
    faulthandler.cancel_dump_traceback_later()
    assert returned.is_set(), "Worker could not reacquire the GIL during deletion"
    assert not gate_expired.is_set(), "The event pump did not release the worker gate"
    assert not shiboken6.isValid(sender) and not shiboken6.isValid(receiver)
    # Verify normal timer delivery and a zero-duration deferred-delete flush.
    timer_fired = []
    QTimer.singleShot(0, lambda: timer_fired.append(True))
    pending = QObject()
    pending.deleteLater()
    qt_wait(0)
    assert timer_fired == [True] and not shiboken6.isValid(pending)
    worker.quit()
    assert worker.wait(2000)
    print("PASS: worker GIL progress, native deletion, timers and zero-duration flush", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
