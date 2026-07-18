from __future__ import annotations
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ---- 模型文件路径（项目相对）----
# model_6.py 位于 framework/domain/other_models/model_6.py
# parents[0]=other_models, [1]=domain, [2]=framework, [3]=项目根
_MODELS_DIR = Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"
_SOC_MODEL_PATH = _MODELS_DIR / "soc_etr_model.joblib"
_SOC_META_PATH = _MODELS_DIR / "soc_metadata.json"
_DOSE_MODEL_PATH = _MODELS_DIR / "dose_etr_model.joblib"
_DOSE_META_PATH = _MODELS_DIR / "dose_metadata.json"

# ---- 尝试导入 sklearn / joblib ----
try:
    import joblib
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

logger.info("model_6 module imported, sklearn_available=%s", _SKLEARN_AVAILABLE)

# ---- 惰性单例状态 ----
_SOC_MODEL = None
_DOSE_MODEL = None
_SOC_META = None
_DOSE_META = None
_SOC_LOAD_FAILED = False
_DOSE_LOAD_FAILED = False
_LOAD_LOCK = threading.Lock()

_MODEL_VERSION = "ETR_v1_20260713"

# ---- 特征合法范围 ----
FEATURE_RANGES = {
    "pH":              (3.0,    11.0),
    "SOCbe":           (0.0,    100.0),
    "TN":              (0.0,    10.0),
    "TP":              (0.0,    10.0),
    "TK":              (0.0,    100.0),
    "AP":              (0.0,    200.0),
    "AK":              (0.0,    500.0),
    "Gap":             (-10.0,  50.0),
    "Dose":            (0.0,    1000.0),
    "Fertilizer type": (1,      2),
}


def _prepare_features(
    input_data: Dict[str, Any],
    feature_names: List[str],
    feature_means: Dict[str, float],
) -> Tuple[pd.DataFrame, List[str], List[Dict[str, Any]]]:
    """准备特征 DataFrame，返回 (df, imputed_list, out_of_range_list)。

    - input_data 的 key 做 strip() 规范化（兼容 "TN " / "TN"）
    - 缺失/转换失败的字段用 feature_means 填充，加入 imputed_list
    - 越界字段加入 out_of_range_list，同时用均值填充
    """
    normalized = {
        k.strip(): v for k, v in (input_data or {}).items() if v is not None
    }
    row: Dict[str, Any] = {}
    imputed: List[str] = []
    out_of_range: List[Dict[str, Any]] = []

    for fname in feature_names:
        fname_stripped = fname.strip()
        if fname_stripped in normalized:
            try:
                value = float(normalized[fname_stripped])
                lo, hi = FEATURE_RANGES.get(fname_stripped, (None, None))
                if lo is not None and (value < lo or value > hi):
                    out_of_range.append({
                        "feature": fname,
                        "value": value,
                        "valid_range": [lo, hi],
                    })
                    row[fname] = feature_means[fname]
                    imputed.append(fname)
                else:
                    row[fname] = value
                continue
            except (ValueError, TypeError):
                pass
        row[fname] = feature_means[fname]
        imputed.append(fname)

    return pd.DataFrame([row], columns=feature_names), imputed, out_of_range


