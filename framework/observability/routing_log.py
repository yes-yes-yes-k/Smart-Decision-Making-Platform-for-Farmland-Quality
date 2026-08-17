"""本地路由/调用观测日志：JSON 行式落盘。

复用 framework/upload/audit_logger.py 的 JSON 行式范式。
默认写入 logs/ 目录，按天文件命名（routing_calls_YYYYMMDD.jsonl）。
可通过 set_log_enabled / set_log_dir / set_log_path 控制开关与路径（便于测试）。
"""
from __future__ import annotations
import os
import json
import warnings
from datetime import datetime
from typing import Any, Dict, Optional

# 默认配置
_LOG_DIR = os.path.join("logs")
_LOG_ENABLED = True
_LOG_PATH_OVERRIDE: Optional[str] = None


def set_log_enabled(enabled: bool) -> None:
    """开关本地路由日志（默认开启；False 时静默跳过写入）。"""
    global _LOG_ENABLED
    _LOG_ENABLED = enabled


def set_log_dir(path: str) -> None:
    """覆盖日志目录（每日文件名按日期生成）。"""
    global _LOG_DIR
    _LOG_DIR = path


def set_log_path(path: str) -> None:
    """直接覆盖日志文件路径（主要用于测试，忽略按天命名）。"""
    global _LOG_PATH_OVERRIDE
    _LOG_PATH_OVERRIDE = path


def _resolve_log_path() -> Optional[str]:
    if not _LOG_ENABLED:
        return None
    if _LOG_PATH_OVERRIDE is not None:
        return _LOG_PATH_OVERRIDE
    day = datetime.now().strftime("%Y%m%d")
    return os.path.join(_LOG_DIR, f"routing_calls_{day}.jsonl")


def write_routing_log_to_db(entry: Dict[str, Any]) -> None:
    """将 entry 写入 routing_decision_log 表。

    抛出所有异常由调用方 try/except 隔离（IntegrityError/OperationalError/字段缺失等）。
    """
    from framework.models import db, RoutingDecisionLog
    log = RoutingDecisionLog(
        trace_id=entry["trace_id"],
        question=entry["question"],
        question_type=entry["question_type"],
        relevance=entry.get("relevance"),
        routing_status=entry.get("routing_status", "normal"),
        router_method=entry.get("router_method", "keyword"),
        candidate_agents=entry.get("candidate_agents"),
        hit_exclusive_rules=entry.get("hit_exclusive_rules"),
        llm_reason=entry.get("llm_reason"),
        llm_duration_ms=entry.get("llm_duration_ms"),
        total_duration_ms=entry.get("total_duration_ms"),
        degradation=entry.get("degradation"),
        five_dim_context=entry.get("five_dim_context"),
        data_version=entry.get("data_version"),
        agent_version=entry.get("agent_version"),
        result_version=entry.get("result_version", "v1.2"),
        failure_reason=entry.get("failure_reason"),
        logged_at=entry.get("logged_at"),
    )
    db.session.add(log)
    db.session.commit()


def write_routing_log(entry: Dict[str, Any]) -> None:
    """追加一条 JSON 行式路由日志；日志关闭时静默跳过。"""
    path = _resolve_log_path()
    if path is None:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_routing_logs(log_dir: Optional[str] = None) -> list[Dict[str, Any]]:
    """读取目录下所有按天命名的路由日志（用于看板/追溯）。"""
    base_dir = log_dir or _LOG_DIR
    entries: list[Dict[str, Any]] = []
    if not os.path.isdir(base_dir):
        return entries
    for name in sorted(os.listdir(base_dir)):
        if name.startswith("routing_calls_") and name.endswith(".jsonl"):
            with open(os.path.join(base_dir, name), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        # 单行损坏不中断整体读取（看板/追溯健壮性）
                        warnings.warn(f"[observability] 跳过损坏的路由日志行: {exc}")
    return entries