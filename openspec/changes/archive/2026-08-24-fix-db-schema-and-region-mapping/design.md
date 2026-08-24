## Context

当前系统使用 PostgreSQL + PostGIS 存储土壤数据。`parcel_info` 表的 `soil_indicators` JSON 字段存储地块指标，供 Model-1~5 查询使用。Model-4（酸化防治）需 `exchangeable_hydrogen`、`exchangeable_aluminum`、`target_ph`、`fertilizer_type` 等字段；Model-5（肥力评价）需 `total_n`（全氮）字段。这些字段在源数据 `F:\BaiduNetdiskDownload\耕地质量大模型` 中存在，但当前数据库模型和导入脚本均未处理。

源数据包含多个 Excel 文件：
- `04_乐昌市土壤三普表层土点数据2022` (27 列，含 pH/CEC/SOM/TN/AP/AK 等)
- `05_乐昌市土壤三普剖面理化和基本数据2022` (剖面数据，含交换性氢离子/交换性铝离子/交换性酸总量/全氮等 Model-4 关键字段)
- `07_乐昌市土壤三普立地条件2022` (立地条件)

区域代码映射表 `AREA_TO_REGION` 仅配置了 `440281`（乐昌），未覆盖 `440233`（新丰县），导致新丰县地块的 Model-1/2/3 计算使用默认系数而非正确的南岭丘陵参数。

## Goals / Non-Goals

**Goals:**
- 扩展 `ThirdSurveyTopsoil` 和 `ThirdSurveyProfile` SQLAlchemy 模型，新增 Model-4/5 必需字段
- 更新导入脚本，从源 Excel 解析并填充新增字段值
- 创建 `area_code_region_map` 数据库表，将区域代码映射从硬编码字典迁移到数据库存储
- 实现 `get_region_mapping(area_code)` 服务层，支持 DB 查询 + 缓存 + 回退机制
- 修改 `parcel_info` 导入逻辑，使 `soil_indicators` JSON 包含 Model-4/5 所需全部指标
- 确保 Model-4 和 Model-5 的 parcel 数据查询能正确获取 `exchangeable_hydrogen`、`exchangeable_aluminum`、`total_n` 等字段

**Non-Goals:**
- 不修改 Model-4/5 的计算算法本身
- 不处理 `target_ph` 和 `fertilizer_type` 的自动计算逻辑（这些由 Model-4 逻辑层处理）
- 不对非粤北区域的区域代码进行配置

## Decisions

### Decision 1: 扩展现有表而非新建表

在 `third_survey_topsoils` 和 `third_survey_profiles` 表中直接新增列，而非创建新的关联表。

**选择的做法:** 在现有模型定义中添加新列，使用 `ALTER TABLE` 迁移或通过 `init_db.py` 重新建表。

**替代方案:** 创建新的 `model4_indicators` 关联表 → 增加 JOIN 查询复杂度，且现有数据均为一对一关系，没有必要拆分。

### Decision 2: 源数据列名→V3.0 字段映射

**`05_乐昌市土壤三普剖面理化和基本数据2022`** 表头关键字段映射：

| 源列名 | V3.0 字段名 | 用途 |
|--------|------------|------|
| 交换性氢离子 | exchangeable_hydrogen | Model-4 |
| 交换性铝离子 | exchangeable_aluminum | Model-4 |
| 交换性酸总量 | exchangeable_acid_total | Model-4 |
| 水解性总酸度 | hydrolytic_total_acidity | Model-4 |
| pH | soil_ph | Model-4/5 |
| 全氮 | total_n | Model-5 |
| 有机质 | organic_matter | Model-5 |
| 有效磷 | available_phosphorus | Model-5 |

**`04_乐昌市土壤三普表层土点数据2022`** 表头关键字段映射：

| 源列名 | V3.0 字段名 | 用途 |
|--------|------------|------|
| pH | soil_ph | Model-4/5 |
| SOM | organic_matter | Model-5 |
| TN | total_n | Model-5 |
| AP | available_phosphorus | Model-5 |
| AK | available_potassium | Model-5 |
| CEC | cation_exchange_capacity | 通用 |

