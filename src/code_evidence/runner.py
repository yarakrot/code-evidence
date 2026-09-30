"""Explicit trusted-host execution. This module is NOT a sandbox."""

import os
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .policy import Check
from .redaction import redact

MAX_LOG_BYTES = 1_000_000
ALLOWED_ENV = {
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "VIRTUAL_ENV",
}


def check_environment() -> dict:
    env = {key: value for key, value in os.environ.items() if key.upper() in ALLOWED_ENV}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"})
    return env


def kill_tree(process):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def execute(root: Path, check: Check) -> dict:
    started = time.monotonic()
    options = {"start_new_session": True} if os.name != "nt" else {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        process = subprocess.Popen(
            check.argv,
            cwd=root,
            env=check_environment(),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **options,
        )
    except OSError as error:
        return {
            "status": "launch_error",
            "exit_code": None,
            "duration_seconds": 0,
            "log": redact(str(error), str(root)),
            "log_truncated": False,
        }
    chunks = deque()
    size = 0
    truncated = False
    capture_lock = threading.Lock()

    def collect():
        nonlocal size, truncated
        try:
            while chunk := process.stdout.read1(8192):
                with capture_lock:
                    chunks.append(chunk)
                    size += len(chunk)
                    while size > MAX_LOG_BYTES:
                        excess = size - MAX_LOG_BYTES
                        first = chunks.popleft()
                        if len(first) > excess:
                            chunks.appendleft(first[excess:])
                            size -= excess
                        else:
                            size -= len(first)
                        truncated = True
        except (OSError, ValueError):
            pass

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    status = "passed"
    try:
        code = process.wait(timeout=check.timeout_seconds)
        if code:
            status = "failed"
    except subprocess.TimeoutExpired:
        status = "timeout"
        kill_tree(process)
        code = process.wait(timeout=10)
    finally:
        reader.join(timeout=2)
        if reader.is_alive():
            kill_tree(process)
            reader.join(timeout=2)
            if reader.is_alive():
                status = "capture_error"
        if not reader.is_alive():
            process.stdout.close()
    with capture_lock:
        log = b"".join(chunks).decode("utf-8", "replace")
    return {
        "status": status,
        "exit_code": code,
        "duration_seconds": round(time.monotonic() - started, 3),
        "log": redact(log, str(root)),
        "log_truncated": truncated,
    }
