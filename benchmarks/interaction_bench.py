"""Profile real canvas drag/resize dispatch and deferred Qt painting separately.

Default input is four synthetic 640x360 video frames (no decoder load). Optional
--media opens four real sources and must be scheduled serially by the caller.
Each measured gesture sends 120 mouse moves through the actual event filters,
flushing normal Qt update requests after every move. No per-frame grabs or
forced full-window repaints occur. Results measure CPU interaction throughput,
not display presentation/VSync latency. Identical profiling overhead applies
when comparing a source snapshot with the current implementation.
"""

import argparse
from collections import defaultdict
import cProfile
import hashlib
import json
import math
import os
from pathlib import Path
import pstats
import statistics
import sys
import time


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--platform", default="offscreen")
    parser.add_argument("--media", type=Path)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--source-width", type=int, default=640)
    parser.add_argument("--source-height", type=int, default=360)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("interaction-bench.json"))
    parser.add_argument("--screenshot", type=Path)
    return parser.parse_args()


def distribution(values):
    values = sorted(values)
    return {"total_ms": sum(values), "mean_ms": statistics.mean(values),
            "median_ms": statistics.median(values),
            "p95_ms": values[min(len(values) - 1, math.ceil(len(values) * .95) - 1)],
            "max_ms": values[-1]}