**选择的做法:** 使用 `05_` 剖面数据作为 Model-4 指标的主要数据源，因为其包含交换性氢离子和交换性铝离子字段。使用 `04_` 表层土数据作为 Model-5 指标的补充数据源。

**替代方案:** 仅使用 `04_` 表层土数据 → 缺少交换性氢离子/铝离子等关键 Model-4 字段。

### Decision 3: 区域代码映射采用数据库表而非硬编码

将区域代码映射从 `coefficients.py` 中的硬编码字典 `AREA_TO_REGION` 迁移到独立的 `area_code_region_map` 数据库表。

**表结构:**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| area_code | String(10) UK | 行政区划代码，如 "440281" |
| region_name | String(64) | 行政区名称，如 "乐昌市" |
| primary | String(10) | 一级农业区代码（HN/CJ） |
| secondary | String(10) | 二级农业区代码（MNY/YXG/QN/NL） |
| ejnyq_idx | Integer | 二级农业区索引（0-3） |
| enabled | Boolean | 是否启用，默认 true |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**服务层设计（参照 `exclusive_rules.py` 模式）:**

```python
# framework/domain/calculations/region_mapping_service.py

_cache: Optional[Dict[str, dict]] = None

def get_region_mapping(area_code: str) -> dict:
    """优先 DB 缓存 → 回退硬编码 → 默认值"""
    mapping = _load_cache().get(area_code)
    if mapping:
        return mapping
    mapping = AREA_TO_REGION.get(area_code)
    if mapping:
        return mapping
    return {"primary": "HN", "secondary": "MNY", "ejnyq_idx": 0}

def _load_cache() -> Dict[str, dict]:
    global _cache
    if _cache is None:
        try:
            rows = db.session.query(AreaCodeRegionMap).filter_by(enabled=True).all()
            _cache = {r.area_code: {"primary": r.primary, "secondary": r.secondary, "ejnyq_idx": r.ejnyq_idx} for r in rows}
        except Exception:
            _cache = {}
    return _cache

def refresh_region_cache() -> None:
    global _cache
    _cache = None
```

**消费者更新:** `grade_calculation.py`、`obstacle_calculation.py`、`stability_calculation.py` 从 `AREA_TO_REGION.get(area_code, ...)` 改为调用 `get_region_mapping(area_code)`。

**选择的做法:** 数据库表 + 模块级缓存 + 硬编码回退的三层架构。

**替代方案:**
1. 仅硬编码字典 → 新增区域代码需修改 Python 文件并重启，运维不便
2. 仅数据库查询 → 高频调用性能差，无缓存每次查库
3. 数据库 + 缓存（所选）→ 平衡性能与可维护性

### Decision 4: 导入脚本修改策略

**`import_real_parcels.py`（parcel_info 导入）:**
- 修改 `FIELD_MAP` 添加 Model-4/5 所需字段
- 在 `build_soil_indicators()` 中增加对 `exchangeable_hydrogen`、`exchangeable_aluminum`、`total_n` 的映射
- 若 shp 文件中无这些字段（目前看 `2024_测试数据.shp` 的字段只有 TYBH/DLMC/SJD/YJZ 等拼音缩写），则需从剖面/表层土 Excel 中按样点编号或地理位置关联补充

**选择的做法:** 分两步导入：先导入 Excel 数据到 `third_survey_*` 表，再修改 `parcel_info.soil_indicators` 从 `third_survey_*` 表按地理坐标或行政区域关联补充 Model-4/5 指标。

**替代方案:** 仅从 shp 数据导入 → 缺少 Model-4 所需的交换性氢离子/铝离子字段。

### Decision 5: 数据库迁移方式

由于使用 PostgreSQL + PostGIS，且当前为开发阶段，采用 `DROP TABLE + CREATE TABLE` 的重建方式（开发环境可接受数据重建）。

**选择的做法:** 删除旧表（如存在）→ 重新建表 → 重新导入全部数据。

**替代方案:** 使用 Alembic 迁移脚本 → 生产环境需要，但当前开发阶段重建更简单。

## Risks / Trade-offs

