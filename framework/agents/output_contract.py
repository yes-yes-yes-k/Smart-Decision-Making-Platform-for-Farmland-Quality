"""专题模型统一输出契约与分层投影。

该模块只负责纯数据转换，不执行模型、不访问数据库。所有模型路径（数据库、
文件、规则降级和 Function Calling）都应先转换为规范模型结果，再由调用方选择投影。
"""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


SCHEMA_VERSION = "2.0"
LEGACY_SCHEMA_VERSION = "1.0"
VALID_STATUSES = frozenset({"ok", "degraded", "rejected", "unavailable", "error"})
MODEL5_QUANTITATIVE_UNAVAILABLE = "MODEL5_QUANTITATIVE_UNAVAILABLE"
MODEL5_REAL_SOURCES = frozenset({"shaoguan_rf", "global_etr", "rf_model"})


@dataclass(frozen=True)
class Issue:
    """机器可读的问题项。"""

    code: str
    severity: str
    message: str
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.field:
            item["field"] = self.field
        if self.details:
            item["details"] = self.details
        return item


def _issue(code: str, severity: str, message: str, **kwargs: Any) -> Dict[str, Any]:
    return Issue(code, severity, message, **kwargs).as_dict()


def sanitize_json(value: Any, issues: Optional[List[Dict[str, Any]]] = None, path: str = "") -> Any:
    """递归转换为严格 JSON 可表示的值，非有限浮点数转换为 None。"""
    if isinstance(value, float):
        if not math.isfinite(value):
            if issues is not None:
                issues.append(_issue(
                    "NON_FINITE_VALUE", "warning",
                    "非有限数值已转换为 null。", field=path or None,
                ))
            return None
        return value
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_json(item, issues, f"{path}.{key}" if path else str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_json(item, issues, f"{path}[{idx}]") for idx, item in enumerate(value)]
    if hasattr(value, "item") and callable(value.item):
        try:
            return sanitize_json(value.item(), issues, path)
        except Exception:
            pass
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def validate_result(result: Mapping[str, Any]) -> Tuple[bool, List[str]]:
    """校验规范信封，返回是否有效及错误列表。"""
    errors: List[str] = []
    required = ("model_id", "status", "subject", "result", "meta", "issues")
    for key in required:
        if key not in result:
            errors.append(f"缺少字段: {key}")
    if result.get("status") not in VALID_STATUSES:
        errors.append("status 不在允许集合中")
    subject = result.get("subject")
    if not isinstance(subject, Mapping) or subject.get("type") not in {"parcel", "area", "unknown"}:
        errors.append("subject.type 无效")
    elif "id" not in subject:
        errors.append("subject 缺少字段: id")
    if not isinstance(result.get("model_id"), str) or not result.get("model_id"):
        errors.append("model_id 必须为非空字符串")
    if not isinstance(result.get("meta"), Mapping):
        errors.append("meta 必须为对象")
    else:
        for key in ("data_source", "simulated", "model_version"):
            if key not in result["meta"]:
                errors.append(f"meta 缺少字段: {key}")
    if not isinstance(result.get("issues"), list):
        errors.append("issues 必须为数组")
    else:
        for index, item in enumerate(result["issues"]):
            if not isinstance(item, Mapping):
                errors.append(f"issues[{index}] 必须为对象")
                continue
            for key in ("code", "severity", "message"):
                if key not in item:
                    errors.append(f"issues[{index}] 缺少字段: {key}")
        if result.get("status") in {"degraded", "rejected", "unavailable", "error"} and not result["issues"]:
            errors.append("非 ok 状态至少需要一条 issues")
    status = result.get("status")
    if status in {"ok", "degraded"} and result.get("result") is not None and not isinstance(result.get("result"), Mapping):
        errors.append("ok/degraded 的 result 必须为对象或 null")
    if status in {"rejected", "unavailable", "error"} and result.get("result") is not None:
        errors.append("失败状态的 result 必须为 null")
    return not errors, errors


def _canonical_model_id(agent: Any) -> str:
    capability = getattr(agent, "capability", None) or {}
    return str(capability.get("model_id") or getattr(agent, "model_id", "unknown"))


def _agent_id(agent: Any) -> str:
    return str(getattr(agent, "agent_id", "") or getattr(agent, "model_id", ""))