def _load_model_and_meta(model_path: Path, meta_path: Path):
    """加载 .joblib 模型与 metadata.json"""
    model = joblib.load(model_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return model, meta


def _ensure_models_loaded() -> bool:
    """惰性加载模型，double-checked locking 保证线程安全。返回是否加载成功。"""
    global _SOC_MODEL, _DOSE_MODEL, _SOC_META, _DOSE_META
    global _SOC_LOAD_FAILED, _DOSE_LOAD_FAILED

    if _SOC_LOAD_FAILED or _DOSE_LOAD_FAILED:
        return False

    if _SOC_MODEL is None and not _SOC_LOAD_FAILED:
        with _LOAD_LOCK:
            if _SOC_MODEL is None and not _SOC_LOAD_FAILED:
                try:
                    _SOC_MODEL, _SOC_META = _load_model_and_meta(
                        _SOC_MODEL_PATH, _SOC_META_PATH
                    )
                    logger.info(
                        "SOC model loaded, feature_names=%s, test_r2=%.4f",
                        _SOC_META["feature_names"],
                        _SOC_META["metrics"]["test_r2"],
                    )
                except Exception:
                    _SOC_LOAD_FAILED = True
                    logger.exception("Failed to load SOC model")

    if _DOSE_MODEL is None and not _DOSE_LOAD_FAILED:
        with _LOAD_LOCK:
            if _DOSE_MODEL is None and not _DOSE_LOAD_FAILED:
                try:
                    _DOSE_MODEL, _DOSE_META = _load_model_and_meta(
                        _DOSE_MODEL_PATH, _DOSE_META_PATH
                    )
                    logger.info(
                        "Dose model loaded, feature_names=%s, test_r2=%.4f",
                        _DOSE_META["feature_names"],
                        _DOSE_META["metrics"]["test_r2"],
                    )
                except Exception:
                    _DOSE_LOAD_FAILED = True
                    logger.exception("Failed to load Dose model")

    if _SOC_LOAD_FAILED or _DOSE_LOAD_FAILED:
        return False
    return True


def _fallback_response(input_data: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """构造 fallback 响应，使用训练集均值作为粗估。"""
    return {
        "status": "fallback",
        "soc_prediction": _SOC_META["feature_means"].get("SOCbe", 12.0) if _SOC_META else 12.0,
        "soc_confidence": 0.3,
        "dose_prediction": _DOSE_META["feature_means"].get("Dose", 100.0) if _DOSE_META else 100.0,
        "dose_confidence": 0.3,
        "dose_warning": "模型不可用，返回训练集均值估算" if reason != "input_out_of_range" else "输入值越界，未执行预测",
        "imputed_features": [],
        "imputation_applied": False,
        "model_version": _MODEL_VERSION,
        "fallback_reason": reason,
    }


def model_6_execution(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """SOC + Dose ML 预测主入口。

    输入：特征字典（key 可含/不含尾随空格，可缺字段）
    输出：预测结果字典，含 status/soc_prediction/dose_prediction 等字段
    """
    try:
        # 1. 检查 sklearn 可用性
        if not _SKLEARN_AVAILABLE:
            return _fallback_response(input_data or {}, reason="sklearn_missing")

        # 2. 检查模型加载状态（首次触发加载）
        if not _ensure_models_loaded():
            return _fallback_response(input_data or {}, reason="model_file_missing")

        # 3. 准备 SOC 特征（10 因子）
        soc_df, soc_imputed, soc_oor = _prepare_features(
            input_data or {}, _SOC_META["feature_names"], _SOC_META["feature_means"]
        )

        # 4. 准备 Dose 特征（9 因子，去掉 Dose 自身）
        dose_input = {
            k: v for k, v in (input_data or {}).items() if k.strip() != "Dose"
        }
        dose_df, dose_imputed, dose_oor = _prepare_features(
            dose_input, _DOSE_META["feature_names"], _DOSE_META["feature_means"]
        )

        # 5. 范围校验：任一越界即拒绝
        all_oor = soc_oor + dose_oor
        if all_oor:
            return {
                "status": "rejected",
                "reason": "input_out_of_range",
                "out_of_range_features": all_oor,
                "soc_prediction": None,
                "soc_confidence": 0.0,
                "dose_prediction": None,
                "dose_confidence": 0.0,
                "dose_warning": "输入值越界，未执行预测",
                "imputed_features": [],
                "imputation_applied": False,
                "model_version": _MODEL_VERSION,
            }

        # 6. 执行预测
        soc_pred = float(_SOC_MODEL.predict(soc_df)[0])
        dose_pred = float(_DOSE_MODEL.predict(dose_df)[0])

        logger.info(
            "model_6_execution success: SOC=%.4f, Dose=%.4f", soc_pred, dose_pred
        )

        # 7. 构造响应
        return {
            "status": "success",
            "soc_prediction": round(soc_pred, 4),
            "soc_confidence": round(_SOC_META["metrics"]["test_r2"], 2),
            "dose_prediction": round(dose_pred, 4),
            "dose_confidence": round(_DOSE_META["metrics"]["test_r2"], 2),
            "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准",
            "imputed_features": sorted(set(soc_imputed + dose_imputed)),
            "imputation_applied": bool(soc_imputed or dose_imputed),
            "model_version": _MODEL_VERSION,
        }

    except Exception as e:
        logger.exception(f"model_6_execution unexpected error: {e}")
        return _fallback_response(input_data or {}, reason="unexpected_error")
