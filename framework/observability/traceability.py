"""结果追溯链：按 trace_id 追溯数据版本、Agent 版本、参数、调用时间。"""
from __future__ import annotations
from typing import Any, Dict, Optional
from .routing_log import read_routing_logs


def trace_result(trace_id: str, log_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """按 trace_id 返回该次调用的追溯信息。

    遍历路由日志，返回含 data_version / agent_version / params / timestamp 的记录；
    未找到返回 None。
    """
    for entry in read_routing_logs(log_dir):
        if entry.get("trace_id") == trace_id:
            return {
                "trace_id": trace_id,
                "data_version": entry.get("data_version"),
                "agent_version": entry.get("agent_version"),
                "params": entry.get("params", {}),
                "call_time": entry.get("timestamp"),
            }
    return None