def _subject(payload: Mapping[str, Any], raw: Mapping[str, Any], model_id: str) -> Dict[str, Any]:
    parcel_id = next(
        (source[key] for source in (payload, raw) for key in ("parcel_id", "parcel_code")
         if key in source and source[key] is not None),
        None,
    )
    if parcel_id is not None:
        return {"type": "parcel", "id": str(parcel_id)}
    area_code = next(
        (source["area_code"] for source in (payload, raw)
         if "area_code" in source and source["area_code"] is not None),
        None,
    )
    if area_code is not None:
        return {"type": "area", "id": str(area_code)}
    return {"type": "unknown", "id": None}


def _status_and_issue(execution: Mapping[str, Any], simulated: bool, source: str) -> Tuple[str, List[Dict[str, Any]]]:
    raw = str(execution.get("status", "error")).lower()
    if raw in {"success", "complete", "completed"}:
        raw = "ok"
    if raw in {"fallback", "partial"}:
        raw = "degraded"
    if raw not in VALID_STATUSES:
        raw = "error"
    if raw == "ok" and simulated:
        raw = "degraded"

    issues: List[Dict[str, Any]] = []
    metadata = execution.get("metadata") if isinstance(execution.get("metadata"), Mapping) else {}
    nested = execution.get("result") if isinstance(execution.get("result"), Mapping) else {}
    reason = (
        execution.get("reason")
        or execution.get("fallback_reason")
        or metadata.get("fallback_reason")
        or nested.get("reason")
        or nested.get("fallback_reason")
    )
    error = execution.get("error") or nested.get("error")
    if isinstance(error, Mapping):
        reason = reason or error.get("code")
        message = execution.get("message") or nested.get("message") or error.get("message")
    else:
        message = execution.get("message") or nested.get("message") or error or metadata.get("warning")
    if isinstance(message, Mapping):
        message = message.get("message") or message.get("code")
    reason_key = str(reason or "").lower()
    if raw == "degraded":
        if reason_key in {"missing_input", "invalid_input", "input_conflict", "input_out_of_range", "cannot_get_ph"}:
            raw = "rejected"
        elif reason_key in {"model_unavailable", "model_file_missing", "sklearn_missing", "not_ready", "import_failed", "diagnosis_not_ready", "stability_not_ready", "acidification_not_ready"}:
            raw = "unavailable"
        elif reason_key in {"exception", "unexpected_error"}:
            raw = "error"
    if raw == "degraded":
        issues.append(_issue(
            str(reason or "DEGRADED_RESULT").upper(), "warning",
            str(message or "使用替代数据源或部分结果。"),
        ))
    elif raw == "rejected":
        issues.append(_issue(str(reason or "INVALID_INPUT").upper(), "error", str(message or "输入不满足模型约束。")))
    elif raw == "unavailable":
        issues.append(_issue(str(reason or "MODEL_UNAVAILABLE").upper(), "error", str(message or "模型能力当前不可用。")))
    elif raw == "error":
        issues.append(_issue("MODEL_EXECUTION_ERROR", "error", "模型执行失败。"))
    return raw, issues


