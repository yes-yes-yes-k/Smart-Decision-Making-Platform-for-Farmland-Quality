from __future__ import annotations
from typing import Any, Dict, Optional

try:
    from ai_culti_demo.farmland_diagnosis.acidification import calculate_acidification_amendment
    _ACID_AVAILABLE = True
except ImportError:
    _ACID_AVAILABLE = False


def _query_sjd_by_parcel_id(parcel_id: str, db_path: str = None) -> Optional[float]:
    """从 evaluation_results 表查 SJD；查无返回 None。"""
    try:
        from ai_culti_demo.farmland_diagnosis.storage import DiagnosisStorage
        storage = DiagnosisStorage(db_path)
        ev = storage.get_evaluation(parcel_id)
        if ev is None:
            return None
        sjd = ev.get("SJD")
        return float(sjd) if sjd is not None else None
    except Exception:
        return None


def model_4_execution(
    input_data: Dict[str, Any],
    land_type: Optional[str] = None,
    fertilizer_type: Optional[str] = None,
) -> Dict[str, Any]:
    """model-4 酸化改良模型入口。"""
    data = input_data or {}
    lt = land_type or data.get("land_type") or "upland"
    ft = fertilizer_type or data.get("fertilizer_type") or "compound"

    if not _ACID_AVAILABLE:
        return {"status": "rejected", "reason": "model_unavailable",
                "ytk": None, "mbnt": None, "land_type": lt, "fertilizer_type": ft,
                "model_version": "process_v2_20260801", "customized_params": {}}

    # 提取 pHstart：优先 SJD，缺则用 parcel_id 查 DB
    sjd = data.get("SJD")
    if sjd is None:
        parcel_id = data.get("parcel_id")
        if parcel_id is not None:
            sjd = _query_sjd_by_parcel_id(str(parcel_id), data.get("db_path"))
            if sjd is None:
                return {"status": "rejected", "reason": "cannot_get_ph",
                        "ytk": None, "mbnt": None, "land_type": lt, "fertilizer_type": ft,
                        "model_version": "process_v2_20260801", "customized_params": {},
                        "warning": "无法从 DB 获取 SJD，请提供 SJD"}
        else:
            sjd = None

    hex_val = data.get("JHX")
    alex_val = data.get("JLA")

    # 可配参数透传
    optional = {}
    for k in ("RPH", "R", "Y", "S", "FertN", "Ndep", "pHtarget"):
        if k in data and data[k] is not None:
            optional[k] = data[k]

    res = calculate_acidification_amendment(
        sjd, hex_val, alex_val,
        land_type=lt, fertilizer_type=ft, **optional,
    )
    # 标准化返回结构
    out = {
        "status": res["status"],
        "ytk": res.get("ytk"),
        "mbnt": res.get("mbnt"),
        "land_type": res.get("land_type", lt),
        "fertilizer_type": res.get("fertilizer_type", ft),
        "model_version": res.get("model_version", "process_v2_20260801"),
        "customized_params": res.get("customized_params", {}),
    }
    if "sub_model" in res:
        out["sub_model"] = res["sub_model"]
    if "warning" in res:
        out["warning"] = res["warning"]
    if "reason" in res:
        out["reason"] = res["reason"]
    if "out_of_range_features" in res:
        out["out_of_range_features"] = res["out_of_range_features"]
    return out
