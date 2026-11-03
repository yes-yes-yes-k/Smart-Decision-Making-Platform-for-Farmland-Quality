"""Independent local port of the legacy AcidificationModel RF /predict path.

This module intentionally does not call model-4, the legacy HTTP service, or any
offline CSV calculation.  Model identity is controlled by the checked-in manifest.
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import sklearn
from sklearn.impute import SimpleImputer

from ..provenance import IMPUTED_SOURCES, SOURCE_REGION_MEAN_BACKFILL

_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = (_ROOT / "data" / "model_artifacts" / "acidification_rf").resolve()
MANIFEST_PATH = ARTIFACT_ROOT / "manifest.json"
REFERENCE_PATH = ARTIFACT_ROOT / "reference_values.json"

# 对外 API 字段（按模型）。前端按可读名传参，不必关心模型内部列序。
_API_FIELDS: dict[int, tuple[str, ...]] = {
    33: ("init_pH", "target_pH", "H", "Al", "OM", "NO3", "NH4", "CEC"),
    35: ("H", "Al", "OM", "NO3", "NH4", "CEC"),
    38: ("CEC", "NH4", "NO3", "Al", "FeO", "OM"),
}
# 模型 pickle 的真实训练列名与顺序（2026-10-17 从 feature_names_in_ 核实）。
# 水田 reflux 与旱地 reflux 的字段集不同：水田用 FeO 且无 H。
_MODEL_COLUMNS: dict[int, tuple[str, ...]] = {
    33: ("pH", "H", "Al", "OM", "NO3", "NH4", "CEC"),
    35: ("H", "Al", "OM", "NO3", "NH4", "CEC"),
    38: ("CEC", "NH4", "NO3", "Al", "FeO", "OM"),
}
# 模型列名 → API 字段名（仅 reduce 的 pH 与 init_pH 不同名）。
_COLUMN_TO_API = {"pH": "init_pH"}

_ALIASES = {
    "init_ph": "init_pH", "initial_pH": "init_pH", "pH": "init_pH",
    "target_ph": "target_pH", "h": "H", "al": "Al", "om": "OM",
    "no3": "NO3", "nh4": "NH4", "cec": "CEC", "feo": "FeO",
}


class AcidificationRFError(ValueError):
    """Invalid or unavailable RF request."""


@dataclass(frozen=True)
class ModelRecord:
    model_id: int
    data_type: str
    land_type: str
    artifact_path: str
    source_model_file_path: str
    sha256: str
    verified_at: str
    source: str
    artifact_size_bytes: int = 0
    serialization_format: str = "pickle"
    serialization_protocol: int = 0
    serialized_with_scikit_learn: str = "unknown"


def _manifest() -> dict[int, ModelRecord]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {int(x["model_id"]): ModelRecord(**x) for x in raw["models"]}


def _record(model_id: int) -> ModelRecord:
    try:
        return _manifest()[int(model_id)]
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise AcidificationRFError("model_unavailable") from exc


def _reference() -> dict[str, Any]:
    """Reference statistics of the training sets, used only as opt-in suggestions."""
    try:
        return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AcidificationRFError("reference_unavailable") from exc


def load_model(model_id: int):
    record = _record(model_id)
    numpy_major = int(np.__version__.split(".", 1)[0])
    if numpy_major != 2 or sklearn.__version__ != record.serialized_with_scikit_learn:
        raise AcidificationRFError("model_unavailable")
    path = (ARTIFACT_ROOT / record.artifact_path).resolve()
    if ARTIFACT_ROOT not in path.parents or path.suffix.lower() != ".pkl" or not path.is_file():
        raise AcidificationRFError("model_unavailable")
    if path.stat().st_size != record.artifact_size_bytes:
        raise AcidificationRFError("model_integrity_mismatch")
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if digest != record.sha256.upper():
        raise AcidificationRFError("model_integrity_mismatch")
    try:
        with path.open("rb") as handle:
            model = pickle.load(handle)
    except (ImportError, AttributeError, EOFError, pickle.UnpicklingError, ValueError) as exc:
        # These assets were serialized with the versions recorded in the project
        # dependencies. A stale runtime (for example NumPy 1.x loading a NumPy
        # 2.x pickle) cannot safely execute them; report the model as unavailable
        # instead of leaking a 500 traceback from the API.
        raise AcidificationRFError("model_unavailable") from exc
    if not callable(getattr(model, "predict", None)):
        raise AcidificationRFError("model_metadata_invalid")
    return record, model


def _same(left: Any, right: Any) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return left == right


def _normalise(record: ModelRecord, row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    expected = _API_FIELDS[record.model_id]
    for raw_key, value in row.items():
        key = str(raw_key).strip()
        canonical = key if key in expected else _ALIASES.get(key.lower(), key)
        if canonical not in expected:
            continue
        if canonical in out and not _same(out[canonical], value):
            raise AcidificationRFError(f"input_conflict:{canonical}")
        out[canonical] = value
    return out


def _number(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AcidificationRFError("invalid_input") from exc
    return result if math.isfinite(result) else None


def _records(data: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(data, Mapping):
        return [data]
    rows = list(data)
    if not rows:
        raise AcidificationRFError("empty_batch")
    return rows


def predict(
    model_id: int,
    data: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    assumptions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one or more legacy-online RF predictions locally.

    ``assumptions`` records fields whose values came from a suggestion rather
    than a measurement (e.g. ``{"NO3": "training_median"}``). Any non-empty
    assumption set forces ``status`` to ``degraded`` so callers cannot present
    the result as fully evidence-based.
    """
    try:
        rows = _records(data)
        # Validate and prepare the complete request before loading the pickle.
        # Besides being cheaper, this is an important boundary: malformed input
        # must never cause model I/O or invoke model code.
        record = _record(model_id)
        if any(not isinstance(row, Mapping) for row in rows):
            raise AcidificationRFError("invalid_input")
        canonical = [_normalise(record, row) for row in rows]
        api_fields = _API_FIELDS[record.model_id]
        columns = _MODEL_COLUMNS[record.model_id]
        matrix: list[list[Any]] = []
        for row in canonical:
            values = {field: _number(row.get(field)) for field in api_fields}
            if record.data_type == "reduce" and (
                values.get("init_pH") is None or values.get("target_pH") is None
            ):
                raise AcidificationRFError("missing_input")
            # 严格按模型训练列序排列；sklearn 收到 ndarray 时不会校验列名。
            matrix.append([values.get(_COLUMN_TO_API.get(col, col)) for col in columns])
        arr = np.asarray(matrix, dtype=object)
        api_by_column = [_COLUMN_TO_API.get(col, col) for col in columns]
        missing = [api_by_column[i] for i in range(len(columns)) if all(v is None for v in arr[:, i])]
        if missing:
            return {"status": "rejected", "reason": "all_column_missing", "model_id": record.model_id,
                    "missing_fields": missing, "imputed_fields": [], "predictions": []}
        imputed = [api_by_column[i] for i in range(len(columns)) if any(v is None for v in arr[:, i])]
        prepared = SimpleImputer(strategy="mean").fit_transform(arr.astype(float))
        record, model = load_model(model_id)
        raw = np.asarray(model.predict(prepared), dtype=float).reshape(-1)
        results = []
        for index, prediction in enumerate(raw):
            item: dict[str, Any] = {"raw_prediction": float(prediction)}
            if record.data_type == "reduce":
                init = _number(canonical[index].get("init_pH"))
                target = _number(canonical[index].get("target_pH"))
                q = prediction * (target - init)
                t_ha = q * 25
                item.update({"result": t_ha / 15, "unit": "t/mu", "conversion": "Q=raw*(target_pH-init_pH); t/ha=Q*25; t/mu=t/ha/15"})
            else:
                item.update({"result": abs(float(prediction)) if record.land_type == "paddy_field" else float(prediction),
                             "unit": "raw_prediction", "conversion": "abs" if record.land_type == "paddy_field" else "identity"})
            results.append(item)
        assumed = {
            str(key): str(value)
            for key, value in (assumptions or {}).items()
            if str(key) in set(api_fields)
        }
        return {"status": "degraded" if (imputed or assumed) else "success", "model_id": record.model_id,
                "data_type": record.data_type, "land_type": record.land_type,
                "imputed_fields": imputed, "assumed_fields": assumed,
                "imputation": {"strategy": "mean", "fit": "request_batch"},
                "predictions": results, "source": "acidification_rf_local"}
    except AcidificationRFError as exc:
        return {"status": "rejected", "reason": str(exc), "model_id": model_id, "predictions": []}


