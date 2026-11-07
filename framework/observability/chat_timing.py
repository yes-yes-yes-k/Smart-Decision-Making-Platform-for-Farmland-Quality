"""Low-overhead JSONL stage timing for chat requests."""
from __future__ import annotations

import json
import os
import time
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

_LOG_DIR = "logs"


def record_chat_stage(
    trace_id: str, stage: str, started: float, *, route: str = "unknown",
    status: str = "ok", **attributes,
) -> None:
    entry = {
        "trace_id": trace_id,
        "stage": stage,
        "route": route,
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **attributes,
    }
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        path = os.path.join(_LOG_DIR, f"chat_timing_{datetime.now(timezone.utc):%Y%m%d}.jsonl")
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        warnings.warn(f"[chat-timing] log write failed: {exc}")


@contextmanager
def chat_stage(trace_id: str | None, stage: str, *, route: str = "unknown") -> Iterator[str]:
    request_trace = trace_id or uuid4().hex
    started = time.perf_counter()
    status = "ok"
    try:
        yield request_trace
    except Exception:
        status = "error"
        raise
    finally:
        record_chat_stage(request_trace, stage, started, route=route, status=status)
