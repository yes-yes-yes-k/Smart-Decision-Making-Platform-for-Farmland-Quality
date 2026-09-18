"""Indicator provenance helpers and deterministic parcel-data quality audits."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from .indicator_definitions import CLASSIFICATION_VERSION, INDICATOR_DEFINITIONS


PROVENANCE_FIELD = "indicator_provenance"
LOW_VARIABILITY_METRICS = {"plow_layer_thickness", "effective_soil_depth"}


def source_provenance(metric_key: str, measurement_year: int) -> dict[str, Any]:
    """Describe values read directly from the source dataset.

    ``isImputed=False`` means the backend importer did not fill the value. It
    deliberately does not claim that the source value was field-measured.
    """
    return {
        "data_source": "model1_shapefile",
        "measurement_year": measurement_year,
        "is_imputed": False,
        "imputation_method": None,
        "quality_flag": (
            "low_variability" if metric_key in LOW_VARIABILITY_METRICS
            else "source_unverified"
        ),
    }


def build_source_provenance(
    indicators: Mapping[str, Any],
    measurement_year: int,
) -> dict[str, dict[str, Any]]:
    return {
        key: source_provenance(key, measurement_year)
        for key, definition in INDICATOR_DEFINITIONS.items()
        if definition.value_from(dict(indicators)) not in (None, "")
    }


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def metric_provenance(indicators: Mapping[str, Any], metric_key: str) -> dict[str, Any]:
    provenance_map = _json_object(indicators.get(PROVENANCE_FIELD))
    raw = _json_object(provenance_map.get(metric_key))

    def first(*names: str) -> Any:
        for name in names:
            if name in raw:
                return raw[name]
        return None

    quality_flag = first("quality_flag", "qualityFlag")
    if not raw:
        quality_flag = "provenance_missing"
    return {
        "dataSource": first("data_source", "dataSource"),
        "measurementYear": first("measurement_year", "measurementYear"),
        "isImputed": first("is_imputed", "isImputed"),
        "imputationMethod": first("imputation_method", "imputationMethod"),
        "qualityFlag": quality_flag,
    }


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _counter_dict(counter: Counter) -> dict[str, int]:
    return {
        str(key): count
        for key, count in sorted(counter.items(), key=lambda item: str(item[0]))
    }


def audit_indicator_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows]
    parcel_count = len(materialized)
    updated_values = [row.get("updated_at") for row in materialized if row.get("updated_at")]
    metrics: list[dict[str, Any]] = []

    for metric_key, definition in INDICATOR_DEFINITIONS.items():
        non_empty_count = 0
        parse_failure_count = 0
        unclassified_count = 0
        values: list[float] = []
        data_sources: Counter = Counter()
        years: Counter = Counter()
        imputed: Counter = Counter()
        methods: Counter = Counter()
        provenance_flags: Counter = Counter()

        for row in materialized:
            indicators = _json_object(row.get("soil_indicators"))
            raw_value = definition.value_from(indicators)
            if raw_value not in (None, ""):
                non_empty_count += 1
            value = definition.parse(raw_value)
            if raw_value not in (None, "") and value is None:
                parse_failure_count += 1
            if value is not None:
                values.append(value)
                if definition.classify(value) is None:
                    unclassified_count += 1

            provenance = metric_provenance(indicators, metric_key)
            data_sources[provenance["dataSource"] or "unknown"] += 1
            years[provenance["measurementYear"] or "unknown"] += 1
            imputed_value = provenance["isImputed"]
            imputed["unknown" if imputed_value is None else str(bool(imputed_value)).lower()] += 1
            methods[provenance["imputationMethod"] or "none"] += 1
            provenance_flags[provenance["qualityFlag"] or "unflagged"] += 1

        unique_count = len(set(values))
        quality_flags: list[str] = []
        if non_empty_count < parcel_count:
            quality_flags.append("missing_values")
        if parse_failure_count:
            quality_flags.append("parse_failures")
        if unclassified_count:
            quality_flags.append("unclassified_values")
        if values and unique_count == 1:
            quality_flags.append("constant_value")
        elif values and unique_count <= 4:
            quality_flags.append("low_variability")
        if data_sources.get("unknown", 0):
            quality_flags.append("provenance_missing")

        metrics.append({
            "metricKey": metric_key,
            "label": definition.label,
            "unit": definition.unit,
            "parcelCount": parcel_count,
            "nonEmptyCount": non_empty_count,
            "nonEmptyRate": round(non_empty_count * 100 / parcel_count, 4) if parcel_count else 0.0,
            "parseableCount": len(values),
            "parseFailureCount": parse_failure_count,
            "unclassifiedCount": unclassified_count,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "uniqueValueCount": unique_count,
            "qualityFlags": quality_flags,
            "provenance": {
                "dataSources": _counter_dict(data_sources),
                "measurementYears": _counter_dict(years),
                "isImputed": _counter_dict(imputed),
                "imputationMethods": _counter_dict(methods),
                "qualityFlags": _counter_dict(provenance_flags),
            },
        })

    return {
        "classificationVersion": CLASSIFICATION_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataAsOf": _isoformat(max(updated_values)) if updated_values else None,
        "parcelCount": parcel_count,
        "metrics": metrics,
    }