def run(options):
    os.environ["QT_QPA_PLATFORM"] = options.platform
    project = options.project.resolve()
    sys.path.insert(0, str(project))
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, QPoint, QPointF, Qt, qVersion
    from PySide6.QtGui import QColor, QCursor, QImage, QMouseEvent, QRegion
    from PySide6.QtMultimedia import QVideoFrame
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from gridstudio.app import MainWindow, STYLE, VideoPane
    from gridstudio.canvas import VideoCanvas
    from gridstudio.free_canvas import FreeCanvas, _SelectionOverlay
    from gridstudio.hover_controls import HoverControls, SeekBar, _VideoTitle

    methods = defaultdict(lambda: {"calls": 0, "inclusive_ms": 0.0})
    measuring = False

    def instrument(cls, name):
        original = getattr(cls, name)
        key = cls.__name__ + "." + name

        def timed(self, *args, **kwargs):
            if not measuring:
                return original(self, *args, **kwargs)
            started = time.perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                row = methods[key]
                row["calls"] += 1
                row["inclusive_ms"] += (time.perf_counter() - started) * 1000

        setattr(cls, name, timed)

    for cls, names in (
        (MainWindow, ("select", "refresh_inspector")),
        (HoverControls, ("refresh", "refresh_geometry", "note_activity", "_refresh_transport", "_layout_transport")),
        (VideoCanvas, ("_fit_video", "paintEvent")),
        (VideoPane, ("update_content_mask",)),
        (FreeCanvas, ("set_rect", "_drag_to", "eventFilter")),
        (_SelectionOverlay, ("paintEvent",)),
        (_VideoTitle, ("paintEvent",)),
        (SeekBar, ("paintEvent",)),
    ):
        for name in names:
            if hasattr(cls, name):
                instrument(cls, name)

    class PaintEvents(QObject):
        def __init__(self):
            super().__init__()
            self.counts = defaultdict(int)
            self.area = defaultdict(int)
            self.regions = defaultdict(list)

        def eventFilter(self, watched, event):
            if measuring and event.type() == QEvent.Type.Paint:
                name = type(watched).__name__ + ":" + watched.objectName()
                self.counts[name] += 1
                self.area[name] += event.region().boundingRect().width() * event.region().boundingRect().height()
                self.regions[name].append(QRegion(event.region()))
            return False

    def region_area(region):
        """Compute exact region area after profiling, without paint-time scans."""
        if region.rectCount() <= 1:
            rect = region.boundingRect()
            return rect.width() * rect.height()
        if sys.platform != "win32":
            return None
        import ctypes
        import struct
        gdi = ctypes.windll.gdi32
        gdi.GetRegionData.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
        gdi.GetRegionData.restype = ctypes.c_uint32
        gdi.DeleteObject.argtypes = (ctypes.c_void_p,)
        gdi.DeleteObject.restype = ctypes.c_int
        handle = region.toHRGN()
        try:
            size = gdi.GetRegionData(handle, 0, None)
            if not size:
                raise RuntimeError("Cannot inspect native region data")
            buffer = ctypes.create_string_buffer(size)
            if not gdi.GetRegionData(handle, size, buffer):
                raise RuntimeError("Cannot read native region data")
            header_size, _kind, count, _bytes, *_bounds = struct.unpack_from("<IIII4i", buffer.raw)
            area = 0
            for offset in range(header_size, header_size + count * 16, 16):
                left, top, right, bottom = struct.unpack_from("<4i", buffer.raw, offset)
                area += max(0, right - left) * max(0, bottom - top)
            return area
        finally:
            gdi.DeleteObject(handle)

    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.set_clean_mode(False)
    win.setFixedSize(options.width, options.height)
    win.show()
    win.activateWindow()

    def flush():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.UpdateRequest)
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)

    while len(win.panes) < 4:
        win.add_blank()
    flush()
    panes = list(win.panes.values())
    rects = ((.04, .05, .45, .45), (.50, .08, .45, .45),
             (.10, .50, .45, .45), (.35, .28, .40, .40))
    for index, (pane, rect, color) in enumerate(zip(panes, rects, ("red", "lime", "blue", "magenta"))):
        win.canvas_workspace.set_rect(pane.state.id, rect)
        if options.media:
            pane.state.source = str(options.media.resolve())
            pane.state.paused = False
            pane.load_source()
        else:
            pane.state.source = f"synthetic-{index}.mp4"
            image = QImage(options.source_width, options.source_height, QImage.Format.Format_RGB32)
            image.fill(QColor(color))
            pane.canvas.set_has_media(True)
            pane.canvas.set_message("")
            pane.canvas.video_item.videoSink().setVideoFrame(QVideoFrame(image))
    win.select(panes[-1].state.id)
    win.playback.timer.stop()
    flush()
    if options.media:
        deadline = time.perf_counter() + 8
        while not all(p.canvas.video_item.videoSink().videoFrame().isValid() for p in panes):
            if time.perf_counter() > deadline:
                raise RuntimeError("Real media failed to decode four initial frames")
            QTest.qWait(10)
    QTest.qWait(30)
    flush()

    paint_events = PaintEvents()
    watched = [win, win.stage, win.canvas_workspace, win.canvas_workspace._overlay]
    for pane in panes:
        watched.extend((pane, pane.canvas, pane.canvas.viewport(),
                        pane.hover_controls.title, pane.hover_controls.bar))
    for widget in watched:
        widget.installEventFilter(paint_events)

    def mouse(target, kind, global_point, button, buttons):
        local = target.mapFromGlobal(global_point)
        event = QMouseEvent(kind, QPointF(local), QPointF(global_point), button, buttons,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, event)

    def media_snapshot():
        snapshots = []
        for index, layer in enumerate(panes):
            frame = layer.canvas.video_item.videoSink().videoFrame()
            snapshots.append({"pane": index, "position_ms": layer.player.position(),
                              "frame_valid": frame.isValid(), "frame_start_us": frame.startTime(),
                              "frame_size": [frame.width(), frame.height()],
                              "playback": layer.player.playbackState().name,
                              "error": layer.player.errorString()})
        return snapshots

    def gesture(kind, frames, profile=None):
        pane = panes[-1]
        stage = win.canvas_workspace
        stage.set_rect(pane.state.id, rects[-1])
        for layer in panes:
            layer.hover_controls.hide_now()
        flush()
        if kind == "move":
            content = pane.canvas.video_content_rect()
            start = pane.canvas.viewport().mapToGlobal(content.center())
            target = pane.canvas.viewport()
        else:
            start = stage.mapToGlobal(pane.geometry().bottomRight())
            target = stage
        QCursor.setPos(start)
        flush()
        methods.clear()
        paint_events.counts.clear()
        paint_events.area.clear()
        paint_events.regions.clear()
        dispatch_ms, paint_flush_ms = [], []
        positions = []
        for i in range(frames):
            t = (i + 1) / frames
            dx = 14 + round(100 * t)
            dy = 12 + round((50 if kind == "move" else 75) * t)
            positions.append(start + QPoint(dx, dy))
        before = pane.geometry().getRect()
        media_before = media_snapshot()
        if profile:
            profile.enable()
        started = time.perf_counter()
        mouse(target, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        if stage._drag is None:
            raise RuntimeError(f"{kind} press failed to start the actual canvas gesture")
        for point in positions:
            tick = time.perf_counter()
            mouse(stage, QEvent.Type.MouseMove, point, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
            dispatch_ms.append((time.perf_counter() - tick) * 1000)
            tick = time.perf_counter()
            flush()
            paint_flush_ms.append((time.perf_counter() - tick) * 1000)
        mouse(stage, QEvent.Type.MouseButtonRelease, positions[-1], Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        flush()
        total_ms = (time.perf_counter() - started) * 1000
        if profile:
            profile.disable()
        after = pane.geometry().getRect()
        media_after = media_snapshot()
        if not all(row["frame_valid"] for row in media_after):
            raise RuntimeError(f"{kind} lost a video frame")
        if before == after:
            raise RuntimeError(f"{kind} produced no geometry change")
        exact_area = {}
        for name, regions in paint_events.regions.items():
            areas = [region_area(region) for region in regions]
            exact_area[name] = sum(areas) if all(area is not None for area in areas) else None
        return {"frames": frames, "total_ms": total_ms,
                "dispatch_only": distribution(dispatch_ms), "event_and_paint_flush": distribution(paint_flush_ms),
                "instrumented_methods": {name: dict(row) for name, row in methods.items()}, "paint_event_counts": dict(paint_events.counts),
                "paint_bounding_area_px": dict(paint_events.area),
                "paint_exact_region_area_px": exact_area,
                "geometry_before": before, "geometry_after": after,
                "media_before": media_before, "media_after": media_after,
                "all_real_frames_advanced": (all(a["frame_start_us"] > b["frame_start_us"]
                                                  for a, b in zip(media_after, media_before))
                                             if options.media else None)}

    # Warm up both event paths and font/graphics caches outside timed sections.
    gesture("move", 8)
    gesture("resize", 8)
    results = {}
    for kind in ("move", "resize"):
        profile = cProfile.Profile()
        measuring = True
        result = gesture(kind, options.frames, profile)
        measuring = False
        stats = pstats.Stats(profile)
        rows = []
        for (filename, line, function), (primitive, calls, own, cumulative, _callers) in stats.stats.items():
            rows.append({"file": filename, "line": line, "function": function,
                         "calls": calls, "primitive_calls": primitive,
                         "own_ms": own * 1000, "cumulative_ms": cumulative * 1000})
        result["cprofile_top_cumulative"] = sorted(rows, key=lambda r: r["cumulative_ms"], reverse=True)[:24]
        result["cprofile_top_self"] = sorted(rows, key=lambda r: r["own_ms"], reverse=True)[:24]
        profile_path = options.output.with_suffix(f".{kind}.prof")
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile.dump_stats(str(profile_path))
        result["profile_path"] = str(profile_path.resolve())
        results[kind] = result

    sources = {}
    for filename in ("app.py", "free_canvas.py", "hover_controls.py", "canvas.py"):
        sources[filename] = hashlib.sha256((project / "gridstudio" / filename).read_bytes()).hexdigest()
    output = {"project": str(project), "qt": qVersion(), "platform": app.platformName(),
              "source": str(options.media.resolve()) if options.media else f"four synthetic {options.source_width}x{options.source_height} frames; no decoder",
              "window_size": [win.width(), win.height()], "stage_size": [win.stage.width(), win.stage.height()],
              "device_pixel_ratio": win.devicePixelRatioF(),
              "paint_area_units": "logical pixels; physical area scales with device pixel ratio squared",
              "source_sha256": sources, "results": results,
              "measurement_limits": "Profiled CPU dispatch/painting throughput; not GPU presentation latency. No per-frame grabs."}
    if options.screenshot:
        options.screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not win.grab().save(str(options.screenshot)):
            raise RuntimeError("Cannot save the final untimed screenshot")
        output["screenshot"] = str(options.screenshot.resolve())
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(options.output.resolve()), "platform": output["platform"],
                      "source": output["source"],
                      "results": {kind: {key: row[key] for key in ("total_ms", "dispatch_only", "event_and_paint_flush", "instrumented_methods", "paint_event_counts", "paint_exact_region_area_px")}
                                  for kind, row in results.items()}}, ensure_ascii=False))
    win.close()
    flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(run(arguments()))
