"""Canonicalization rules for parcel management fields."""
from __future__ import annotations

import math
from typing import Any


CANONICAL_MANAGEMENT_FIELDS = ("land_type", "fertilizer_type", "target_ph")


def _missing(value: Any) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


def _normalized(field: str, value: Any) -> Any:
    if _missing(value):
        return None
    if field == "target_ph":
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"soil_indicators.{field} 不是有效数值") from exc
        if not math.isfinite(number):
            raise ValueError(f"soil_indicators.{field} 不是有限数值")
        return number
    return str(value).strip()


def canonicalize_parcel_management_fields(parcel: Any) -> None:
    """Promote legacy values, reject conflicts, and remove duplicate JSON keys."""
    indicators = dict(getattr(parcel, "soil_indicators", None) or {})
    changed = False
    for field in CANONICAL_MANAGEMENT_FIELDS:
        if field not in indicators:
            continue
        legacy = _normalized(field, indicators[field])
        canonical = _normalized(field, getattr(parcel, field, None))
        if canonical is None and legacy is not None:
            setattr(parcel, field, legacy)
        elif legacy is not None and canonical != legacy:
            raise ValueError(
                f"{field} 来源冲突：顶层规范字段与 soil_indicators 不一致"
            )
        indicators.pop(field)
        changed = True
    if changed:
        parcel.soil_indicators = indicators


__all__ = ("CANONICAL_MANAGEMENT_FIELDS", "canonicalize_parcel_management_fields")
