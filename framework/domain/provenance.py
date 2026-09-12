"""地块指标来源标注与回填识别。

`parcel_info.soil_indicators` 是 JSON 快照，历史上由两类脚本写入：

1. 地块级映射（``scripts/import_real_parcels.py``）：来自地块 shp 的指标；
2. 区域平均回填（``scripts/link_soil_indicators.py``）：把三普采样表的平均值
   批量写入所有地块，用于补齐 Model-4/5 需要的字段；
3. 少量固定默认值（同导入脚本写入的 ``target_ph``、``fertilizer_type``）。

来源是**写入方的事实**，不是数据的统计特征。因此本模块用一份声明式台账
（``SOURCE_MANIFEST``）记录“谁写了什么”，而不是根据数值分布去反推：分布层面
既会把源数据本身的常量误判为回填，也无法恢复“同一字段在不同地块可能是实测、
也可能是平均填充”这种逐地块事实。

来源取值：

- ``measured``：由地块级来源数据映射得到；
- ``region_mean_backfill``：由区域/全局平均值批量回填；
- ``default``：代码默认值或模板值。

未出现在来源标记中的字段视为**来源未知**，不得当作实测值使用。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

PROVENANCE_KEY = "provenance"

SOURCE_MEASURED = "measured"
SOURCE_REGION_MEAN_BACKFILL = "region_mean_backfill"
SOURCE_DEFAULT = "default"

SOURCES = (SOURCE_MEASURED, SOURCE_REGION_MEAN_BACKFILL, SOURCE_DEFAULT)
IMPUTED_SOURCES = frozenset({SOURCE_REGION_MEAN_BACKFILL, SOURCE_DEFAULT})

#: 统一问题码：模型输入中包含回填或默认取值。
IMPUTED_INPUT = "IMPUTED_INPUT"

#: 由 ``scripts/import_real_parcels.py`` 从 2024 年测试地块 shp 逐地块映射的字段。
MEASURED_FIELDS: tuple[str, ...] = (
    "soil_ph",
    "organic_matter",
    "available_phosphorus",
    "available_potassium",
    "bulk_density",
    "topsoil_thickness",
    "plow_layer_thickness",
    "soil_texture",
    "irrigation_condition",
    "drainage_capacity",
    "terrain_position",
    "soil_structure",
    "quality_grade",
)

#: 由 ``scripts/link_soil_indicators.py`` 用三普采样表平均值批量填充的字段。
#:
#: 该脚本只填充缺失字段，因此这些字段的取值不是地块实测值。当前填充口径是
#: **全局平均**（脚本注释写作“按行政区域”，实现未按区域分组）。
BACKFILLED_FIELDS: tuple[str, ...] = (
    "exchangeable_hydrogen",
    "exchangeable_aluminum",
    "exchangeable_acid_total",
    "hydrolytic_total_acidity",
    "total_n",
    "cation_exchange_capacity",
)

#: 由导入脚本写入的固定默认值。
DEFAULT_FIELDS: tuple[str, ...] = (
    "target_ph",
    "fertilizer_type",
)

#: 声明式来源台账：字段 -> 来源。唯一事实来源，供标注脚本与守卫使用。
SOURCE_MANIFEST: dict[str, str] = {
    **{field: SOURCE_MEASURED for field in MEASURED_FIELDS},
    **{field: SOURCE_REGION_MEAN_BACKFILL for field in BACKFILLED_FIELDS},
    **{field: SOURCE_DEFAULT for field in DEFAULT_FIELDS},
}

#: 来源台账的依据说明（写入文档与脚本输出）。
MANIFEST_BASIS: tuple[tuple[str, str], ...] = (
    ("measured", "scripts/import_real_parcels.py 从 2024_测试数据.shp 逐地块映射"),
    ("region_mean_backfill", "scripts/link_soil_indicators.py 用三普采样表平均值批量填充缺失字段"),
    ("default", "import_real_parcels.py 写入的固定默认值（target_ph=6.5、fertilizer_type=compound）"),
)

#: Model-5 必填特征 -> soil_indicators 字段
#:
#: 注意 ``TN`` 取自 ``total_nitrogen``（见 ParcelDataAccessor 的 model-5 映射），
#: 而不是 ``link_soil_indicators.py`` 回填的 ``total_n``；两者字段名不一致的问题
#: 见本 change 的 Open Questions。测试 test_model5_feature_sources_match_accessor
#: 用于防止后续再次漂移。
MODEL5_FEATURE_SOURCES: dict[str, str] = {
    "pH": "soil_ph",
    "SOMbe": "organic_matter",
    "AK": "available_potassium",
    "AP": "available_phosphorus",
    "TN": "total_nitrogen",
}

#: Model-4 过程模型输入 -> soil_indicators 字段
MODEL4_INPUT_SOURCES: dict[str, str] = {
    "SJD": "soil_ph",
    "Hex": "exchangeable_hydrogen",
    "Alex": "exchangeable_aluminum",
}

#: Model-4 的上下文参数（不是 soil_indicators 字段，缺失即按默认值处理）
MODEL4_CONTEXT_INPUTS = ("target_ph", "fertilizer_type")


def manifest_for(fields: Optional[Iterable[str]] = None) -> dict[str, str]:
    """返回来源台账（可按字段筛选），用于标注脚本写入。"""
    if fields is None:
        return dict(SOURCE_MANIFEST)
    return {field: SOURCE_MANIFEST[field] for field in fields if field in SOURCE_MANIFEST}


def declared_source(field: str) -> Optional[str]:
    """台账声明的来源；未在台账中的字段返回 ``None``。"""
    return SOURCE_MANIFEST.get(field)


def provenance_map(indicators: Optional[Mapping[str, Any]]) -> dict[str, str]:
    """读取指标快照中的来源标记；缺失或格式异常时返回空字典。"""
    if not isinstance(indicators, Mapping):
        return {}
    raw = indicators.get(PROVENANCE_KEY)
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def source_of(indicators: Optional[Mapping[str, Any]], field: str) -> Optional[str]:
    """返回字段的来源标记，未标注时返回 ``None``（来源未知）。"""
    return provenance_map(indicators).get(field)


def is_imputed(indicators: Optional[Mapping[str, Any]], field: str) -> bool:
    """字段是否来自回填或默认值。来源未知按“未知”处理，不作为回填判定。"""
    return source_of(indicators, field) in IMPUTED_SOURCES


def imputed_fields(
    indicators: Optional[Mapping[str, Any]],
    fields: Optional[Iterable[str]] = None,
) -> list[str]:
    """列出被回填或被默认的字段，保持传入顺序。"""
    candidates = list(fields) if fields is not None else sorted(provenance_map(indicators))
    return [field for field in candidates if is_imputed(indicators, field)]


def imputed_feature_names(
    indicators: Optional[Mapping[str, Any]],
    feature_sources: Mapping[str, str],
) -> list[str]:
    """把“被回填的字段”映射为模型特征名，例如 ``total_n`` -> ``TN``。"""
    return [
        feature
        for feature, source_field in feature_sources.items()
        if is_imputed(indicators, source_field)
    ]
