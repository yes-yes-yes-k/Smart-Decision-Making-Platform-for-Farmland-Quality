"""Manage the research evidence comparison worker process.

R3.2. The worker code (GraphExtractionWorker.run_forever and
ResearchService.run_once) already exists. This script provides the
start/stop/status management layer so the worker can be run as a
background process with a clear identity and lifecycle.

Usage:
    python scripts/manage_research_worker.py start [--mode extraction|comparison]
    python scripts/manage_research_worker.py stop
    python scripts/manage_research_worker.py status

The worker_id is ``hostname:pid`` so lease ownership is traceable.
A PID file at ``.workbuddy/research-worker.pid`` tracks the live process.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PID_FILE = PROJECT_ROOT / ".workbuddy" / "research-worker.pid"


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _terminate(pid: int, timeout: float = 10.0) -> bool:
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
            if not handle:
                return False
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 15)  # SIGTERM
        except (ProcessLookupError, PermissionError):
            return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _is_running(pid):
            return True
        time.sleep(0.5)
    return False


def cmd_start(mode: str) -> int:
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"worker already running (pid={pid})")
        return 1

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Launch the worker as a detached subprocess.
    worker_script = PROJECT_ROOT / "scripts" / "_research_worker_loop.py"
    if not worker_script.exists():
        print(f"worker script not found: {worker_script}")
        return 1

    import subprocess
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, str(worker_script), "--mode", mode],
        stdout=open(PROJECT_ROOT / ".workbuddy" / "research-worker.log", "a"),
        stderr=subprocess.STDOUT,
        cwd=str(PROJECT_ROOT),
        creationflags=creationflags,
    )
    PID_FILE.write_text(str(proc.pid))
    time.sleep(1)
    if proc.poll() is not None:
        print(f"worker exited immediately (code={proc.returncode})")
        PID_FILE.unlink(missing_ok=True)
        return 1
    print(f"worker started (pid={proc.pid}, mode={mode}, worker_id={socket.gethostname()}:{proc.pid})")
    return 0


def cmd_stop() -> int:
    pid = _read_pid()
    if not pid:
        print("no worker running (pid file not found)")
        return 1
    if not _is_running(pid):
        print(f"worker process not running (pid={pid} stale)")
        PID_FILE.unlink(missing_ok=True)
        return 0
    if _terminate(pid):
        print(f"worker stopped (pid={pid})")
    else:
        print(f"worker did not terminate gracefully (pid={pid})")
    PID_FILE.unlink(missing_ok=True)
    return 0


def cmd_status() -> int:
    pid = _read_pid()
    if not pid:
        print("status=stopped (no pid file)")
        return 0
    if _is_running(pid):
        print(f"status=running pid={pid} worker_id={socket.gethostname()}:{pid}")
        return 0
    else:
        print(f"status=stopped (pid={pid} stale)")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the research evidence worker")
    parser.add_argument("command", choices=["start", "stop", "status"])
    parser.add_argument("--mode", choices=["extraction", "comparison"], default="comparison",
                        help="worker mode (default: comparison)")
    args = parser.parse_args()
    sys.exit({"start": lambda: cmd_start(args.mode),
              "stop": cmd_stop,
              "status": cmd_status}[args.command]())


if __name__ == "__main__":
    main()
