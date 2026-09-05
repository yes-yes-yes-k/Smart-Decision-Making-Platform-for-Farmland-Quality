from __future__ import annotations
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ---- 模型文件路径（项目相对）----
# model_5.py 位于 framework/domain/other_models/model_5.py
# parents[0]=other_models, [1]=domain, [2]=framework, [3]=项目根
_MODELS_DIR = Path(__file__).resolve().parents[3] / "data" / "fertility" / "models"
_SOC_MODEL_PATH = _MODELS_DIR / "soc_etr_model.joblib"
_SOC_META_PATH = _MODELS_DIR / "soc_metadata.json"
_DOSE_MODEL_PATH = _MODELS_DIR / "dose_etr_model.joblib"
_DOSE_META_PATH = _MODELS_DIR / "dose_metadata.json"

# ---- 韶关（SG）区域 RF Dose 模型路径 ----
_SG_UPLAND_MODEL_PATH = _MODELS_DIR / "sg_dose_upland_rf_model.joblib"
_SG_UPLAND_META_PATH = _MODELS_DIR / "sg_dose_upland_metadata.json"
_SG_PADDY_MODEL_PATH = _MODELS_DIR / "sg_dose_paddy_rf_model.joblib"
_SG_PADDY_META_PATH = _MODELS_DIR / "sg_dose_paddy_metadata.json"

# 韶关区域 area_code 集合（可扩展）
SHAOGUAN_AREA_CODES = {"lechang"}

# ---- 尝试导入 sklearn / joblib ----
try:
    import joblib
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

logger.info("model_5 module imported, sklearn_available=%s", _SKLEARN_AVAILABLE)

# ---- 惰性单例状态 ----
_SOC_MODEL = None
_DOSE_MODEL = None
_SOC_META = None
_DOSE_META = None
_SOC_LOAD_FAILED = False
_DOSE_LOAD_FAILED = False

# ---- 韶关 SG RF 模型惰性单例状态 ----
_SG_UPLAND_MODEL = None
_SG_PADDY_MODEL = None
_SG_UPLAND_META = None
_SG_PADDY_META = None
_SG_UPLAND_LOAD_FAILED = False
_SG_PADDY_LOAD_FAILED = False

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


EXTERNAL_FIELD_MAP = {
    "SJD": "pH",
    "YJZ": "SOCbe",
    "TD": "TN",
    "TL": "TP",
    "TJ": "TK",
    "YXL": "AP",
    "SXJ": "AK",
    "YJZTSZ": "Gap",
    "YJFLX": "Fertilizer type",
    # API/常见结构化表单中的英文别名
    "fertilizer_type": "Fertilizer type",
}


