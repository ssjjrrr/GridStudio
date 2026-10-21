"""Measure selection, layer membership changes, and idle timer/query counts.

Synthetic frames exclude decoder setup from the layer-management comparison.
Run old and new projects serially with the same script and platform. Timings
include normal paint/event flushes, never a screenshot per operation.
"""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--platform", default="offscreen")
    parser.add_argument("--panes", type=int, default=16)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = args.platform
    sys.path.insert(0, str(args.project.resolve()))
    from PySide6.QtCore import QCoreApplication, QEvent, QObject
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtMultimedia import QVideoFrame
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from gridstudio.app import MainWindow, STYLE
    from gridstudio import __version__

    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.resize(1280, 720)
    win.show()

    def flush():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    for _ in range(args.panes - 1):
        win.add_blank()
    flush()
    originals = tuple(win.panes.values())
    for index, pane in enumerate(originals):
        picture = QImage(640, 360, QImage.Format.Format_RGB32)
        picture.fill(QColor.fromHsv(index * 23 % 360, 220, 220))
        pane.canvas.set_has_media(True)
        pane.canvas.video_item.videoSink().setVideoFrame(QVideoFrame(picture))
    flush()

    class Lifecycle(QObject):
        def __init__(self):
            super().__init__()
            self.counts = Counter()

        def eventFilter(self, watched, event):
            if event.type() in (QEvent.Type.Hide, QEvent.Type.Show, QEvent.Type.ParentChange):
                self.counts[event.type().name] += 1
            return False

    audit = Lifecycle()
    for pane in originals:
        pane.installEventFilter(audit)
    selected = originals[0].state.id
    started = time.perf_counter()
    for _ in range(args.cycles):
        win.duplicate(selected)
        flush()
        win.remove_pane(win.active_id)
        flush()
    membership_ms = (time.perf_counter() - started) * 1000
    assert all(win.panes[p.state.id] is p and p.isVisible() for p in originals)

    win.select(selected)
    flush()
    started = time.perf_counter()
    for _ in range(1000):
        win.select(selected)
    flush()
    selection_ms = (time.perf_counter() - started) * 1000

    queries = Counter()
    ticks = []
    win.playback.timer.timeout.connect(lambda: ticks.append(1))
    for pane in originals:
        # An ordinary full-file loop needs no controller query even if the
        # native player reports a ready duration. No decoder is opened here.
        pane.state.source = "synthetic.mp4"
        pane.state.paused = False
        pane.player.duration = lambda: queries.update(duration=1) or 12000
    if hasattr(win.playback, "refresh_activity"):
        win.playback.refresh_activity()
    QTest.qWait(300)
    output = {
        "version": __version__, "platform": app.platformName(), "panes": len(originals),
        "membership_cycles": args.cycles, "membership_ms": membership_ms,
        "retained_layer_events": dict(audit.counts), "selection_calls": 1000,
        "selection_ms": selection_ms, "ordinary_loop_idle_ms": 300,
        "ordinary_loop_timer_ticks": len(ticks), "ordinary_loop_native_queries": dict(queries),
        "limits": "Synthetic frames and duration stubs isolate UI/controller work; not decoder capacity or FPS.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output))
    win.close()
    flush()


if __name__ == "__main__":
    main()
