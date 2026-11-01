"""报告上下文聚合器。

按范围（地块/区域）读取 parcel_info 指标，复用/补算 model-4（酸化改良用量）
与 model-5（有机质培肥用量）治理用量结果，并对区域范围做聚合统计，
产出结构化 ReportContext 供报告生成器消费。

设计依据：openspec/changes/data-driven-report-generation/design.md（D2/D3/D4）。
"""
from __future__ import annotations

import logging
import math
from contextlib import contextmanager
from datetime import datetime
from statistics import mean
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 区域范围采样阈值：超阈值且需大量补算时采样，避免全量重算。可由环境变量覆盖。
import os
try:
    REGION_SAMPLE_THRESHOLD = int(os.environ.get("REPORT_REGION_SAMPLE_THRESHOLD", "50"))
except ValueError:
    REGION_SAMPLE_THRESHOLD = 50

# 报告类型 → 治理用量模型子集（D3）
# 仅开放两个治理类报告；另两类方案报告前端拦截，聚合层亦拒绝。
REPORT_TYPE_TO_AGENT: dict[str, str] = {
    "acidification_treatment": "model-4",
    "organic_matter_improvement": "model-5",
}
UNSUPPORTED_REPORT_TYPES = {"farmland_protection_upgrade", "supplementary_farmland"}