def map_parcel_indicators(indicators: Mapping[str, Any]) -> dict[str, Any]:
    """Map only explicitly established indicator semantics; unknown RF fields stay unknown."""
    known = {key: indicators[key] for key in ("soil_ph", "exchangeable_hydrogen", "exchangeable_aluminum", "organic_matter") if key in indicators}
    return {"status": "need_verification", "data": known, "unknown_fields": ["NO3", "NH4", "CEC", "FeO"],
            "provenance": {key: "known" for key in known}, "degraded": True}


def available_models() -> list[dict[str, Any]]:
    """List the RF models registered in the checked-in manifest.

    Returns only public identity fields; artifact paths and hashes stay internal.
    """
    try:
        records = _manifest()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise AcidificationRFError("model_unavailable") from exc
    return [
        {"model_id": record.model_id, "data_type": record.data_type, "land_type": record.land_type}
        for record in sorted(records.values(), key=lambda item: item.model_id)
    ]


# 地块 land_type（parcel_info）→ manifest land_type 的对应关系。
_PARCEL_LAND_TO_RF = {
    "upland": "dryland",
    "dryland": "dryland",
    "paddy": "paddy_field",
    "paddy_field": "paddy_field",
}

# RF 规范字段 ← parcel_info.soil_indicators 键。
_RF_FROM_INDICATORS = {
    "init_pH": "soil_ph",
    "H": "exchangeable_hydrogen",
    "Al": "exchangeable_aluminum",
    "OM": "organic_matter",
    "CEC": "cation_exchange_capacity",
    "target_pH": "target_ph",
}

