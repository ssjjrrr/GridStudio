"""Run a command with streamed logs and bounded macOS native hang capture.

Example:
    python scripts/run_diagnostics.py --output artifacts/mac-arm \
        --idle-timeout 60 --timeout 420 -- python -u -m pytest tests -vv

This is a diagnostic command supervisor, not a retry mechanism. A timeout
always fails with exit status 124, even if the child exits while being sampled.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time


def announce(message: str) -> None:
    print(f"[diagnostics] {message}", flush=True)


def forward_output(pipe, messages: queue.Queue) -> None:
    try:
        while chunk := pipe.read(65536):
            messages.put(chunk)
    finally:
        messages.put(None)


def stop_process_group(process: subprocess.Popen) -> None:
    """Bound cleanup, including media subprocesses inherited by the command."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        # The group may outlive its leader; kill remaining children too.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # Windows has no POSIX killpg. taskkill /T also handles venv launchers
        # whose real interpreter is a child rather than the immediate PID.
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        announce(f"Child PID {process.pid} did not confirm exit after forced termination")


def capture_native(process: subprocess.Popen, output: Path) -> dict:
    sample_log = output / "native-sample.log"
    if sys.platform != "darwin":
        explanation = "Native /usr/bin/sample capture is available only on macOS.\n"
        sample_log.write_text(explanation, encoding="utf-8")
        return {"status": "unavailable", "reason": explanation.strip()}
    command = ["/usr/bin/sample", str(process.pid), "5", "-file", str(output / "native-sample.txt")]
    announce(f"Capturing all native threads of PID {process.pid} with /usr/bin/sample")
    with sample_log.open("wb") as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=20, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "command": command, "timeout_seconds": 20}
        except OSError as error:
            log.write(str(error).encode("utf-8", errors="replace"))
            return {"status": "error", "command": command, "error": str(error)}
    sample = output / "native-sample.txt"
    captured = result.returncode == 0 and sample.is_file() and sample.stat().st_size > 0
    return {"status": "captured" if captured else "failed", "command": command,
            "returncode": result.returncode, "sample_bytes": sample.stat().st_size if sample.is_file() else 0}


def run(command: list[str], output: Path, idle_timeout: float, timeout: float) -> int:
    output.mkdir(parents=True, exist_ok=True)
    # These four files belong to this invocation; avoid stale samples from a
    # prior run being mistaken for evidence about a successful command.
    for name in ("stdout.log", "native-sample.txt", "native-sample.log", "diagnostics.json"):
        (output / name).unlink(missing_ok=True)
    record = {"command": command, "platform": sys.platform,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "idle_timeout_seconds": idle_timeout, "timeout_seconds": timeout}
    process = None
    reader = None
    messages = queue.Queue()
    started = last_output = time.monotonic()
    status = 1
    reason = "supervisor_error"
    timed_out = False
    eof = False
    finished_at = None
    try:
        options = {"start_new_session": True} if os.name == "posix" else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
        environment = dict(os.environ)
        environment.setdefault("PYTHONUNBUFFERED", "1")
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, bufsize=0, env=environment, **options)
        record["pid"] = process.pid
        announce(f"Started PID {process.pid}; logs in {output}")
        reader = threading.Thread(target=forward_output, args=(process.stdout, messages), daemon=True)
        reader.start()
        with (output / "stdout.log").open("wb") as log:
            while True:
                try:
                    chunk = messages.get(timeout=.1)
                except queue.Empty:
                    chunk = b""
                if chunk is None:
                    eof = True
                elif chunk:
                    last_output = time.monotonic()
                    log.write(chunk)
                    log.flush()
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                now = time.monotonic()
                returncode = process.poll()
                if returncode is not None:
                    if finished_at is None:
                        finished_at = now
                    if eof or now - finished_at >= 2:
                        status = returncode if returncode >= 0 else 128 - returncode
                        reason = "completed"
                        break
                if returncode is None and (now - last_output >= idle_timeout or now - started >= timeout):
                    reason = "output_idle_timeout" if now - last_output >= idle_timeout else "wall_timeout"
                    record["silence_seconds"] = round(now - last_output, 3)
                    timed_out = True
                    announce(f"{reason}: capturing evidence, then stopping the command (exit 124)")
                    record["native_sample"] = capture_native(process, output)
                    stop_process_group(process)
                    status = 124
                    break
            # Keep output generated while sampling or terminating, without
            # waiting forever on a descendant that inherited the output pipe.
            if reader is not None:
                reader.join(timeout=1)
            while not messages.empty():
                chunk = messages.get_nowait()
                if chunk:
                    log.write(chunk)
                    sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    except KeyboardInterrupt:
        reason, status = "interrupted", 130
    except OSError as error:
        record["error"] = str(error)
        announce(f"Supervisor error: {error}")
    finally:
        if process is not None and process.poll() is None:
            stop_process_group(process)
        record.update({"reason": reason, "timed_out": timed_out, "exit_status": status,
                       "child_returncode": process.poll() if process is not None else None,
                       "elapsed_seconds": round(time.monotonic() - started, 3)})
        (output / "diagnostics.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    announce(f"Finished: {reason}, exit {status}")
    return status


def positive(value: str) -> float:
    number = float(value)
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("Timeout must be a finite positive number")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--idle-timeout", type=positive, default=60)
    parser.add_argument("--timeout", type=positive, default=420)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Provide the command after --")
    return run(command, args.output.resolve(), args.idle_timeout, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