- **[数据源匹配风险]** 剖面理化数据的 `样点编号` 与表层土的 `ID` 可能不完全对应 → 先用行政区域+坐标关联，或通过土壤普查样点编号匹配。需验证两套数据的点位编号关系。
- **[字段为空值]** 部分点位可能缺少 Model-4/5 指标 → 允许 NULL，模型计算时降级处理（已有机制）
- **[区域代码正确性]** 440233 是否确实属于南岭丘陵区需农业区划专家确认 → 若有误，修改映射表即可，不影响架构
- **[数据量]** 5488 个 parcels 关联 217 条剖面数据可能存在一对多或缺失 → 使用最近邻匹配或行政区域匹配，并记录日志
- **[导入耗时]** 重新导入 3 个数据源 + parcel 数据约需 5-10 分钟 → 可接受，一次性操作

## Migration Plan

1. 备份现有数据库数据
2. 创建 `AreaCodeRegionMap` SQLAlchemy 模型（`framework/models/thematic_model.py`）
3. 实现区域映射服务层 `region_mapping_service.py`
4. 修改 SQLAlchemy 模型（`soil_data.py`）添加新字段
5. 重建数据库表（`init_db.py`）
6. 初始化 `area_code_region_map` 表数据（插入 440281、440233 映射）
7. 实现/更新导入脚本，从 Excel 重新导入土壤数据
8. 执行 `import_real_parcels.py` 重新导入 parcels
9. 编写数据关联脚本，从 `third_survey_*` 表补充 `parcel_info.soil_indicators` 中的 Model-4/5 指标
10. 更新消费者代码（grade_calculation / obstacle_calculation / stability_calculation）使用 `get_region_mapping()`
11. 验证 Model-4 和 Model-5 查询结果

**回滚策略:** 保留原数据库备份，可随时恢复。

## Resolved Questions (from data exploration)

通过 Python 探查数据源，已解决以下问题：

### Q1: 剖面数据与表层土数据关联策略
**结论**: 两套数据无直接 ID 对应关系，但行政区划均为"乐昌市"。采用按行政区划批量填充策略。

- `05_` 剖面数据（216 条）：样品编号格式 `240321162167b11`，包含 Model-4 所需全部字段（交换性氢离子、交换性铝离子、全氮等）
- `04_` 表层土数据（649 条）：ID 格式 `231030049540b01`，包含 pH、SOM、TN、AP、AK、CEC 等常规指标
- 两套数据行政区域均为"乐昌市"，但 ID 不同源
- **决策**: `05_` 数据（216 条）导入 `third_survey_profiles` 表作为 Model-4 指标的样本数据；`04_` 数据（649 条）作为 Model-5 的常规指标补充。由于剖面数据量（216）远少于 parcels 数量（5488），`soil_indicators` 中的 Model-4 指标字段（exchangeable_hydrogen、exchangeable_aluminum 等）**仅对有剖面数据支撑的地块填充**，其他地块的这些字段保持 null，Model-4 计算时按已有降级机制处理。

### Q2: `target_ph` 和 `fertilizer_type` 默认值
**结论**: 源数据（`03_` 测土配方、`04_` 表层土、`05_` 剖面、`07_` 立地条件）均未包含 `target_ph` 或 `fertilizer_type` 字段。

- **决策**:
  - `target_ph`（目标 pH）: 设为 `6.5`（广东省耕地一般目标值）
  - `fertilizer_type`（肥料类型）: 设为 `"compound"`（通用复合肥）
  - 这两个字段在 `parcel_info.soil_indicators` 中设默认值，后续可通过 Model-4 交互接口让用户调整

### Q3: Model-4 数据查询路径
**结论**: Model-4 应统一从 `parcel_info.soil_indicators` JSON 查询，不直接读 `third_survey_profiles` 表。

- **决策**: Model-4 的 `parcel_data_accessor` 从 `parcel_info` 表读取 `soil_indicators` JSON 字段，获取 `exchangeable_hydrogen`、`exchangeable_aluminum`、`soil_ph` 等。`third_survey_profiles` 表仅作为数据存储和查询备用，不直接与模型计算耦合。
