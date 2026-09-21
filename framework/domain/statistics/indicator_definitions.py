"""Canonical indicator ranges shared by the statistics API and map legend."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable


IndicatorValue = float | str | None
ValueParser = Callable[[Any], IndicatorValue]


# Increment whenever public metric labels, grouping, ranges or colors change.
CLASSIFICATION_VERSION = "2026-09-21.1"


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


def _to_string(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(items) or None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class IndicatorGroup:
    key: str
    label: str
    order: int
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "order": self.order,
            "description": self.description,
        }


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
    group_key: str
    order: int
    value_type: str = "number"
    parser: ValueParser = _to_float
    source_aliases: tuple[str, ...] = ()
    availability_note: str | None = None

    def parse(self, value: Any) -> IndicatorValue:
        return self.parser(value)

    def classify(self, value: Any) -> BucketDefinition | None:
        parsed = self.parse(value)
        if parsed is None or not isinstance(parsed, (int, float)):
            return None
        return next((bucket for bucket in self.buckets if bucket.contains(parsed)), None)

    def value_from(self, indicators: dict[str, Any]) -> Any:
        for field in (self.source_field, *self.source_aliases):
            value = indicators.get(field)
            if value is not None and value != "":
                return value
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "sourceField": self.source_field,
            "sourceAliases": list(self.source_aliases),
            "unit": self.unit,
            "decimals": self.decimals,
            "groupKey": self.group_key,
            "order": self.order,
            "valueType": self.value_type,
            "aggregatable": self.value_type in {"number", "category"},
            "availabilityNote": self.availability_note,
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


INDICATOR_GROUPS: tuple[IndicatorGroup, ...] = (
    IndicatorGroup("quality_evaluation", "质量评价", 10, "耕地质量等级、综合指数及主要限制因素"),
    IndicatorGroup("soil_nutrients", "土壤养分", 20, "有机质、全氮、有效磷和速效钾"),
    IndicatorGroup("physical_properties", "理化性质", 30, "土壤 pH、容重、厚度和质地"),
    IndicatorGroup("pollution_status", "污染状况", 40, "重金属、其他污染物及风险筛查结果"),
    IndicatorGroup("farmland_conditions", "农田条件", 50, "灌排、坡度和田间基础设施"),
)


INDICATOR_DEFINITIONS: dict[str, IndicatorDefinition] = {
    "quality_grade": IndicatorDefinition(
        key="quality_grade",
        label="耕地质量等级",
        source_field="quality_grade",
        unit="等",
        decimals=1,
        group_key="quality_evaluation",
        order=10,
        parser=_quality_grade,
        buckets=tuple(
            _bucket(
                f"grade_{grade}", f"{grade}等", f"{grade}等", QUALITY_COLORS[grade - 1],
                float(grade), float(grade), lower_inclusive=True, upper_inclusive=True,
            )
            for grade in range(1, 11)
        ),
    ),
    "composite_index": IndicatorDefinition(
        key="composite_index", label="综合指数", source_field="composite_index", unit="", decimals=4,
        group_key="quality_evaluation", order=20, buckets=(),
        availability_note="历史年度快照中的综合质量指数；未配置统一分级阈值。",
    ),
    "limiting_factors": IndicatorDefinition(
        key="limiting_factors", label="主要限制因素", source_field="limiting_factors", unit="", decimals=0,
        group_key="quality_evaluation", order=30, value_type="category", parser=_to_string, buckets=(),
        source_aliases=("primary_factors",),
        availability_note="仅在已写入障碍诊断结果的地块可用。",
    ),
    "soil_ph": IndicatorDefinition(
        key="soil_ph", label="土壤 pH", source_field="soil_ph", unit="pH", decimals=2,
        group_key="physical_properties", order=10,
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
        group_key="soil_nutrients", order=10,
        buckets=(
            _bucket("low", "低", "(0,10]", "#D73027", 0, 10, upper_inclusive=True),
            _bucket("medium_low", "中低", "(10,20]", "#FC8D59", 10, 20, upper_inclusive=True),
            _bucket("medium_high", "中高", "(20,25]", "#FEE08B", 20, 25, upper_inclusive=True),
            _bucket("high", "高", "(25,+∞)", "#1A9850", lower=25),
        ),
    ),
    "total_nitrogen": IndicatorDefinition(
        key="total_nitrogen", label="全氮含量", source_field="total_nitrogen", unit="g/kg", decimals=3,
        group_key="soil_nutrients", order=20, source_aliases=("total_n",), buckets=(),
        availability_note="兼容历史字段 total_n；未配置统一分级阈值。",
    ),
    "available_phosphorus": IndicatorDefinition(
        key="available_phosphorus", label="有效磷含量", source_field="available_phosphorus", unit="mg/kg", decimals=2,
        group_key="soil_nutrients", order=30,
        buckets=(
            _bucket("low", "低", "(0,10]", "#D73027", 0, 10, upper_inclusive=True),
            _bucket("medium_low", "中低", "(10,20]", "#FC8D59", 10, 20, upper_inclusive=True),
            _bucket("medium_high", "中高", "(20,35]", "#FEE08B", 20, 35, upper_inclusive=True),
            _bucket("high", "高", "(35,+∞)", "#1A9850", lower=35),
        ),
    ),
    "available_potassium": IndicatorDefinition(
        key="available_potassium", label="速效钾含量", source_field="available_potassium", unit="mg/kg", decimals=2,
        group_key="soil_nutrients", order=40,
        buckets=(
            _bucket("low", "低", "(0,50]", "#D73027", 0, 50, upper_inclusive=True),
            _bucket("medium_low", "中低", "(50,100]", "#FC8D59", 50, 100, upper_inclusive=True),
            _bucket("medium_high", "中高", "(100,150]", "#FEE08B", 100, 150, upper_inclusive=True),
            _bucket("high", "高", "(150,+∞)", "#1A9850", lower=150),
        ),
    ),
    "bulk_density": IndicatorDefinition(
        key="bulk_density", label="土壤容重", source_field="bulk_density", unit="g/cm³", decimals=2,
        group_key="physical_properties", order=20,
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
        group_key="physical_properties", order=30,
        buckets=(
            _bucket("very_low", "极低", "(0,10]", "#D73027", 0, 10, upper_inclusive=True),
            _bucket("low", "低", "(10,15]", "#FC8D59", 10, 15, upper_inclusive=True),
            _bucket("medium", "中", "(15,20)", "#FEE08B", 15, 20),
            _bucket("high", "高", "[20,+∞)", "#1A9850", lower=20, lower_inclusive=True),
        ),
    ),
    "effective_soil_depth": IndicatorDefinition(
        key="effective_soil_depth", label="有效土层厚度", source_field="effective_soil_depth", unit="cm", decimals=2,
        group_key="physical_properties", order=40, source_aliases=("topsoil_thickness",),
        buckets=(
            _bucket("very_low", "极低", "(0,60)", "#D73027", 0, 60),
            _bucket("low", "低", "[60,80)", "#FC8D59", 60, 80, lower_inclusive=True),
            _bucket("medium", "中", "[80,100)", "#FEE08B", 80, 100, lower_inclusive=True),
            _bucket("high", "高", "[100,+∞)", "#1A9850", lower=100, lower_inclusive=True),
        ),
    ),
    "soil_texture": IndicatorDefinition(
        key="soil_texture", label="土壤质地", source_field="soil_texture", unit="", decimals=0,
        group_key="physical_properties", order=50, value_type="category", parser=_to_string, buckets=(),
    ),
    "cadmium": IndicatorDefinition(
        key="cadmium", label="镉", source_field="cadmium", unit="mg/kg", decimals=3,
        group_key="pollution_status", order=10, source_aliases=("cd",), buckets=(),
        availability_note="仅在导入污染物监测数据后可用；风险判定需结合现行标准。",
    ),
    "mercury": IndicatorDefinition(
        key="mercury", label="汞", source_field="mercury", unit="mg/kg", decimals=3,
        group_key="pollution_status", order=20, source_aliases=("hg",), buckets=(),
        availability_note="仅在导入污染物监测数据后可用；风险判定需结合现行标准。",
    ),
    "arsenic": IndicatorDefinition(
        key="arsenic", label="砷", source_field="arsenic", unit="mg/kg", decimals=3,
        group_key="pollution_status", order=30, source_aliases=("as",), buckets=(),
        availability_note="仅在导入污染物监测数据后可用；风险判定需结合现行标准。",
    ),
    "lead": IndicatorDefinition(
        key="lead", label="铅", source_field="lead", unit="mg/kg", decimals=3,
        group_key="pollution_status", order=40, source_aliases=("pb",), buckets=(),
        availability_note="仅在导入污染物监测数据后可用；风险判定需结合现行标准。",
    ),
    "chromium": IndicatorDefinition(
        key="chromium", label="铬", source_field="chromium", unit="mg/kg", decimals=3,
        group_key="pollution_status", order=50, source_aliases=("cr",), buckets=(),
        availability_note="仅在导入污染物监测数据后可用；风险判定需结合现行标准。",
    ),
    "pollution_risk": IndicatorDefinition(
        key="pollution_risk", label="污染风险筛查结果", source_field="pollution_risk", unit="", decimals=0,
        group_key="pollution_status", order=60, value_type="category", parser=_to_string, buckets=(),
        availability_note="只展示已入库的风险筛查结论，不根据缺失监测值推断。",
    ),
    "irrigation_condition": IndicatorDefinition(
        key="irrigation_condition", label="灌溉条件", source_field="irrigation_condition", unit="", decimals=0,
        group_key="farmland_conditions", order=10, value_type="category", parser=_to_string, buckets=(),
        source_aliases=("irrigation_capacity",),
    ),
    "drainage_capacity": IndicatorDefinition(
        key="drainage_capacity", label="排水能力", source_field="drainage_capacity", unit="", decimals=0,
        group_key="farmland_conditions", order=20, value_type="category", parser=_to_string, buckets=(),
    ),
    "slope": IndicatorDefinition(
        key="slope", label="坡度", source_field="slope", unit="°", decimals=2,
        group_key="farmland_conditions", order=30, buckets=(),
        availability_note="未配置统一分级阈值。",
    ),
    "infrastructure": IndicatorDefinition(
        key="infrastructure", label="田间基础设施", source_field="infrastructure", unit="", decimals=0,
        group_key="farmland_conditions", order=40, value_type="category", parser=_to_string, buckets=(),
    ),
}


def get_indicator_definition(key: str) -> IndicatorDefinition:
    try:
        return INDICATOR_DEFINITIONS[key]
    except KeyError as exc:
        raise ValueError(f"不支持的统计指标: {key}") from exc


def classify_indicator(key: str, value: Any) -> BucketDefinition | None:
    return get_indicator_definition(key).classify(value)
