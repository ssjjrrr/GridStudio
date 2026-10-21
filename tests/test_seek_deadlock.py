"""The fixed command breaks a controlled native Qt connection-lock/GIL cycle.

The worker callback widens a real Qt mutex scheduling window with a finite
sleep. This tests that lock order with a decoded frame, rather than claiming
to reproduce the exact native stack of a past intermittent application hang.
Only fixed mode runs in the suite; an unsafe direct seek must never hang the
pytest process. Launch the actual base interpreter so timeout kills the media
process itself instead of leaving a Windows venv launcher's child orphaned.
"""

import json
import os
from pathlib import Path
import site
import subprocess
import sys

import pytest


def output_text(value):
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def test_fixed_seek_releases_gil_during_worker_disconnect_and_decodes_target_frame():
    project = Path(__file__).resolve().parents[1]
    helper = Path(__file__).resolve().parent / "helpers" / "seek_deadlock_probe.py"
    media = Path(__file__).resolve().parent / "fixtures" / "sample.mp4"
    assert helper.is_file()
    assert media.is_file(), "The real H.264 regression fixture is required"
    base_interpreter = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    assert base_interpreter.is_file()

    # A base interpreter does not automatically adopt the current venv's
    # packages. Forward import directories, not the launcher executable.
    import_paths = [str(project), *site.getsitepackages()]
    import_paths.extend(path for path in sys.path
                        if path and Path(path).is_dir()
                        and Path(path).name in ("site-packages", "dist-packages"))
    import_paths.extend(path for path in os.environ.get("PYTHONPATH", "").split(os.pathsep) if path)
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(dict.fromkeys(import_paths)))
    command = [str(base_interpreter), "-u", str(helper), "--mode", "fixed",
               "--platform", "offscreen", "--media", str(media)]
    try:
        result = subprocess.run(command, cwd=project, env=environment,
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=10)
    except subprocess.TimeoutExpired as error:
        pytest.fail("Fixed Qt seek deadlock probe exceeded its 10-second process deadline.\n"
                    + output_text(error.stdout) + output_text(error.stderr))
    diagnostics = result.stdout + result.stderr
    assert result.returncode == 0, diagnostics
    records = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    events = [record["event"] for record in records]
    for expected in ("worker_disconnect_notify_entered", "worker_disconnect_notify_returned",
                     "seek_begin", "seek_return", "probe_pass"):
        assert expected in events, diagnostics
    assert (events.index("worker_disconnect_notify_entered") < events.index("seek_begin")
            < events.index("worker_disconnect_notify_returned") < events.index("seek_return")), diagnostics
    start = next(record for record in records if record["event"] == "seek_begin")
    passed = next(record for record in records if record["event"] == "probe_pass")
    assert start["mode"] == passed["mode"] == "fixed"
    assert start["correct_player_thread"]
    assert passed["receiver_destroyed"] and passed["worker_exited"]
    assert passed["target"] == 4000
    assert passed["position_ms"] == pytest.approx(passed["target"], abs=80)
    assert passed["frame_ms"] == pytest.approx(passed["target"], abs=100)