class ReportContextError(Exception):
    """聚合失败异常，携带错误码。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# 应用上下文
# ---------------------------------------------------------------------------

_app_cache: Any = None


def _get_app():
    """延迟获取 Flask app（与 ParcelDataAccessor 一致）。"""
    global _app_cache
    if _app_cache is None:
        try:
            from framework.api.app import create_app
            _app_cache = create_app("default")
        except Exception as e:
            logger.warning("创建 Flask app 失败: %s", e)
            _app_cache = False
    return _app_cache or None


@contextmanager
def _app_ctx():
    """若已在应用上下文则直接复用，否则创建并 push 一个。"""
    try:
        from flask import current_app
        current_app._get_current_object()
        yield
        return
    except Exception:
        pass
    app = _get_app()
    if app is None:
        raise RuntimeError("Flask app 不可用，无法查询数据库")
    with app.app_context():
        yield


# ---------------------------------------------------------------------------
# 1. 范围模型
# ---------------------------------------------------------------------------

def normalize_scope(scope: Any, area_code: Any = None) -> dict[str, str]:
    """归一化范围为 {"type", "id"}。

    缺省 scope 时把 area_code 等价为 {"type":"region","id":area_code}。
    """
    if isinstance(scope, dict) and scope.get("type") and scope.get("id"):
        return {"type": str(scope["type"]), "id": str(scope["id"])}
    if area_code:
        return {"type": "region", "id": str(area_code)}
    raise ReportContextError("MISSING_PARAMS", "scope 与 area_code 至少其一存在")


# 中文名 → 行政区划编码映射（GB/T 2260）
# 县级：精确匹配 6 位 area_code；市级：4 位前缀用于 LIKE 查询
AREA_NAME_TO_CODE: dict[str, str] = {
    # 韶关市（440200）下辖区县
    "浈江区": "440202", "武江区": "440203", "曲江区": "440204",
    "乐昌市": "440281", "南雄市": "440282", "始兴县": "440222",
    "仁化县": "440224", "翁源县": "440223", "新丰县": "440233",
    "乳源瑶族自治县": "440232",
}

# 市级 → 4 位前缀（取 area_code 前 4 位做 LIKE 查询，覆盖市下所有区县）
CITY_TO_CODE_PREFIX: dict[str, str] = {
    "韶关市": "4402",
}


def _resolve_area_code(area_id: str) -> str:
    """把区域标识归一化为数据库 area_code。

    纯数字直接返回（已是编码）；中文县名查 AREA_NAME_TO_CODE；
    市名查 CITY_TO_CODE_PREFIX 返回前缀（调用方需按前缀 LIKE 查询）。
    无法映射时原样返回，交由查询层兜底。
    """
    if area_id.isdigit():
        return area_id
    if area_id in AREA_NAME_TO_CODE:
        return AREA_NAME_TO_CODE[area_id]
    if area_id in CITY_TO_CODE_PREFIX:
        return CITY_TO_CODE_PREFIX[area_id]
    return area_id


def resolve_parcel_ids(scope: dict[str, str]) -> list[str]:
    """解析范围为地块编号列表。parcel 返回单元素；region 查 area_code 下全部地块。

    支持中文名（县/市名）与数字编码两种 area_code 输入：
    - 县名/编码：精确匹配
    - 市名：按前缀 LIKE 查询，覆盖市下所有区县
    """
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
    accessor = ParcelDataAccessor()
    if scope["type"] == "parcel":
        return [scope["id"]]
    if scope["type"] == "region":
        area_id = scope["id"]
        resolved = _resolve_area_code(area_id)
        # 市级前缀（4 位）→ LIKE 查询
        if resolved in CITY_TO_CODE_PREFIX.values():
            return accessor.get_parcel_ids_by_area_prefix(resolved)
        # 县级编码或原名 → 精确查询
        return accessor.get_parcel_ids_by_area_code(resolved)
    raise ReportContextError("UNKNOWN_SCOPE_TYPE", f"未知范围类型: {scope['type']}")


# ---------------------------------------------------------------------------
# 2. 指标加载
# ---------------------------------------------------------------------------

def load_indicators(parcel_ids: list[str]) -> tuple[list[dict], list[str]]:
    """经 ParcelDataAccessor 读取地块指标与元信息。

    缺失地块记入 missing 并跳过，不影响整体流程。
    返回 (indicators_snapshot, missing)。
    """
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
    accessor = ParcelDataAccessor()
    snapshot: list[dict] = []
    missing: list[str] = []
    for pid in parcel_ids:
        record = accessor.get_parcel_record(pid)
        if record is None or not record.get("soil_indicators"):
            missing.append(pid)
            continue
        snapshot.append(record)
    return snapshot, missing


# ---------------------------------------------------------------------------
# 3. 治理用量计算/复用（D4：先读库后补算）
# ---------------------------------------------------------------------------

def _read_model4_from_db(parcel_id: str) -> Optional[dict]:
    """从 AcidificationRemediationResult 读最新一条 model-4 结果。

    关键字段（soil_conditioner_dosage/woody_peat_dosage/soil_ph）为空或占位值
    时视为无效记录，返回 None 触发补算。
    """
    try:
        from framework.models.thematic_model import AcidificationRemediationResult
        with _app_ctx():
            row = (
                AcidificationRemediationResult.query
                .filter_by(parcel_id=parcel_id)
                .order_by(AcidificationRemediationResult.created_at.desc())
                .first()
            )
            if row is None:
                return None
            result = {
                "parcel_id": parcel_id,
                "soil_ph": row.soil_ph,
                "exchangeable_hydrogen": row.exchangeable_hydrogen,
                "exchangeable_aluminum": row.exchangeable_aluminum,
                "target_ph": row.target_ph,
                "soil_conditioner_dosage": row.soil_conditioner_dosage,  # 亿土康
                "woody_peat_dosage": row.woody_peat_dosage,              # 木本泥炭
                "model_version": row.model_version,
                "source": "db",
            }
            # 关键字段为空/占位值 → 视为无效记录，触发补算
            # 判定规则：
            #   - soil_conditioner_dosage 为空或 <= 0
            #   - woody_peat_dosage 为空或 <= 0
            #   - soil_ph 为空或 <= 0（pH 不可能为 0）
            # 三者同时满足才视为无效（任一字段有真实值仍复用）
            def _empty_or_le0(val):
                if val is None:
                    return True
                if isinstance(val, (int, float)) and float(val) <= 0:
                    return True
                return False

            sc_empty = _empty_or_le0(result["soil_conditioner_dosage"])
            wp_empty = _empty_or_le0(result["woody_peat_dosage"])
            ph_empty = _empty_or_le0(result["soil_ph"])
            if sc_empty and wp_empty and ph_empty:
                logger.info(
                    "model-4 记录关键字段全空 (parcel_id=%s, sc=%s, wp=%s, ph=%s)，触发补算降级",
                    parcel_id, result["soil_conditioner_dosage"],
                    result["woody_peat_dosage"], result["soil_ph"],
                )
                return None
            return result
    except Exception as e:
        logger.warning("读 model-4 结果失败 (parcel_id=%s): %s", parcel_id, e)
        return None


def _compute_model4(record: dict) -> Optional[dict]:
    """现场补算 model-4：经 _map_indicators_to_inputs 取 SJD/Hex/Alex 后调 calculate_acidification。

    返回 YTK（石灰施用量）与 MBNT（有机肥施用量），不落库。
    输入包含回填或默认取值时，用量置空并返回 imputed_inputs（与统一输出契约的 Model-4 规则一致）。
    """
    try:
        from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
        from framework.domain.calculations.acidification_calculation import calculate_acidification
        from framework.domain.provenance import (
            MODEL4_CONTEXT_INPUTS,
            MODEL4_INPUT_SOURCES,
            imputed_fields,
        )
        accessor = ParcelDataAccessor()
        indicators = record["soil_indicators"]
        mapped = accessor._map_indicators_to_inputs(indicators, "model-4")
        sjd = mapped.get("SJD")
        hex_ = mapped.get("Hex")
        alex = mapped.get("Alex")
        if sjd is None or hex_ is None or alex is None:
            return None
        land_type = record.get("land_type") or "upland"
        fertilizer_type = record.get("fertilizer_type") or "urea"
        target_ph = record.get("target_ph")
        out = calculate_acidification(
            SJD=float(sjd), Hex=float(hex_), Alex=float(alex),
            land_type=land_type, fertilizer_type=fertilizer_type,
            pHtarget=float(target_ph) if target_ph is not None else None,
        )
        imputed_inputs = imputed_fields(
            indicators, (*MODEL4_INPUT_SOURCES.values(), *MODEL4_CONTEXT_INPUTS)
        )
        dosage_available = not imputed_inputs
        return {
            "parcel_id": record["parcel_id"],
            "soil_ph": sjd,
            "exchangeable_hydrogen": hex_,
            "exchangeable_aluminum": alex,
            "target_ph": target_ph,
            "lime_dosage": out.get("YTK") if dosage_available else None,          # 石灰施用量
            "organic_fertilizer_dosage": out.get("MBNT") if dosage_available else None,  # 有机肥施用量
            "imputed_inputs": imputed_inputs,
            "model_version": "process_v2_compute",
            "source": "computed",
        }
    except Exception as e:
        logger.warning("补算 model-4 失败 (parcel_id=%s): %s", record.get("parcel_id"), e)
        return None


def _compute_model5_for_parcel(record: dict) -> Optional[dict]:
    """现场补算 model-5 单地块用量：predict_dose。

    返回 organic_fertilizer_dosage/level 等，不落库。
    输入含回填字段时用量置空并返回 imputed_features（与统一输出契约的 Model-5 规则一致）。
    """
    try:
        from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
        from framework.domain.calculations.organic_matter_calculation import predict_dose
        from framework.domain.provenance import provenance_map
        accessor = ParcelDataAccessor()
        indicators = record["soil_indicators"]
        mapped = accessor._map_indicators_to_inputs(indicators, "model-5")
        land_type = record.get("land_type") or "upland"
        prediction = predict_dose(mapped, land_type, provenance=provenance_map(indicators))
        imputed_features = list(prediction.imputed_features)
        som = mapped.get("SOMbe")
        level = _som_level(som)
        return {
            "parcel_id": record["parcel_id"],
            "organic_matter": som,
            "soil_ph": mapped.get("pH"),
            "organic_fertilizer_dosage": prediction.dose if not imputed_features else None,
            "imputed_features": imputed_features,
            "level": level,
            "potential_increase": None,
            "simulated": prediction.simulated,
            "source": prediction.data_source,
            "model_version": prediction.model_version,
            "reason": prediction.reason,
        }
    except Exception as e:
        logger.warning("补算 model-5 失败 (parcel_id=%s): %s", record.get("parcel_id"), e)
        return None


def _som_level(som: Optional[float]) -> str:
    """有机质分级（与 OrganicMatterResult.level 语义一致）。"""
    if som is None:
        return "未知"
    if som < 10:
        return "极低"
    if som < 20:
        return "低"
    if som < 30:
        return "中"
    if som < 40:
        return "高"
    return "极高"


def _read_model5_latest() -> Optional[dict]:
    """读取最新的、可由执行日志证明为真实模型输出的 Model-5 记录。"""
    try:
        from framework.models.thematic_model import ModelExecutionLog, OrganicMatterResult
        with _app_ctx():
            rows = (
                OrganicMatterResult.query
                .order_by(OrganicMatterResult.created_at.desc())
                .all()
            )
            for row in rows:
                log = ModelExecutionLog.query.filter_by(id=row.execution_id).first()
                output = log.output_result if log and isinstance(log.output_result, dict) else {}
                meta = output.get("meta") if isinstance(output.get("meta"), dict) else {}
                source = str(meta.get("data_source") or "unknown")
                model_version = log.model_version if log else None
                trusted = (
                    row.simulated is False
                    and log is not None
                    and log.simulated is False
                    and str(log.status).lower() in {"ok", "success", "complete", "completed"}
                    and bool(model_version and str(model_version).strip().lower() != "unknown")
                    and source in {"shaoguan_rf", "global_etr", "rf_model"}
                )
                if not trusted or row.organic_fertilizer_dosage is None:
                    continue
                return {
                    "organic_fertilizer_type": row.organic_fertilizer_type,
                    "organic_fertilizer_dosage": row.organic_fertilizer_dosage,
                    "level": row.level,
                    "potential_increase": None,
                    "om_improvement_target": row.om_improvement_target,
                    "simulated": False,
                    "source": source,
                    "model_version": model_version,
                }
            return None
    except Exception as e:
        logger.warning("读 model-5 最新结果失败: %s", e)
        return None


# ---------------------------------------------------------------------------
# 4. 模型结果聚合（含区域采样）
# ---------------------------------------------------------------------------

def _sample_indices(n: int, threshold: int) -> list[int]:
    """从 n 个中均匀采样 threshold 个索引。"""
    if n <= threshold:
        return list(range(n))
    step = n / threshold
    return [min(int(i * step), n - 1) for i in range(threshold)]


def compute_model_results(
    agent_id: str,
    parcel_records: list[dict],
    scope: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """按 agent_id 聚合治理用量。返回 (model_results, sampling_info)。"""
    if agent_id == "model-4":
        return _aggregate_model4(parcel_records, scope)
    if agent_id == "model-5":
        return _aggregate_model5(parcel_records, scope)
    return {}, {}


def _aggregate_model4(parcel_records: list[dict], scope: dict[str, str]) -> tuple[dict, dict]:
    results: list[dict] = []
    db_hits = 0
    computed = 0
    failed = 0
    need_compute_idx = []
    # 第一遍：读库
    for i, rec in enumerate(parcel_records):
        pid = rec["parcel_id"]
        hit = _read_model4_from_db(pid)
        if hit is not None:
            results.append(hit)
            db_hits += 1
        else:
            need_compute_idx.append(i)
    # 采样：区域范围且需补算数量超阈值
    sampling_info: dict[str, Any] = {"applied": False, "total": len(parcel_records), "db_hits": db_hits}
    compute_idx = need_compute_idx
    if scope["type"] == "region" and len(need_compute_idx) > REGION_SAMPLE_THRESHOLD:
        compute_idx = _sample_indices(len(need_compute_idx), REGION_SAMPLE_THRESHOLD)
        compute_idx = [need_compute_idx[k] for k in compute_idx]
        sampling_info["applied"] = True
        sampling_info["sampled"] = len(compute_idx)
        sampling_info["need_compute"] = len(need_compute_idx)
        sampling_info["threshold"] = REGION_SAMPLE_THRESHOLD
    # 第二遍：补算（仅对采样后子集）
    for i in compute_idx:
        rec = parcel_records[i]
        out = _compute_model4(rec)
        if out is not None:
            results.append(out)
            computed += 1
        else:
            failed += 1
    sampling_info["computed"] = computed
    sampling_info["failed"] = failed
    return {"model-4": results}, sampling_info


def _aggregate_model5(parcel_records: list[dict], scope: dict[str, str]) -> tuple[dict, dict]:
    """优先复用可信真实记录，否则按范围调用当前 RF；失败时保留空定量结果。"""
    sampling_info: dict[str, Any] = {"applied": False, "total": len(parcel_records), "db_hits": 0}
    latest = _read_model5_latest()
    if latest is not None:
        sampling_info["db_hits"] = 1
        return {"model-5": latest}, sampling_info
    # 无落库结果，补算
    if not parcel_records:
        return {"model-5": None}, sampling_info
    if scope["type"] == "parcel":
        out = _compute_model5_for_parcel(parcel_records[0])
        sampling_info["computed"] = 1 if out else 0
        return {"model-5": out}, sampling_info
    # 区域范围：采样补算取均值
    n = len(parcel_records)
    idxs = list(range(n))
    if n > REGION_SAMPLE_THRESHOLD:
        idxs = _sample_indices(n, REGION_SAMPLE_THRESHOLD)
        sampling_info["applied"] = True
        sampling_info["sampled"] = len(idxs)
        sampling_info["threshold"] = REGION_SAMPLE_THRESHOLD
    doses: list[float] = []
    soms: list[float] = []
    versions: list[str] = []
    attempted = 0
    for i in idxs:
        out = _compute_model5_for_parcel(parcel_records[i])
        attempted += 1
        if out and out.get("organic_fertilizer_dosage") is not None:
            doses.append(float(out["organic_fertilizer_dosage"]))
        if out and out.get("organic_matter") is not None:
            soms.append(float(out["organic_matter"]))
        if out and out.get("model_version"):
            versions.append(str(out["model_version"]))
    sampling_info["computed"] = attempted
    if not doses and not soms:
        return {"model-5": None}, sampling_info
    avg_dose = mean(doses) if doses else None
    avg_som = mean(soms) if soms else None
    return {
        "model-5": {
            "organic_fertilizer_dosage": avg_dose,
            "potential_increase": None,
            "level": _som_level(avg_som),
            "organic_matter": avg_som,
            "source": "rf_model" if doses else "unavailable",
            "simulated": not bool(doses),
            "model_version": versions[0] if versions else None,
            "sample_count": len(doses) if doses else len(soms),
        }
    }, sampling_info


# ---------------------------------------------------------------------------
# 5. 区域聚合统计
# ---------------------------------------------------------------------------

def compute_region_stats(scope: dict[str, str], parcel_records: list[dict], model_results: dict) -> Optional[dict]:
    """仅 region 范围：对连续指标与治理用量算均值/最小/最大/分布。parcel 范围返回 None。"""
    if scope["type"] != "region" or not parcel_records:
        return None

    def _series(getter):
        vals = []
        for rec in parcel_records:
            v = getter(rec)
            if v is not None:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
        return vals

    stats: dict[str, Any] = {}
    # 指标
    ph_vals = _series(lambda r: r.get("soil_indicators", {}).get("soil_ph"))
    som_vals = _series(lambda r: r.get("soil_indicators", {}).get("organic_matter"))
    for name, vals in (("soil_ph", ph_vals), ("organic_matter", som_vals)):
        if vals:
            stats[name] = {"mean": round(mean(vals), 3), "min": round(min(vals), 3), "max": round(max(vals), 3), "count": len(vals)}
    # 治理用量
    m4 = model_results.get("model-4")
    if isinstance(m4, list):
        for key, label in (("lime_dosage", "lime_dosage"), ("soil_conditioner_dosage", "soil_conditioner_dosage"), ("woody_peat_dosage", "woody_peat_dosage"), ("organic_fertilizer_dosage", "m4_organic_fertilizer_dosage")):
            vals = [float(r[key]) for r in m4 if r.get(key) is not None]
            if vals:
                stats[label] = {"mean": round(mean(vals), 3), "min": round(min(vals), 3), "max": round(max(vals), 3), "count": len(vals)}
    m5 = model_results.get("model-5")
    if isinstance(m5, dict) and m5.get("organic_fertilizer_dosage") is not None:
        # model-5 区域级为单值，仍记录
        stats["m5_organic_fertilizer_dosage"] = {"mean": m5.get("organic_fertilizer_dosage"), "count": m5.get("sample_count", 1)}
    return stats or None


# ---------------------------------------------------------------------------
# 6. 串联
# ---------------------------------------------------------------------------

def build_report_context(
    report_type: str,
    scope: Any,
    area_code: Any = None,
) -> dict[str, Any]:
    """聚合报告上下文。失败抛 ReportContextError。"""
    # 校验报告类型（D3）
    if report_type in UNSUPPORTED_REPORT_TYPES:
        raise ReportContextError("UNSUPPORTED_REPORT_TYPE", f"暂不支持的报告类型: {report_type}")
    agent_id = REPORT_TYPE_TO_AGENT.get(report_type)
    if agent_id is None:
        raise ReportContextError("UNKNOWN_REPORT_TYPE", f"未知报告类型: {report_type}")

    # 归一化范围
    scope = normalize_scope(scope, area_code)

    # 解析地块
    parcel_ids = resolve_parcel_ids(scope)
    if not parcel_ids:
        raise ReportContextError("CONTEXT_UNAVAILABLE", f"范围内无地块: scope={scope}")

    # 加载指标
    parcel_records, missing = load_indicators(parcel_ids)
    if not parcel_records:
        raise ReportContextError("CONTEXT_UNAVAILABLE", f"范围内无可用地块指标: scope={scope}, missing={missing}")

    # 治理用量
    model_results, sampling_info = compute_model_results(agent_id, parcel_records, scope)

    # 区域统计
    region_stats = compute_region_stats(scope, parcel_records, model_results)

    # 溯源元信息
    versions: list[str] = []
    m4 = model_results.get("model-4")
    if isinstance(m4, list):
        versions.extend(r.get("model_version") for r in m4 if r.get("model_version"))
    m5 = model_results.get("model-5")
    if isinstance(m5, dict) and m5.get("model_version"):
        versions.append(m5["model_version"])
    source_meta = {
        "agent_id": agent_id,
        "model_versions": sorted(set(v for v in versions if v)),
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_source_table": "parcel_info",
        "total_parcels": len(parcel_ids),
        "missing_parcels": missing,
        "sampling": sampling_info,
        "scope": scope,
    }

    return {
        "scope": scope,
        "parcel_ids": parcel_ids,
        "indicators_snapshot": parcel_records,
        "model_results": model_results,
        "region_stats": region_stats,
        "source_meta": source_meta,
    }


def error_result(code: str, message: str) -> dict[str, Any]:
    """构造标准错误返回（与 generate_report 旧错误结构一致）。"""
    return {"status": "error", "error": {"code": code, "message": message}}
