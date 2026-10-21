"""Event-loop waiting for tests and benchmarks, outside the application runtime."""

import math
import time

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop


def qt_wait(milliseconds: int) -> None:
    """Process events and deferred deletion for at least the requested time.

    PySide 6.10.2's QTest.qWait binding keeps the GIL while Qt processes
    DeferredDelete. A native destructor can then wait for a Qt connection
    mutex held by a media worker trying to enter Python's disconnectNotify.
    The int overload of processEvents and sendPostedEvents explicitly release
    the GIL in this PySide version. Keep the same event/deletion/sleep sequence
    as Qt's qWait, using those bindings and Python's GIL-releasing sleep.
    """
    if milliseconds < 0:
        raise ValueError("Wait duration must not be negative")
    if QCoreApplication.instance() is None:
        raise RuntimeError("qt_wait requires a QCoreApplication")
    deadline = time.monotonic() + milliseconds / 1000
    while True:
        remaining_ms = max(0, math.ceil((deadline - time.monotonic()) * 1000))
        # Do not replace the int with QDeadlineTimer: the bindings differ in
        # their allow-thread declarations. Zero still processes pending work.
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, remaining_ms)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(.01, remaining))
