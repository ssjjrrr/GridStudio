"""The test wait must not introduce a GIL/Qt-lock cycle absent from app.exec."""

import os
from pathlib import Path
import site
import subprocess
import sys

import pytest


def test_wait_allows_worker_disconnection_while_delivering_native_deferred_delete():
    project = Path(__file__).resolve().parents[1]
    helper = Path(__file__).parent / "helpers" / "qt_wait_probe.py"
    # Use the actual interpreter, not a Windows venv launcher: timeout must
    # terminate the Qt process itself if this lock-order regression reappears.
    interpreter = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
    paths = [str(project), *site.getsitepackages()]
    paths.extend(path for path in os.environ.get("PYTHONPATH", "").split(os.pathsep) if path)
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(dict.fromkeys(paths)))
    try:
        result = subprocess.run([interpreter, "-u", str(helper)], cwd=project, env=environment,
                                capture_output=True, timeout=8)
    except subprocess.TimeoutExpired as error:
        pytest.fail("Qt event-loop wait deadlocked during native deletion.\n"
                    + (error.stdout or b"").decode("utf-8", errors="replace")
                    + (error.stderr or b"").decode("utf-8", errors="replace"))
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert result.returncode == 0, output
    assert "PASS: worker GIL progress, native deletion, timers and zero-duration flush" in output
