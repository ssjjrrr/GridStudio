"""Compare deterministic playback work counts without opening a video decoder.

Install requirements-dev.txt first: the benchmark reuses the current source's
fake-player fixtures from tests/test_playback_perf.py. --baseline points to an
older source root containing gridstudio/playback.py; only its controller is
loaded. No wall-clock CPU, decoding throughput or display FPS is measured.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


SCENARIOS = (
    "64_independent_50_ticks",
    "8_paused_percent_50_ticks",
    "8_playing_percent_50_ticks",
    "8_playing_percent_ab_50_ticks",
    "join_8_percent",
    "media_ready_8_percent",
    "seek_8_percent",
)


def summarize(owner):
    queries = {}
    for pane in owner.panes.values():
        for name, count in pane.player.queries.items():
            queries[name] = queries.get(name, 0) + count
    return {
        "queries": queries,
        "total_queries": sum(queries.values()),
        "apply_state_calls": sum(len(p.applied) for p in owner.panes.values()),
        "inspector_refreshes": owner.refreshes,
    }


def measure(controller_type, owner_type, scenario):
    owner = owner_type()
    controller = controller_type(owner)
    try:
        if scenario == "64_independent_50_ticks":
            for i in range(64):
                owner.add(str(i), paused=False)
            owner.clear_counts()
            for _ in range(50):
                controller.tick()
        else:
            paused = scenario == "8_paused_percent_50_ticks"
            for i in range(8):
                owner.add(str(i), duration=10_000 * (i + 1),
                          position=1000 * (i + 1), paused=paused)
            if scenario != "join_8_percent":
                controller.join_group(list(owner.panes), mode="percent")
                if scenario == "8_playing_percent_ab_50_ticks":
                    controller.set_loop("0", True, 1000, 5000)
                owner.clear_counts()
            if scenario.endswith("50_ticks"):
                for _ in range(50):
                    controller.tick()
            elif scenario == "join_8_percent":
                controller.join_group(list(owner.panes), mode="percent")
            elif scenario == "media_ready_8_percent":
                controller.media_ready("7")
            elif scenario == "seek_8_percent":
                controller.seek("0", 3000)
        result = summarize(owner)
        result["timer_active_after_action"] = controller.timer.isActive()
        return result
    finally:
        controller.timer.stop()
        controller.deleteLater()
        owner.deleteLater()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Older source root containing gridstudio/playback.py")
    parser.add_argument("--output", type=Path, required=True,
                        help="Write JSON with source hashes and before/after work counts")
    options = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    before_path = options.baseline.resolve() / "gridstudio" / "playback.py"
    after_path = project / "gridstudio" / "playback.py"
    if not before_path.is_file():
        parser.error("--baseline must contain gridstudio/playback.py")

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path[:0] = [str(project), str(project / "tests")]
    from PySide6.QtWidgets import QApplication
    from gridstudio.playback import PlaybackController
    from test_playback_perf import CountingOwner

    spec = importlib.util.spec_from_file_location("gridstudio._playback_query_before", before_path)
    before = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = before
    spec.loader.exec_module(before)
    application = QApplication.instance() or QApplication([])
    result = {
        "note": ("Getter-equivalent counts from pure Python fake players. Fifty manually "
                 "invoked ticks represent one second at 20 ms. No event loop is pumped "
                 "during each measurement; timer state is inspected separately. These "
                 "counts are not CPU timings, decoder performance or display FPS."),
        "sources": {
            label: {"playback_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for label, path in (("before", before_path), ("after", after_path))
        },
        "scenarios": {
            scenario: {
                "before": measure(before.PlaybackController, CountingOwner, scenario),
                "after": measure(PlaybackController, CountingOwner, scenario),
            }
            for scenario in SCENARIOS
        },
    }
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    # Keep the QApplication alive until every QObject and timer is retired.
    application.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
