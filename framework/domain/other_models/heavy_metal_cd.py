"""Local torch port of the AcidMap heavy-metal Cd prediction models.

Two independent PyTorch MLPs are loaded directly with torch (``weights_only=False``,
source asset already verified by manifest hash):

- ``crop_cd``      : 14 features  -> crop Cd content (mg/kg)
- ``effective_cd`` : 21 features -> soil available Cd (mg/kg)

Both models embed a linear term ``a * special_feature + b`` where the special
feature is ``solution`` (index 13) / ``Cdsolution`` (index 20).  The special
feature decides the monotonic direction, so a wrong index silently shifts the
prediction (crop_cd misusing fallback index 2 shifts mean 0.261 -> 0.339).

Feature order is fixed by the scaler array order (= the DataFrame construction
order in the source repo).  The public API uses readable field names; the model
column order is kept as an internal constant with dimension assertions.

``solution``/``Cdsolution`` come from the upstream MSM complexation model which
is NOT in this repository.  Per user decision, a missing special input is filled
with the training-set median (-2.1266, n=40100) as an explicit assumption and the
result is forced to ``degraded``.  Other missing/invalid inputs are rejected
without calling the model.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = (_ROOT / "data" / "model_artifacts" / "heavy_metal_cd").resolve()
MANIFEST_PATH = ARTIFACT_ROOT / "manifest.json"

#: 对外可读字段（顺序 = 模型训练列序 = scaler 数组顺序）。
_API_FIELDS: dict[str, tuple[str, ...]] = {
    "crop_cd": (
        "silt_fraction", "sand_fraction", "gravel_fraction",
        "available_phosphorus", "available_potassium", "slowly_available_potassium",
        "total_aluminum", "total_calcium", "total_iron", "total_magnesium",
        "total_manganese", "total_nitrogen", "total_sulfur", "solution",
    ),
    "effective_cd": (
        "oc_fe_0_30", "silt_fraction", "sand_fraction", "gravel_fraction",
        "available_potassium", "available_phosphorus", "electrical_conductivity",
        "slowly_available_potassium", "total_aluminum", "total_calcium",
        "total_cadmium", "exchangeable_base", "exchangeable_hydrogen",
        "total_iron", "total_potassium", "total_magnesium", "total_manganese",
        "total_nitrogen", "total_phosphorus", "total_sulfur", "cdsolution",
    ),
}

#: 模型内部列名（AcidMap 特征名，顺序与 scaler 数组一致）。
_MODEL_COLUMNS: dict[str, tuple[str, ...]] = {
    "crop_cd": (
        "002_0002IDW", "02_002IDW", "2_02IDW", "AvaP", "AvaK_IDW", "SAvaK_IDW",
        "TAl_IDW", "TCa_IDW", "TFe_IDW", "TMg_IDW", "TMn_IDW", "TN_IDW",
        "TS_IDW", "solution",
    ),
    "effective_cd": (
        "OC-Fe_0-30", "002_0002IDW", "02_002IDW", "2_02IDW", "AvaK_IDW", "AvaP_IDW",
        "EC_IDW", "SAvaK_IDW", "TAl_IDW", "TCa_IDW", "TCd_IDW", "TEB_IDW",
        "TExH_IDW", "TFe_IDW", "TK_IDW", "TMg_IDW", "TMn_IDW", "TN_IDW",
        "TP_IDW", "TS_IDW", "Cdsolution",
    ),
}

#: 特殊特征（单调约束方向由它决定）：对外字段名 + 在特征序中的位置。
_SPECIAL_FEATURE: dict[str, tuple[str, int]] = {
    "crop_cd": ("solution", 13),
    "effective_cd": ("cdsolution", 20),
}

#: 别名（小写化匹配，避免大小写/下划线差异）。
_ALIASES: dict[str, str] = {
    "silt": "silt_fraction", "sand": "sand_fraction", "gravel": "gravel_fraction",
    "avail_p": "available_phosphorus", "avail_k": "available_potassium",
    "sl_avail_k": "slowly_available_potassium", "t_al": "total_aluminum",
    "t_ca": "total_calcium", "t_fe": "total_iron", "t_mg": "total_magnesium",
    "t_mn": "total_manganese", "t_n": "total_nitrogen", "t_s": "total_sulfur",
    "total_n": "total_nitrogen", "cdsolution": "cdsolution",
    "oc_fe": "oc_fe_0_30", "ec": "electrical_conductivity",
    "t_cd": "total_cadmium", "t_eb": "exchangeable_base", "t_exh": "exchangeable_hydrogen",
    "t_k": "total_potassium", "t_p": "total_phosphorus",
    # AcidMap 原始特征名直连
    "002_0002idw": "silt_fraction", "02_002idw": "sand_fraction", "2_02idw": "gravel_fraction",
    "avap": "available_phosphorus", "avak_idw": "available_potassium",
    "savak_idw": "slowly_available_potassium", "tal_idw": "total_aluminum",
    "tca_idw": "total_calcium", "tfe_idw": "total_iron", "tmg_idw": "total_magnesium",
    "tmn_idw": "total_manganese", "tn_idw": "total_nitrogen", "ts_idw": "total_sulfur",
    "oc-fe_0-30": "oc_fe_0_30", "ec_idw": "electrical_conductivity",
    "tcd_idw": "total_cadmium", "teb_idw": "exchangeable_base",
    "texh_idw": "exchangeable_hydrogen", "tk_idw": "total_potassium",
    "tp_idw": "total_phosphorus",
}

#: 训练集参考值（soilgd 输入表，两模型共用同值；用户拍板的降级建议值）。
_REFERENCE_STATS: dict[str, Any] = {
    "value": -2.1266,
    "n": 40100,
    "p25": -3.0787,
    "p75": -1.2319,
    "dataset": "soilgd.CropCd_input_data / EffCd_input_data",
    "unit_status": "unverified",
    "note": "训练样本中位数，非地块实测；采用后结论按降级处理",
}


class HeavyMetalCdError(ValueError):
    """Invalid or unavailable Cd prediction request."""


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    prediction: str
    features: int
    special_feature_index: int
    special_feature_name: str
    baseline_prediction_means_input: float
    files: dict[str, str]


def _manifest() -> dict[str, ModelRecord]:
    try:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HeavyMetalCdError("model_unavailable") from exc
    out: dict[str, ModelRecord] = {}
    for key, item in (raw.get("models") or {}).items():
        try:
            out[key] = ModelRecord(
                model_id=key,
                prediction=item["prediction"],
                features=int(item["features"]),
                special_feature_index=int(item["special_feature_index"]),
                special_feature_name=item["special_feature_name"],
                baseline_prediction_means_input=float(item["baseline_prediction_means_input"]),
                files=dict(item["files"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HeavyMetalCdError("model_metadata_invalid") from exc
    if not out:
        raise HeavyMetalCdError("model_unavailable")
    return out


def _record(model_id: str) -> ModelRecord:
    try:
        return _manifest()[model_id]
    except (KeyError, TypeError) as exc:
        raise HeavyMetalCdError("unknown_model") from exc


def _load_constraint_module(model_dir: Path, modname: str) -> None:
    """torch.load 反序列化需要先注册 .pth 里 pickle 引用的类定义模块。"""
    path = model_dir / f"{modname}.py"
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)


def load_model(model_id: str):
    """校验 manifest 摘要后加载 torch 模型（weights_only=False，资产受控且 hash 已核验）。"""
    record = _record(model_id)
    model_dir = (ARTIFACT_ROOT / model_id).resolve()
    if ARTIFACT_ROOT not in model_dir.parents or not model_dir.is_dir():
        raise HeavyMetalCdError("model_unavailable")
    pth_name = next((k for k in record.files if k.endswith(".pth")), None)
    if pth_name is None:
        raise HeavyMetalCdError("model_metadata_invalid")
    for name, digest in record.files.items():
        path = model_dir / name
        if ARTIFACT_ROOT not in path.resolve().parents or not path.is_file():
            raise HeavyMetalCdError("model_unavailable")
        actual = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        if actual != digest.upper():
            raise HeavyMetalCdError("model_integrity_mismatch")
    # 注册 .pth 反序列化所需的类定义模块
    modname = "constrained_nn6" if model_id == "crop_cd" else "constrained_nn6C"
    try:
        _load_constraint_module(model_dir, modname)
    except Exception as exc:  # noqa: BLE001 - 加载失败按资产异常处理
        raise HeavyMetalCdError("model_unavailable") from exc
    model = torch.load(str(model_dir / pth_name), map_location="cpu", weights_only=False)
    model.eval()
    return record, model, model_dir


def _normalise(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in row.items():
        key = str(raw_key).strip()
        canonical = key if key in _API_FIELDS["crop_cd"] or key in _API_FIELDS["effective_cd"] else _ALIASES.get(key.lower(), key)
        if canonical in _API_FIELDS["crop_cd"] or canonical in _API_FIELDS["effective_cd"]:
            out[canonical] = value
    return out


def _number(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HeavyMetalCdError("invalid_input") from exc
    return result if math.isfinite(result) else None


def predict(
    model_id: str,
    data: Mapping[str, Any],
    assumptions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one Cd parameter-level prediction locally with torch.

    - Complete finite inputs            -> ``success``
    - Missing ``solution``/``cdsolution``-> filled with training median, ``degraded``,
      ``assumed_fields`` echoes the reference stats (user decision).
    - Missing other required field      -> ``need_input``; invalid input -> ``rejected``.
      The model is never loaded/called on these paths.
    """
    try:
        if model_id not in _API_FIELDS:
            raise HeavyMetalCdError("unknown_model")
        fields = _API_FIELDS[model_id]
        canonical = _normalise(data)
        values: dict[str, float | None] = {f: _number(canonical.get(f)) for f in fields}

        missing = [f for f in fields if values[f] is None]
        special, special_idx = _SPECIAL_FEATURE[model_id]
        assumed: dict[str, Any] = {}
        if values[special] is None:
            # 用户拍板：缺失特殊络合输入时采用训练集中位数并强制降级
            values[special] = float(_REFERENCE_STATS["value"])
            assumed[special] = {
                "basis": "training_median",
                "value": _REFERENCE_STATS["value"],
                "n": _REFERENCE_STATS["n"],
                "p25_p75": [_REFERENCE_STATS["p25"], _REFERENCE_STATS["p75"]],
                "dataset": _REFERENCE_STATS["dataset"],
                "unit_status": _REFERENCE_STATS["unit_status"],
            }
        missing = [f for f in fields if values[f] is None]
        if missing:
            return {
                "status": "need_input",
                "model_id": model_id,
                "missing_fields": missing,
                "assumed_fields": assumed if assumed else {},
                "prediction": None,
                "source": "heavy_metal_cd_local",
            }
        # 显式 assumptions（如调用方声明的其他参考值）也强制降级
        explicit = {
            str(k): str(v) for k, v in (assumptions or {}).items()
            if str(k) in fields
        }
        if explicit:
            assumed.update(explicit)

        record, model, model_dir = load_model(model_id)
        if len(fields) != record.features:
            raise HeavyMetalCdError("model_metadata_invalid")

        # mean/scale 从资产目录加载，标准化后转 tensor
        mean = np.load(str(model_dir / next(k for k in record.files if k.endswith("_mean.npy")))).astype(np.float64)
        scale = np.load(str(model_dir / next(k for k in record.files if k.endswith("_scale.npy")))).astype(np.float64)
        if mean.shape[0] != len(fields) or scale.shape[0] != len(fields):
            raise HeavyMetalCdError("model_metadata_invalid")

        x_row = np.array([values[f] for f in fields], dtype=np.float64)
        x_scaled = ((x_row - mean) / scale).astype(np.float32).reshape(1, -1)
        x_t = torch.tensor(x_scaled)
        with torch.no_grad():
            log_pred = float(model(x_t, x_t, special_idx).squeeze().item())
        if not math.isfinite(log_pred):
            raise HeavyMetalCdError("prediction_not_finite")
        prediction = float(math.exp(log_pred))

        result: dict[str, Any] = {
            "status": "degraded" if assumed else "success",
            "model_id": model_id,
            "prediction": prediction,
            "unit": "mg/kg",
            "unit_status": "unverified",
            "special_feature": {
                "name": special,
                "assumed": bool(assumed.get(special)),
            },
            "assumed_fields": assumed,
            "source": "heavy_metal_cd_local",
        }
        return result
    except HeavyMetalCdError as exc:
        return {
            "status": "rejected",
            "reason": str(exc),
            "model_id": model_id,
            "prediction": None,
            "source": "heavy_metal_cd_local",
        }


