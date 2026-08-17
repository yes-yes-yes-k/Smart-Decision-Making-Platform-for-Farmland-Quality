"""路由观测封装：在 nodes.identify_question_node 内包装两次路由调用，记录观测数据。

observe_routing() 不改变路由判定结果，仅额外写入 JSON 行式日志。
返回 (question_type, relevance, final_type, routing_status)，字段与现状完全一致。
"""
from __future__ import annotations
import warnings
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from framework.agents.exclusive_rules import (
    EXCLUSIVE_RULES,
    _rule_matches,
    apply_exclusive_rules,
)
from framework.agents.router import QuestionTypeRouter
from framework.agents.routing import identify_question_type
from .routing_log import write_routing_log

# 结果版本：路由算法判定签名版本，随判定演进递增
ROUTING_RESULT_VERSION = "v1.2"

_router = QuestionTypeRouter()


def _matched_rules(question: str, context: Optional[dict]) -> list[str]:
    """返回命中的排他规则 target（只读，不改变路由行为）。"""
    return [r.target for r in EXCLUSIVE_RULES if _rule_matches(r, question, context)]


def _safe_write_log(entry: Dict[str, Any]) -> None:
    """安全写入观测日志：失败仅告警，绝不传播异常/掩盖路由结果。

    观测写入属非功能性副作用，日志系统故障（盘满、目录不可写等）不得
    影响路由主流程，也不得替换已发生的原始路由异常。
    """
    try:
        write_routing_log(entry)
    except Exception as exc:  # noqa: BLE001 - 观测副作用必须全面隔离
        warnings.warn(f"[observability] 路由日志写入失败，已忽略: {exc}")


def _attach_llm_routing_state(entry: Dict[str, Any]) -> None:
    """从 routing 模块读取 LLM 路由观测状态并附加到日志 entry。"""
    try:
        from framework.agents import routing as _routing
        entry["router_method"] = _routing._last_router_method
        entry["llm_reason"] = _routing._last_llm_reason
        entry["llm_duration_ms"] = _routing._last_llm_duration_ms
    except Exception:
        # routing 模块未就绪时仍保留字段（默认值）
        entry.setdefault("router_method", "keyword")
        entry.setdefault("llm_reason", None)
        entry.setdefault("llm_duration_ms", None)


def observe_routing(
    question: str,
    context: Optional[dict] = None,
    *,
    trace_id: Optional[str] = None,
    data_version: Optional[str] = None,
    agent_version: Optional[str] = None,
    params: Optional[dict] = None,
) -> Tuple[int, float, int, str]:
    """执行并观测一次完整路由判定。

    与 nodes.identify_question_node 现状一致地调用 identify_question_type（内部已应用
    排他规则）后，再次调用 apply_exclusive_rules，返回 (question_type, relevance,
    final_type, routing_status)。内部异常时写入 failure_reason 后重新抛出。
    """
    tid = trace_id or uuid.uuid4().hex
    entry: Dict[str, Any] = {
        "trace_id": tid,
        "question": question,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_version": data_version,
        "agent_version": agent_version,
        "params": params or {},
        "result_version": ROUTING_RESULT_VERSION,
        "failure_reason": None,
    }
    t0 = time.perf_counter()
    try:
        question_type, relevance = identify_question_type(question, context)
        entry["relevance"] = relevance
        entry["candidate_agents"] = _router.get_agents_for_type(question_type)
        entry["hit_exclusive_rules"] = _matched_rules(question, context)
        final_type, routing_status = apply_exclusive_rules(question, question_type, context)
        entry["question_type"] = final_type
        entry["routing_status"] = routing_status
        entry["degradation"] = routing_status
        _attach_llm_routing_state(entry)
        _FIVE_DIM_KEYS = ("scale", "data_type", "business_task", "expected_output")
        entry["five_dim_context"] = (
            {k: context.get(k) for k in _FIVE_DIM_KEYS} if context else {}
        )
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        return question_type, relevance, final_type, routing_status
    except Exception as exc:
        entry["failure_reason"] = str(exc)
        _attach_llm_routing_state(entry)
        _FIVE_DIM_KEYS = ("scale", "data_type", "business_task", "expected_output")
        entry["five_dim_context"] = (
            {k: context.get(k) for k in _FIVE_DIM_KEYS} if context else {}
        )
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        raise