def _same_value(left: Any, right: Any) -> bool:
    """比较字段值；数值字符串与数值本身视为同一输入。"""
    if left == right:
        return True
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def _normalize_input(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """统一外部字段和模型字段，检测规范字段与源字段冲突。"""
    normalized: Dict[str, Any] = {}
    for k, v in (input_data or {}).items():
        if v is None:
            continue
        raw_key = k.strip()
        key = EXTERNAL_FIELD_MAP.get(raw_key, raw_key)
        if key == "SOMbe":
            key = "SOCbe"
        if key in normalized and not _same_value(normalized[key], v):
            raise ValueError(f"input_conflict:{raw_key}->{key}")
        normalized[key] = v
    return normalized


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


def _ensure_sg_model_loaded(land_type: str) -> bool:
    """按 land_type 惰性加载对应 SG RF 模型，返回是否加载成功。

    - land_type="paddy" → 加载水田模型
    - 其他值（含 "upland" 及非法值）→ 加载旱地模型
    - 复用 _LOAD_LOCK 的 double-checked locking
    """
    global _SG_UPLAND_MODEL, _SG_PADDY_MODEL, _SG_UPLAND_META, _SG_PADDY_META
    global _SG_UPLAND_LOAD_FAILED, _SG_PADDY_LOAD_FAILED

    if land_type == "paddy":
        if _SG_PADDY_LOAD_FAILED:
            return False
        if _SG_PADDY_MODEL is None and not _SG_PADDY_LOAD_FAILED:
            with _LOAD_LOCK:
                if _SG_PADDY_MODEL is None and not _SG_PADDY_LOAD_FAILED:
                    try:
                        _SG_PADDY_MODEL, _SG_PADDY_META = _load_model_and_meta(
                            _SG_PADDY_MODEL_PATH, _SG_PADDY_META_PATH
                        )
                        logger.info(
                            "SG paddy model loaded, feature_names=%s, test_r2=%.4f",
                            _SG_PADDY_META["feature_names"],
                            _SG_PADDY_META["metrics"]["test_r2"],
                        )
                    except Exception:
                        _SG_PADDY_LOAD_FAILED = True
                        logger.exception("Failed to load SG paddy model")
        return not _SG_PADDY_LOAD_FAILED

    # upland 或非法值都走旱地分支
    if _SG_UPLAND_LOAD_FAILED:
        return False
    if _SG_UPLAND_MODEL is None and not _SG_UPLAND_LOAD_FAILED:
        with _LOAD_LOCK:
            if _SG_UPLAND_MODEL is None and not _SG_UPLAND_LOAD_FAILED:
                try:
                    _SG_UPLAND_MODEL, _SG_UPLAND_META = _load_model_and_meta(
                        _SG_UPLAND_MODEL_PATH, _SG_UPLAND_META_PATH
                    )
                    logger.info(
                        "SG upland model loaded, feature_names=%s, test_r2=%.4f",
                        _SG_UPLAND_META["feature_names"],
                        _SG_UPLAND_META["metrics"]["test_r2"],
                    )
                except Exception:
                    _SG_UPLAND_LOAD_FAILED = True
                    logger.exception("Failed to load SG upland model")
    return not _SG_UPLAND_LOAD_FAILED


_FALLBACK_REASON_CODES = {
    "sklearn_missing": "MODEL5_DEPENDENCY_UNAVAILABLE",
    "model_file_missing": "MODEL5_MODEL_UNAVAILABLE",
    "missing_input": "MODEL5_INPUT_MISSING",
    "invalid_input": "MODEL5_INPUT_INVALID",
    "unexpected_error": "MODEL5_PREDICTION_FAILED",
}


def _fallback_response(input_data: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """构造不含任何训练均值或规则数值的安全降级响应。"""
    reason_code = _FALLBACK_REASON_CODES.get(reason, "MODEL5_QUANTITATIVE_UNAVAILABLE")
    return {
        "status": "degraded",
        "model_id": "model-5",
        "soc_prediction": None,
        "soc_confidence": None,
        "dose_prediction": None,
        "dose": None,
        "manure_dosage": None,
        "potential_increase": None,
        "dose_confidence": None,
        "dose_warning": "真实模型当前不可用，未生成定量预测。",
        "imputed_features": [],
        "imputation_applied": False,
        "model_version": None,
        "reason": reason_code,
        "fallback_reason": reason,
        "data_source": "unavailable",
        "simulated": True,
    }


def model_5_execution(input_data: Dict[str, Any], land_type: Optional[str] = None) -> Dict[str, Any]:
    """model-5 SOC + Dose ML 预测主入口。

    输入：特征字典（key 可含/不含尾随空格，可缺字段；可含 area_code/land_type）
    输出：预测结果字典，含 status/soc_prediction/dose_prediction 等字段

    区域路由：
    - area_code 命中 SHAOGUAN_AREA_CODES → Dose 走 SG RF（按 land_type 选子模型），SOC 始终走全局 ETR
    - 未命中 → Dose 和 SOC 均走全局 ETR（行为不变，land_type 被忽略）
    - land_type 为 None 时默认 "upland"（韶关区域在 dose_warning 追加"未指定"提示）；
      仅 "upland"/"paddy" 合法，非法值默认 upland 并在韶关区域 dose_warning 中提示
    """
    try:
        # 1. 输入规范化（外部字段/SOMbe → 规范字段，strip，过滤 None）
        input_data = _normalize_input(input_data)

        # 2. 检查 sklearn 可用性
        if not _SKLEARN_AVAILABLE:
            return _fallback_response(input_data, reason="sklearn_missing")

        # 3. 区域判定
        area_code = input_data.get("area_code", "")
        is_shaoguan = isinstance(area_code, str) and area_code.lower() in SHAOGUAN_AREA_CODES

        # 4. land_type 规范化（None/非法值默认 upland；提示仅韶关区域生成）
        if land_type is None:
            land_type = input_data.get("land_type")
        land_type_missing = land_type is None
        land_type_norm = land_type if land_type in ("upland", "paddy") else "upland"
        land_type_invalid = land_type is not None and land_type not in ("upland", "paddy")

        # 5. SOC 始终走全局 ETR（先确保全局模型加载）
        if not _ensure_models_loaded():
            return _fallback_response(input_data, reason="model_file_missing")

        soc_df, soc_imputed, soc_oor = _prepare_features(
            input_data, _SOC_META["feature_names"], _SOC_META["feature_means"]
        )

        # 6. Dose 特征（去掉 Dose 自身）
        dose_input = {k: v for k, v in input_data.items() if k.strip() != "Dose"}

        # 7. Dose 区域路由
        if is_shaoguan:
            if not _ensure_sg_model_loaded(land_type_norm):
                return _fallback_response(input_data, reason="model_file_missing")
            if land_type_norm == "paddy":
                sg_model = _SG_PADDY_MODEL
                sg_meta = _SG_PADDY_META
                land_label = "水田"
            else:
                sg_model = _SG_UPLAND_MODEL
                sg_meta = _SG_UPLAND_META
                land_label = "旱地"
            dose_df, dose_imputed, dose_oor = _prepare_features(
                dose_input, sg_meta["feature_names"], sg_meta["feature_means"]
            )
        else:
            dose_df, dose_imputed, dose_oor = _prepare_features(
                dose_input, _DOSE_META["feature_names"], _DOSE_META["feature_means"]
            )

        # 8. 范围校验：任一越界即拒绝
        all_oor = soc_oor + dose_oor
        if all_oor:
            return {
                "status": "rejected",
                "model_id": "model-5",
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
                "simulated": False,
            }

        missing_features = sorted(set(soc_imputed + dose_imputed))
        if missing_features:
            fallback = _fallback_response(input_data, reason="missing_input")
            fallback["missing_features"] = missing_features
            return fallback

        # 9. 执行预测
        soc_pred = float(_SOC_MODEL.predict(soc_df)[0])

        if is_shaoguan:
            dose_pred = float(sg_model.predict(dose_df)[0])
            sg_test_r2 = sg_meta["metrics"]["test_r2"]
            # land_type 提示仅韶关区域生成（spec: 非韶关 SHALL 忽略 land_type）
            if land_type_missing:
                lt_warning = "（未指定 land_type，默认使用旱地模型）"
            elif land_type_invalid:
                lt_warning = f"（未识别的 land_type={land_type}，默认按旱地处理）"
            else:
                lt_warning = ""
            dose_warning = (
                f"韶关{land_label} RF 模型 R²={sg_test_r2:.2f}，预测结果仅供参考"
                f"{lt_warning}"
            )
            dose_confidence = round(sg_test_r2, 2)
            # 低样本量提示
            if sg_meta.get("training_samples", 0) < 30:
                dose_warning += "（训练样本量较少，置信度偏低）"
            # 韶关 dose 返回 SG RF 模型版本号（spec: 韶关 dose 响应 model_version）
            response_model_version = sg_meta["model_version"]
        else:
            dose_pred = float(_DOSE_MODEL.predict(dose_df)[0])
            # 非韶关区域忽略 land_type（spec: 非韶关 SHALL 忽略 land_type）
            dose_warning = (
                "Dose 模型 R²=0.47，预测结果仅供参考，建议结合田间试验校准"
            )
            dose_confidence = round(_DOSE_META["metrics"]["test_r2"], 2)
            # 非韶关 dose 返回全局 ETR 版本号
            response_model_version = _MODEL_VERSION

        logger.info(
            "model_5_execution success: SOC=%.4f, Dose=%.4f, is_shaoguan=%s, land_type=%s",
            soc_pred, dose_pred, is_shaoguan, land_type_norm,
        )

        # 10. 构造响应
        return {
            "status": "success",
            "model_id": "model-5",
            "soc_prediction": round(soc_pred, 4),
            "soc_confidence": round(_SOC_META["metrics"]["test_r2"], 2),
            "dose_prediction": round(dose_pred, 4),
            "dose_confidence": dose_confidence,
            "dose_warning": dose_warning.strip(),
            "imputed_features": sorted(set(soc_imputed + dose_imputed)),
            "imputation_applied": bool(soc_imputed or dose_imputed),
            "model_version": response_model_version,
            "region": "shaoguan" if is_shaoguan else "global",
            "land_type": land_type_norm if is_shaoguan else None,
            "simulated": False,
        }

    except ValueError as e:
        if str(e).startswith("input_conflict:"):
            return {
                "status": "rejected",
                "reason": "input_conflict",
                "message": str(e),
                "model_id": "model-5",
                "soc_prediction": None,
                "dose_prediction": None,
                "simulated": False,
            }
        logger.exception("model_5_execution input validation error: %s", e)
        return _fallback_response(input_data, reason="invalid_input")
    except Exception as e:
        logger.exception(f"model_5_execution unexpected error: {e}")
        return _fallback_response(input_data, reason="unexpected_error")