def available_models() -> list[dict[str, Any]]:
    """List the Cd models registered in the checked-in manifest (public fields only)."""
    records = _manifest()
    return [
        {
            "model_id": record.model_id,
            "prediction": record.prediction,
            "features": record.features,
            "special_feature_index": record.special_feature_index,
            "special_feature_name": record.special_feature_name,
            "input_fields": list(_API_FIELDS[record.model_id]),
            "unit_status": "unverified",
            "note": "参数级预测，不等同于地块级评估",
        }
        for record in sorted(records.values(), key=lambda item: item.model_id)
    ]


#: parcel_info.soil_indicators 键 → Cd 对外字段（仅语义/单位/来源可确认的映射）。
_INDICATORS_TO_CD: dict[str, str] = {
    "available_potassium": "available_potassium",
    "available_phosphorus": "available_phosphorus",
    "total_n": "total_nitrogen",
    "silt_content": "silt_fraction",
    "sand_content": "sand_fraction",
}


def prefill_from_parcel(
    indicators: Mapping[str, Any],
    model_id: str,
) -> dict[str, Any]:
    """Build Cd input prefill from one parcel's stored indicators.

    Only fields with an established mapping are filled; ``provenance`` reports the
    stored source of each filled field (``measured`` / ``region_mean_backfill`` /
    ``default`` / ``unknown``).  Unmapped or absent inputs go to ``missing_fields``.
    Never fabricates values; never auto-runs prediction.
    """
    if model_id not in _API_FIELDS:
        raise HeavyMetalCdError("unknown_model")
    fields = _API_FIELDS[model_id]
    stored = dict(indicators.get("provenance") or {})
    data: dict[str, Any] = {}
    sources: dict[str, str] = {}
    missing: list[str] = []
    for field in fields:
        indicator_key = next((k for k, v in _INDICATORS_TO_CD.items() if v == field), None)
        value = indicators.get(indicator_key) if indicator_key else None
        if value is None:
            missing.append(field)
            continue
        data[field] = value
        sources[field] = stored.get(indicator_key, "unknown")
    return {
        "status": "need_input" if missing else "ready",
        "model_id": model_id,
        "data": data,
        "provenance": sources,
        "missing_fields": missing,
        "is_parcel_level_assessment": False,
        "prediction_not_run": True,
    }
