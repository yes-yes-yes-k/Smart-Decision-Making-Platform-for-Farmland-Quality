"""Canonical indicator ranges shared by the statistics API and map legend."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable


NumberParser = Callable[[Any], float | None]


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quality_grade(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    match = re.search(r"(10|[1-9])", str(value).strip())
    return float(match.group(1)) if match else None


@dataclass(frozen=True)
class BucketDefinition:
    key: str
    label: str
    range_label: str
    color: str
    lower: float | None = None
    upper: float | None = None
    lower_inclusive: bool = False
    upper_inclusive: bool = False

    def contains(self, value: float) -> bool:
        if self.lower is not None:
            if value < self.lower or (value == self.lower and not self.lower_inclusive):
                return False
        if self.upper is not None:
            if value > self.upper or (value == self.upper and not self.upper_inclusive):
                return False
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "rangeLabel": self.range_label,
            "color": self.color,
            "lower": self.lower,
            "upper": self.upper,
            "lowerInclusive": self.lower_inclusive,
            "upperInclusive": self.upper_inclusive,
        }


@dataclass(frozen=True)
class IndicatorDefinition:
    key: str
    label: str
    source_field: str
    unit: str
    decimals: int
    buckets: tuple[BucketDefinition, ...]
    parser: NumberParser = _to_float

    def parse(self, value: Any) -> float | None:
        return self.parser(value)

    def classify(self, value: Any) -> BucketDefinition | None:
        parsed = self.parse(value)
        if parsed is None:
            return None
        return next((bucket for bucket in self.buckets if bucket.contains(parsed)), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "sourceField": self.source_field,
            "unit": self.unit,
            "decimals": self.decimals,
            "buckets": [bucket.as_dict() for bucket in self.buckets],
        }


def _bucket(
    key: str,
    label: str,
    range_label: str,
    color: str,
    lower: float | None = None,
    upper: float | None = None,
    *,
    lower_inclusive: bool = False,
    upper_inclusive: bool = False,
) -> BucketDefinition:
    return BucketDefinition(
        key=key,
        label=label,
        range_label=range_label,
        color=color,
        lower=lower,
        upper=upper,
        lower_inclusive=lower_inclusive,
        upper_inclusive=upper_inclusive,
    )


QUALITY_COLORS = (
    "#1A9850", "#45B966", "#75C96F", "#A6D96A", "#D9EF8B",
    "#FEE08B", "#FDAE61", "#F46D43", "#D73027", "#8E1B1B",
)


INDICATOR_DEFINITIONS: dict[str, IndicatorDefinition] = {
    "quality_grade": IndicatorDefinition(
        key="quality_grade",
        label="耕地质量等级",
        source_field="quality_grade",
        unit="等",
        decimals=1,
        parser=_quality_grade,
        buckets=tuple(
            _bucket(
                f"grade_{grade}", f"{grade}等", f"{grade}等", QUALITY_COLORS[grade - 1],
                float(grade), float(grade), lower_inclusive=True, upper_inclusive=True,
            )
            for grade in range(1, 11)
        ),
    ),
    "soil_ph": IndicatorDefinition(
        key="soil_ph", label="酸化 pH 情况", source_field="soil_ph", unit="pH", decimals=2,
        buckets=(
            _bucket("very_strong_acid", "极强酸性", "<4.5", "#B2182B", upper=4.5),
            _bucket("strong_acid", "强酸性", "[4.5,5.5)", "#EF8A62", 4.5, 5.5, lower_inclusive=True),
            _bucket("acid", "酸性", "[5.5,6.5)", "#FDDBC7", 5.5, 6.5, lower_inclusive=True),
            _bucket("neutral", "中性", "[6.5,7.5]", "#92C5DE", 6.5, 7.5, lower_inclusive=True, upper_inclusive=True),
            _bucket("alkaline", "碱性", ">7.5", "#2166AC", lower=7.5),
        ),
    ),
    "organic_matter": IndicatorDefinition(
        key="organic_matter", label="有机质含量", source_field="organic_matter", unit="g/kg", decimals=2,
        buckets=(
            _bucket("low", "低", "(0,10]", "#D73027", 0, 10, upper_inclusive=True),
            _bucket("medium_low", "中低", "(10,20]", "#FC8D59", 10, 20, upper_inclusive=True),
            _bucket("medium_high", "中高", "(20,25]", "#FEE08B", 20, 25, upper_inclusive=True),
            _bucket("high", "高", "(25,+∞)", "#1A9850", lower=25),
        ),
    ),
    "available_phosphorus": IndicatorDefinition(
        key="available_phosphorus", label="有效磷含量", source_field="available_phosphorus", unit="mg/kg", decimals=2,
        buckets=(
            _bucket("low", "低", "(0,10]", "#D73027", 0, 10, upper_inclusive=True),
            _bucket("medium_low", "中低", "(10,20]", "#FC8D59", 10, 20, upper_inclusive=True),
            _bucket("medium_high", "中高", "(20,35]", "#FEE08B", 20, 35, upper_inclusive=True),
            _bucket("high", "高", "(35,+∞)", "#1A9850", lower=35),
        ),
    ),
    "available_potassium": IndicatorDefinition(
        key="available_potassium", label="速效钾含量", source_field="available_potassium", unit="mg/kg", decimals=2,
        buckets=(
            _bucket("low", "低", "(0,50]", "#D73027", 0, 50, upper_inclusive=True),
            _bucket("medium_low", "中低", "(50,100]", "#FC8D59", 50, 100, upper_inclusive=True),
            _bucket("medium_high", "中高", "(100,150]", "#FEE08B", 100, 150, upper_inclusive=True),
            _bucket("high", "高", "(150,+∞)", "#1A9850", lower=150),
        ),
    ),
    "bulk_density": IndicatorDefinition(
        key="bulk_density", label="土壤容重", source_field="bulk_density", unit="g/cm³", decimals=2,
        buckets=(
            _bucket("very_low", "极低", "(0,0.9)", "#2166AC", 0, 0.9),
            _bucket("low", "低", "[0.9,0.95)", "#67A9CF", 0.9, 0.95, lower_inclusive=True),
            _bucket("slightly_low", "偏低", "[0.95,1)", "#D1E5F0", 0.95, 1, lower_inclusive=True),
            _bucket("normal", "正常", "[1,1.2]", "#A6D96A", 1, 1.2, lower_inclusive=True, upper_inclusive=True),
            _bucket("slightly_high", "偏高", "(1.2,1.3]", "#FEE08B", 1.2, 1.3, upper_inclusive=True),
            _bucket("high", "高", "(1.3,1.4]", "#FDAE61", 1.3, 1.4, upper_inclusive=True),
            _bucket("very_high", "极高", "(1.4,+∞)", "#D73027", lower=1.4),
        ),
    ),
    "plow_layer_thickness": IndicatorDefinition(
        key="plow_layer_thickness", label="耕层厚度", source_field="plow_layer_thickness", unit="cm", decimals=2,
        buckets=(
            _bucket("very_low", "极低", "(0,10]", "#D73027", 0, 10, upper_inclusive=True),
            _bucket("low", "低", "(10,15]", "#FC8D59", 10, 15, upper_inclusive=True),
            _bucket("medium", "中", "(15,20)", "#FEE08B", 15, 20),
            _bucket("high", "高", "[20,+∞)", "#1A9850", lower=20, lower_inclusive=True),
        ),
    ),
    "effective_soil_depth": IndicatorDefinition(
        key="effective_soil_depth", label="有效土层厚度", source_field="topsoil_thickness", unit="cm", decimals=2,
        buckets=(
            _bucket("very_low", "极低", "(0,60)", "#D73027", 0, 60),
            _bucket("low", "低", "[60,80)", "#FC8D59", 60, 80, lower_inclusive=True),
            _bucket("medium", "中", "[80,100)", "#FEE08B", 80, 100, lower_inclusive=True),
            _bucket("high", "高", "[100,+∞)", "#1A9850", lower=100, lower_inclusive=True),
        ),
    ),
}


def get_indicator_definition(key: str) -> IndicatorDefinition:
    try:
        return INDICATOR_DEFINITIONS[key]
    except KeyError as exc:
        raise ValueError(f"不支持的统计指标: {key}") from exc


def classify_indicator(key: str, value: Any) -> BucketDefinition | None:
    return get_indicator_definition(key).classify(value)