# 当前地块数据中不存在对应字段的 RF 输入。
_RF_NOT_IN_PARCEL_DATA = ("NO3", "NH4", "FeO")


def prefill_from_parcel(
    indicators: Mapping[str, Any],
    land_type: str,
    model_id: int | None = None,
) -> dict[str, Any]:
    """Build RF input prefill from one parcel's stored indicators.

    Only fields with an established mapping are filled. Fields absent from the
    parcel data are returned in ``missing_fields`` and left for the caller to
    supply; this function never fabricates them.

    ``provenance`` reports the stored source of each filled field
    (``measured`` / ``region_mean_backfill`` / ``default``), so callers can
    disclose that some inputs are not parcel-level measurements.
    """
    rf_land = _PARCEL_LAND_TO_RF.get(str(land_type or "").strip().lower())
    if rf_land is None:
        raise AcidificationRFError("unknown_land_type")

    models = available_models()
    if model_id is None:
        record = next(
            (m for m in models if m["land_type"] == rf_land and m["data_type"] == "reflux"),
            None,
        )
        if record is None:
            raise AcidificationRFError("model_unavailable")
    else:
            record = next((m for m in models if m["model_id"] == int(model_id)), None)
            if record is None:
                raise AcidificationRFError("model_unavailable")
            # 旧系统语义：reduce（降酸）不区分土地类型，水田降酸沿用旱地 reduce 模型；
            # 仅 reflux 按土地类型严格匹配（35 旱地 / 38 水田特征契约不同，错配会静默喂错列）。
            if record["data_type"] == "reflux" and record["land_type"] != rf_land:
                raise AcidificationRFError("land_type_mismatch")

    stored = dict(indicators.get("provenance") or {})
    data: dict[str, Any] = {}
    sources: dict[str, str] = {}
    missing: list[str] = []

    for field in _API_FIELDS[record["model_id"]]:
        source_key = _RF_FROM_INDICATORS.get(field)
        value = indicators.get(source_key) if source_key else None
        if value is None:
            missing.append(field)
            continue
        data[field] = value
        sources[field] = stored.get(source_key, "unknown")

    imputed = [f for f, src in sources.items() if src in IMPUTED_SOURCES]
    warnings: list[str] = []
    for field in imputed:
        if sources[field] == SOURCE_REGION_MEAN_BACKFILL:
            warnings.append(f"{field} 为区域平均回填值，非地块实测")
        else:
            warnings.append(f"{field} 使用默认值")
    for field in missing:
        if field in _RF_NOT_IN_PARCEL_DATA:
            warnings.append(f"{field} 在地块数据中没有对应字段，需手工填写")

    suggestions = _build_suggestions(record["model_id"], missing)
    for field, item in suggestions.items():
        warnings.append(
            f"{field} 可参考训练样本中位数 {item['value']}（n={item['row_count']}，非实测，采用后按降级处理）"
        )

    return {
        "status": "need_input" if missing else "ready",
        "model_id": record["model_id"],
        "data_type": record["data_type"],
        "land_type": record["land_type"],
        "data": data,
        "provenance": sources,
        "missing_fields": missing,
        "imputed_fields": imputed,
        "suggestions": suggestions,
        "warnings": warnings,
    }


def _build_suggestions(model_id: int, missing: Sequence[str]) -> dict[str, Any]:
    """Opt-in reference values for fields the parcel data cannot supply.

    These are training-set medians, not measurements. Callers must let the end
    user decide whether to adopt them, and pass the choice back as
    ``assumptions`` on ``predict`` so the result is marked degraded.
    """
    if not missing:
        return {}
    try:
        reference = _reference()
    except AcidificationRFError:
        return {}
    entry = (reference.get("models") or {}).get(str(model_id)) or {}
    stats_by_field = entry.get("fields") or {}
    out: dict[str, Any] = {}
    for field in missing:
        stats = stats_by_field.get(field)
        if not stats:
            continue
        out[field] = {
            "value": stats["median"],
            "basis": "training_median",
            "dataset": entry.get("dataset"),
            "row_count": entry.get("row_count"),
            "range_p25_p75": [stats["p25"], stats["p75"]],
            "unit_status": reference.get("unit_status", "unverified"),
            "note": "训练样本中位数，非地块实测；采用后结论按降级处理",
        }
    return out