def _normalize_result(agent_key: str, raw: Any, payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return None
    source = dict(raw)
    # execute() 有时把业务结果嵌套在 result.result 中。各 Agent 的外层
    # 还可能带有 status/metadata 等运行字段，这些字段不属于业务 result。
    nested = source.get("result")
    if isinstance(nested, Mapping):
        outer = {
            key: value for key, value in source.items()
            if key not in {"result", "metadata", "status", "data_source", "simulated", "persisted"}
        }
        source = {**outer, **dict(nested)}

    def first_present(*keys: str) -> Any:
        for key in keys:
            if key in source and source[key] is not None:
                return source[key]
        return None

    if agent_key == "model-1":
        modules = source.get("stability_modules") or source.get("modules")
        if modules is None and isinstance(source.get("all_results"), Mapping):
            modules = source.get("all_results")
        if modules is None:
            modules = {k: v for k, v in source.items() if str(k).startswith("module_")}
        if isinstance(modules, Mapping):
            modules = {k: v for k, v in modules.items() if k != "all_results"}
        return {
            "region": first_present("region") if "region" in source else payload.get("area_code"),
            "score": first_present("score", "stability_score", "composite_index"),
            "grade": first_present("grade", "quality_grade", "risk_level"),
            "modules": modules or {},
        }
    if agent_key == "model-2":
        return {
            "quality_grade": first_present("quality_grade", "grade"),
            "composite_index": first_present("composite_index", "quality_index"),
            "indicators": first_present("indicators") if "indicators" in source else [],
            "obstacle_degree": first_present("obstacle_degree", "memberships") if first_present("obstacle_degree", "memberships") is not None else [],
        }
    if agent_key == "model-3":
        diagnosis = source.get("diagnosis") if isinstance(source.get("diagnosis"), Mapping) else source
        evaluation = source.get("evaluation") if isinstance(source.get("evaluation"), Mapping) else {}
        def diagnosis_value(*keys: str) -> Any:
            for key in keys:
                if key in diagnosis and diagnosis[key] is not None:
                    return diagnosis[key]
            return None

        primary = diagnosis_value("primary_factors", "ZYZAYS", "main_factors") or []
        secondary = diagnosis_value("secondary_factors", "CYZAYS") or []
        split = lambda value: [x for x in str(value).replace("；", ";").split(";") if x and x != "无"] if isinstance(value, str) else (value or [])
        return {
            "obstacle_type": diagnosis_value("obstacle_type", "ZALX"),
            "primary_factors": split(primary),
            "secondary_factors": split(secondary),
            "obstacle_degrees": diagnosis_value("obstacle_degrees") or evaluation.get("obstacle_degree") or [],
            "obstacle_levels": diagnosis_value("obstacle_levels") or evaluation.get("obstacle_levels") or [],
            "obstacle_combination": diagnosis_value("obstacle_combination") if "obstacle_combination" in diagnosis else evaluation.get("obstacle_combination"),
        }
    if agent_key == "model-4":
        metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
        return {
            "acidification_level": first_present("acidification_level", "level"),
            "background_acid": first_present("background_acid", "Aback"),
            "acid_deposition_input": first_present("acid_deposition_input", "Adep"),
            "crop_acid_output": first_present("crop_acid_output", "Acrop"),
            "nitrogen_cycle_acid": first_present("nitrogen_cycle_acid", "ANcy"),
            "agricultural_acid": first_present("agricultural_acid", "Aagri"),
            "soil_conditioner_dosage": _first_value(source, "soil_conditioner_dosage", "ytk", "YTK"),
            "woody_peat_dosage": _first_value(source, "woody_peat_dosage", "mbnt", "MBNT"),
            "sub_model": first_present("sub_model") if "sub_model" in source else metadata.get("sub_model"),
        }
    if agent_key == "model-5":
        dose = first_present("dose_prediction", "dose", "manure_dosage", "organic_fertilizer_dosage")
        return {
            "organic_matter": first_present("organic_matter", "SOMbe", "SOCbe", "YJZ"),
            "level": first_present("level"),
            "soc_prediction": first_present("soc_prediction"),
            "dose_prediction": dose,
            "dose": dose,
            "manure_dosage": dose,
            "potential_increase": first_present("potential_increase"),
            "soc_confidence": first_present("soc_confidence"),
            "dose_confidence": first_present("dose_confidence"),
            "region": first_present("region") if "region" in source else payload.get("area_code"),
            "land_type": first_present("land_type") if "land_type" in source else payload.get("land_type"),
            "imputed_features": first_present("imputed_features") if "imputed_features" in source else [],
        }
    return {k: v for k, v in source.items() if k not in {"parcel_id", "metadata", "data_source", "simulated", "persisted"}}


def _first_value(source: Mapping[str, Any], *keys: str) -> Any:
    """从多个历史字段名中取第一个存在的值。"""
    nested = source.get("result") if isinstance(source.get("result"), Mapping) else {}
    for key in keys:
        if source.get(key) is not None:
            return source[key]
        if nested.get(key) is not None:
            return nested[key]
    return None


def normalize_execution(agent: Any, payload: Optional[Mapping[str, Any]], execution: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """将现有 execute/tool_result 转换为规范模型结果信封。"""
    payload = payload or {}
    execution = execution or {}
    model_id = _canonical_model_id(agent)
    agent_key = _agent_id(agent)
    metadata = execution.get("metadata") if isinstance(execution.get("metadata"), Mapping) else {}
    source = str(execution.get("data_source") or metadata.get("data_source") or "unknown")
    simulated = bool(execution.get("simulated", metadata.get("simulated", False)))
    raw_result = execution.get("result") if isinstance(execution.get("result"), Mapping) else {}
    nested_metadata = raw_result.get("metadata") if isinstance(raw_result.get("metadata"), Mapping) else {}
    model_version = (
        execution.get("model_version")
        or metadata.get("model_version")
        or raw_result.get("model_version")
        or nested_metadata.get("model_version")
    )

    if agent_key == "model-6" or model_id == "comprehensive-fertility-improvement":
        status = "unavailable"
        issues = [_issue("MODEL_NOT_IMPLEMENTED", "error", "综合地力改良提升模型尚未实现。")]
        result = None
        simulated = True
        source = "stub"
    else:
        status, issues = _status_and_issue(execution, simulated, source)
        raw_result = execution.get("result")
        result = _normalize_result(agent_key, raw_result, payload)
        if agent_key == "model-5" and isinstance(result, Mapping):
            result = dict(result)
            is_real_source = source in MODEL5_REAL_SOURCES
            has_real_version = bool(model_version and str(model_version).strip().lower() != "unknown")
            quantitative_available = status == "ok" and not simulated and is_real_source and has_real_version
            if quantitative_available:
                required_prediction_fields = (
                    ("dose_prediction",)
                    if source == "rf_model"
                    else (
                        "soc_prediction", "dose_prediction",
                        "soc_confidence", "dose_confidence",
                    )
                )
                missing = [key for key in required_prediction_fields if result.get(key) is None]
                if missing:
                    status = "degraded"
                    quantitative_available = False
                    issues.append(_issue(
                        "PARTIAL_PREDICTION", "warning",
                        "真实模型仅返回部分必要预测结果。", details={"missing_fields": missing},
                    ))
            if not quantitative_available:
                for key in ("soc_prediction", "dose_prediction", "dose", "manure_dosage", "potential_increase"):
                    result[key] = None
                if status == "ok":
                    status = "degraded"
                simulated = True
                if source == "unknown":
                    source = "unavailable"
                issues.append(_issue(
                    MODEL5_QUANTITATIVE_UNAVAILABLE,
                    "warning",
                    "缺少可验证的真实模型来源，Model-5 定量结果不可用。",
                ))
            else:
                # 当前没有经验证的 potential_increase 预测模型。
                result["potential_increase"] = None
        if status == "ok" and result is None:
            status = "degraded"
            issues.append(_issue("MISSING_RESULT", "warning", "模型未返回可用的结构化业务结果。"))
        if status in {"rejected", "unavailable", "error"}:
            result = None

    envelope: Dict[str, Any] = {
        "model_id": model_id,
        "status": status,
        "subject": _subject(payload, execution, model_id),
        "result": result,
        "meta": {
            "data_source": source,
            "simulated": simulated,
            "model_version": model_version,
        },
        "issues": issues,
    }
    extra_issues: List[Dict[str, Any]] = []
    envelope["result"] = sanitize_json(envelope["result"], extra_issues, "result")
    envelope["meta"] = sanitize_json(envelope["meta"], extra_issues, "meta")
    # 相同 issue 只保留一份。
    seen = set()
    envelope["issues"] = [item for item in envelope["issues"] + extra_issues if not ((item.get("code"), item.get("field")) in seen or seen.add((item.get("code"), item.get("field"))))]
    return envelope


def public_full(model_result: Mapping[str, Any]) -> Dict[str, Any]:
    """专题模型 API 的完整规范投影。"""
    return sanitize_json(deepcopy(dict(model_result)))


def chat_compact(model_result: Mapping[str, Any]) -> Dict[str, Any]:
    """聊天显式请求时返回的精简模型投影。"""
    result = model_result.get("result")
    if not isinstance(result, Mapping):
        compact_result = None
    else:
        compact_result = dict(result)
        if isinstance(compact_result.get("modules"), Mapping):
            compact_result["modules"] = {
                key: value for key, value in compact_result["modules"].items()
                if key in {"score", "grade", "risk_level", "退化风险等级", "稳定性得分"}
            }
    return sanitize_json({
        "model_id": model_result.get("model_id"),
        "status": model_result.get("status"),
        "subject": model_result.get("subject"),
        "result": compact_result,
        "meta": model_result.get("meta"),
        "issues": model_result.get("issues", []),
    })


def llm_context(model_result: Mapping[str, Any]) -> Dict[str, Any]:
    """最终总结 LLM 使用的紧凑上下文。"""
    result = model_result.get("result")
    key_result: Dict[str, Any] = {}
    if isinstance(result, Mapping):
        for key in (
            "region", "score", "grade", "quality_grade", "composite_index", "obstacle_type",
            "primary_factors", "secondary_factors", "acidification_level", "soil_conditioner_dosage",
            "woody_peat_dosage", "soc_prediction", "dose_prediction", "soc_confidence", "dose_confidence",
        ):
            if key in result:
                key_result[key] = result[key]
    return sanitize_json({
        "model_id": model_result.get("model_id"),
        "status": model_result.get("status"),
        "result": key_result or None,
        "issues": model_result.get("issues", []),
    })


def audit_projection(model_result: Mapping[str, Any], inputs: Optional[Mapping[str, Any]] = None, diagnostics: Optional[Any] = None) -> Dict[str, Any]:
    """审计投影，供日志/trace 使用，不应直接返回 HTTP。"""
    return sanitize_json({
        "inputs": deepcopy(dict(inputs or {})),
        "result": deepcopy(dict(model_result)),
        "diagnostics": deepcopy(diagnostics),
    })


def legacy_projection(model_result: Mapping[str, Any]) -> Dict[str, Any]:
    """从规范结果单向生成兼容期 Schema 1.0 展示结构。"""
    model_id = model_result.get("model_id")
    result = deepcopy(model_result.get("result"))
    meta = model_result.get("meta") if isinstance(model_result.get("meta"), Mapping) else {}
    issues = model_result.get("issues", [])
    findings = []
    if isinstance(result, Mapping):
        findings = [
            {"title": str(key), "content": str(value)}
            for key, value in result.items()
            if value is not None and key != "modules"
        ]
    legacy = {
        "status": "ok" if model_result.get("status") in {"ok", "degraded"} else model_result.get("status"),
        "model": {"model_id": model_id},
        "capability": {"model_id": model_id},
        "summary": deterministic_answer(model_result),
        "findings": findings,
        "recommendations": [],
        "evidence": result,
        "analysis": result,
        "data_source": meta.get("data_source"),
        "simulated": meta.get("simulated", False),
        "degraded": model_result.get("status") == "degraded",
        "reliability": {
            "level": "real_model" if model_result.get("status") == "ok" else model_result.get("status"),
            "message": issues[0].get("message") if issues else "结果可用。",
        },
        "fallback": {
            "used": model_result.get("status") == "degraded",
            "fields": [],
            "strategy": issues[0].get("code") if issues else "未使用回退",
        },
    }
    if model_id == "organic-matter-improvement":
        legacy["deprecation"] = {
            "code": MODEL5_QUANTITATIVE_UNAVAILABLE,
            "message": "旧规则施用量和提升量已停止提供；客户端必须接受 null，且不得本地回填。",
        }
    return sanitize_json(legacy)


def deterministic_answer(model_result: Mapping[str, Any]) -> str:
    """不依赖 LLM 的确定性摘要。"""
    status = model_result.get("status")
    if status == "unavailable":
        return "当前模型能力暂不可用，请稍后重试或检查运行依赖。"
    if status == "rejected":
        return "当前输入不满足模型计算条件，请补充或修正必要参数。"
    if status == "error":
        return "模型执行失败，暂时无法返回结果。"
    result = model_result.get("result")
    if not isinstance(result, Mapping):
        return "当前没有可用的结构化模型结果。"
    parts: List[str] = []
    labels = {
        "quality_grade": "质量等级", "composite_index": "综合指数", "grade": "等级",
        "score": "得分", "obstacle_type": "障碍类型", "acidification_level": "酸化程度",
        "soil_conditioner_dosage": "土壤调理剂用量", "woody_peat_dosage": "木本泥炭用量",
        "soc_prediction": "SOC预测", "dose_prediction": "培肥施用量",
    }
    for key, label in labels.items():
        if result.get(key) is not None:
            value = result[key]
            if isinstance(value, float):
                precision = 3 if key in {
                    "composite_index", "score", "soc_prediction",
                    "soc_confidence", "dose_confidence",
                } else 1
                value = f"{value:.{precision}f}".rstrip("0").rstrip(".")
            parts.append(f"{label}：{value}")
    if result.get("primary_factors"):
        parts.append(f"主要障碍因素：{result['primary_factors']}")
    return "；".join(parts) or "模型已完成分析，但没有可展示的关键指标。"


__all__ = [
    "SCHEMA_VERSION", "LEGACY_SCHEMA_VERSION", "VALID_STATUSES", "Issue", "sanitize_json", "validate_result",
    "normalize_execution", "public_full", "chat_compact", "llm_context", "audit_projection",
    "legacy_projection", "deterministic_answer",
]
