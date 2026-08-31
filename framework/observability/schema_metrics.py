"""Schema 版本与规范状态的轻量运行时计数器。

计数器只用于进程内观测，不参与模型计算，也不把审计信息写入公共响应。
"""
from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any, Dict

_lock = Lock()
_schema_calls: Counter[str] = Counter()
_status_calls: Counter[str] = Counter()


def record_schema_call(schema_version: str, status: str) -> None:
    with _lock:
        _schema_calls[str(schema_version)] += 1
        _status_calls[str(status)] += 1


def snapshot_schema_metrics() -> Dict[str, Any]:
    with _lock:
        return {
            "schema_calls": dict(_schema_calls),
            "status_calls": dict(_status_calls),
        }


def reset_schema_metrics() -> None:
    with _lock:
        _schema_calls.clear()
        _status_calls.clear()


__all__ = ["record_schema_call", "snapshot_schema_metrics", "reset_schema_metrics"]
