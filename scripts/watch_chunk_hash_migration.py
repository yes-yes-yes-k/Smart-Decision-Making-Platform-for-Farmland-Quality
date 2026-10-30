"""Watch migration checkpoints and verify final hash coverage on completion."""
import argparse
import ctypes
from datetime import datetime, UTC
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def process_alive(pid):
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # access denied is not proof of exit
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--final-inventory", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=10)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("poll interval must be positive")
    args.events.parent.mkdir(parents=True, exist_ok=True)
    last = None
    def emit(event):
        event["observed_at"] = datetime.now(UTC).isoformat()
        line = json.dumps(event, ensure_ascii=False)
        with args.events.open("a", encoding="utf-8") as stream:
            stream.write(line+"\n")
        print(line, flush=True)
    while True:
        try:
            report = json.loads(args.report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(args.poll_seconds)
            continue
        stamp = (report["state"], len(report["documents"]), report.get("updated_chunks", 0), report["failed"])
        if stamp != last:
            emit(dict(event="checkpoint", state=stamp[0], processed_documents=stamp[1],
                selected_documents=report["selected_documents"], updated_chunks=stamp[2], failed=stamp[3],
                last_document_id=report.get("last_document_id")))
            last = stamp
        if report["state"] == "paused":
            emit(dict(event="paused"))
            return 0
        if report["state"] in {"completed", "completed_with_blocks"}:
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run([sys.executable, str(root / "scripts/inventory_chunk_content_hashes.py"),
                "--output", str(args.final_inventory.resolve())], cwd=root, capture_output=True, timeout=600)
            if result.returncode:
                emit(dict(event="final_inventory_failed"))
                return 1
            inventory = json.loads(args.final_inventory.read_text(encoding="utf-8"))
            passed = (inventory["remaining_documents"] == 0 and
                not inventory["totals"].get("conflicting", 0) and not inventory["count_mismatch_documents"])
            emit(dict(event="coverage_verified" if passed else "coverage_requires_attention",
                eligible_documents=inventory["eligible_documents"], fully_bound_documents=inventory["fully_bound_documents"],
                remaining_documents=inventory["remaining_documents"], totals=inventory["totals"],
                count_mismatch_documents=inventory["count_mismatch_documents"]))
            return int(not passed)
        if not process_alive(int(report["process_id"])):
            # A report can race with the producer's final atomic replace.
            time.sleep(2)
            current = json.loads(args.report.read_text(encoding="utf-8"))
            if current["state"] == "running":
                emit(dict(event="process_exited_before_completion", process_id=report["process_id"]))
                return 1
            continue
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
