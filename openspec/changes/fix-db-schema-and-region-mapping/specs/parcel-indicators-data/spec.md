# parcel-indicators-data Specification

## Purpose

Define the structure and content requirements for parcel soil indicators stored in `parcel_info.soil_indicators` JSON field, ensuring all thematic models (especially Model-4 acidification and Model-5 fertility) can query the complete set of required indicators.

## ADDED Requirements

### Requirement: Parcel soil indicators completeness

`parcel_info` 表的 `soil_indicators` JSON 字段 SHALL 包含所有主题模型计算所需的土壤指标。指标按 V3.0 snake_case 命名规范存储。

#### Scenario: Model-1/2/3 指标可用
- **WHEN** 从 `parcel_info` 查询地块数据用于 Model-1/2/3 计算
- **THEN** `soil_indicators` SHALL 包含：`soil_ph`, `organic_matter`, `available_phosphorus`, `available_potassium`, `bulk_density`, `topsoil_thickness`, `plow_layer_thickness`, `soil_texture`, `irrigation_condition`, `drainage_capacity`, `terrain_position`, `soil_structure`

#### Scenario: Model-4 酸化模型指标可用
- **WHEN** 从 `parcel_info` 查询地块数据用于 Model-4 酸化防治计算
- **THEN** `soil_indicators` SHALL 包含：`soil_ph`, `exchangeable_hydrogen`, `exchangeable_aluminum`, `target_ph`, `fertilizer_type`, `land_type`
- **AND** 以上字段值 SHALL 从 `third_survey_profiles` 或 `third_survey_topsoils` 数据源中解析后写入

#### Scenario: Model-5 肥力评价指标可用
- **WHEN** 从 `parcel_info` 查询地块数据用于 Model-5 肥力评价计算
- **THEN** `soil_indicators` SHALL 包含：`soil_ph`, `organic_matter`, `available_potassium`, `available_phosphorus`, `total_n`
- **AND** `total_n`（全氮）值 SHALL 从 `third_survey_profiles` 数据源的全氮字段解析写入

#### Scenario: 指标值缺失处理
- **WHEN** 某个指标在源数据中不存在
- **THEN** `soil_indicators` 中对应字段 SHALL 被省略或设为 null
- **AND** 模型计算 SHALL 能容忍缺失值并按规范降级处理

### Requirement: Indicator naming convention

所有指标 SHALL 使用 V3.0 English snake_case 命名，与 `FIELD_MAP` 映射表一致。禁止使用 V2.0 拼音缩写（SJD/YJZ/YTK/hex/alex 等）。

#### Scenario: 命名规范验证
- **WHEN** 检查 `soil_indicators` JSON 键名
- **THEN** 所有键名 SHALL 使用 snake_case 格式，如 `soil_ph` 而非 `SJD`、`organic_matter` 而非 `YJZ`

### Requirement: Indicator data sources

不同指标从不同数据源解析写入：

| 指标 | 数据源文件 | 源列名 |
|------|-----------|--------|
| `soil_ph` | 剖面理化/表层土 | pH |
| `exchangeable_hydrogen` | 剖面理化 | 交换性氢离子 |
| `exchangeable_aluminum` | 剖面理化 | 交换性铝离子 |
| `exchangeable_acid_total` | 剖面理化 | 交换性酸总量 |
| `total_n` | 剖面理化 | 全氮 |
| `organic_matter` | 剖面理化/表层土 | 有机质 |
| `available_phosphorus` | 表层土 | AP |
| `available_potassium` | 表层土 | AK |

#### Scenario: 数据源解析正确性
- **WHEN** 从 Excel 源文件导入数据
- **THEN** 每个指标 SHALL 从正确的源列名解析并映射到 V3.0 字段名

### Requirement: Land type classification

`land_type` SHALL 从源数据的地类字段解析，分类为 `paddy`（水田）或 `upland`（旱地）。

#### Scenario: 地类映射
- **WHEN** 源数据地类为 "水田"
- **THEN** `land_type` SHALL 为 "paddy"
- **WHEN** 源数据地类为 "旱地" 或 "水浇地"
- **THEN** `land_type` SHALL 为 "upland"

## MODIFIED Requirements

### Requirement: Soil Data Import

系统 SHALL 提供导入脚本，从 `F:\BaiduNetdiskDownload\耕地质量大模型` 目录的 Excel 文件批量导入乐昌市土壤数据到数据库，按数据源分表存储。导入的数据源包括：三普表层土、三普剖面理化、三普立地条件、三普容重、二普点、测土配方、农业化学化、粮食产量。导入脚本 SHALL 在 `third_survey_topsoils` 和 `third_survey_profiles` 表中新增以下列：`exchangeable_hydrogen`（交换性氢离子）、`exchangeable_aluminum`（交换性铝离子）、`exchangeable_acid_total`（交换性酸总量）、`hydrolytic_total_acidity`（水解性总酸度）、`total_n`（全氮）。

#### Scenario: 成功导入所有数据源
- **WHEN** 运行土壤数据导入脚本且源目录文件齐全
- **THEN** 系统 SHALL 将所有数据源的数据分别导入到对应的数据库表，每张表行数大于 0
- **AND** `third_survey_profiles` 表的 `exchangeable_hydrogen`、`exchangeable_aluminum`、`total_n` 字段 SHALL 有值（非全 NULL）

#### Scenario: 部分数据文件缺失
- **WHEN** 运行导入脚本且部分 Excel 文件缺失
- **THEN** 系统 SHALL 跳过缺失文件的数据源，记录 warning 日志，继续导入其他可用数据源

#### Scenario: 列名映射处理
- **WHEN** Excel 文件的中文列名与数据库字段名不一致
- **THEN** 导入脚本 SHALL 使用硬编码列名映射表将中文列名转换为英文字段名，缺失列允许 NULL 值

### Requirement: Parcel data import with full indicators

系统 SHALL 在导入 `parcel_info` 时，将 Model-4/5 所需的指标（`exchangeable_hydrogen`、`exchangeable_aluminum`、`total_n` 等）写入 `soil_indicators` JSON 字段。若 shp 源文件无这些字段，系统 SHALL 从 `third_survey_*` 表按坐标或行政区域关联补充。

#### Scenario: Parcel 数据包含 Model-4 指标
- **WHEN** 5488 个 parcel 被导入
- **THEN** 至少 90% 的 parcel 的 `soil_indicators` SHALL 包含 `exchangeable_hydrogen` 字段（值非 null）
- **AND** 至少 90% 的 parcel 的 `soil_indicators` SHALL 包含 `exchangeable_aluminum` 字段

#### Scenario: Parcel 数据包含 Model-5 指标
- **WHEN** 5488 个 parcel 被导入
- **THEN** 至少 90% 的 parcel 的 `soil_indicators` SHALL 包含 `total_n`（全氮）字段
- **AND** `organic_matter`、`available_potassium`、`available_phosphorus` 字段 SHALL 有值
