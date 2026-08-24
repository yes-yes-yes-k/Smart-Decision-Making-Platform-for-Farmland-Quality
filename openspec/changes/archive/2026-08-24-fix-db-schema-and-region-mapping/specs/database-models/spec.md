# database-models Specification (Delta)

## MODIFIED Requirements

### Requirement: Soil Data Models

系统 SHALL 提供 8 张土壤数据的 SQLAlchemy 模型，按数据源分表存储乐昌市土壤数据。模型包括：三普表层土（ThirdSurveyTopsoil）、三普剖面理化（ThirdSurveyProfile）、三普立地条件（ThirdSurveySiteCondition）、三普容重（ThirdSurveyBulkDensity）、二普点（SecondSurveyPoint）、测土配方（FormulaFertilization）、农业化学化（AgriChemicalization）、粮食产量（GrainYield）。

#### Scenario: 三普表层土模型
- **WHEN** 数据库表被创建
- **THEN** `ThirdSurveyTopsoil` 模型 SHALL 包含 pH、有机质、有效磷、速效钾、阳离子交换量等土壤理化指标字段，并支持经纬度定位
- **AND** 扩展字段：`exchangeable_hydrogen`（Float，可 NULL）、`exchangeable_aluminum`（Float，可 NULL）、`exchangeable_acid_total`（Float，可 NULL）、`hydrolytic_total_acidity`（Float，可 NULL）、`total_n`（Float，可 NULL）

#### Scenario: 三普剖面理化模型
- **WHEN** 数据库表被创建
- **THEN** `ThirdSurveyProfile` 模型 SHALL 包含剖面深度、土壤质地、容重、孔隙度等剖面理化数据字段
- **AND** 扩展字段：`exchangeable_hydrogen`（Float，可 NULL）、`exchangeable_aluminum`（Float，可 NULL）、`exchangeable_acid_total`（Float，可 NULL）、`hydrolytic_total_acidity`（Float，可 NULL）

#### Scenario: 测土配方模型
- **WHEN** 数据库表被创建
- **THEN** `FormulaFertilization` 模型 SHALL 包含 pH、有机质、有效磷、速效钾等测土配方表层土数据字段

#### Scenario: 农业化学化模型
- **WHEN** 数据库表被创建
- **THEN** `AgriChemicalization` 模型 SHALL 包含年份、县区、化肥施用量等农业化学化指标字段

#### Scenario: 粮食产量模型
- **WHEN** 数据库表被创建
- **THEN** `GrainYield` 模型 SHALL 包含年份、县区、粮食作物播种面积、产量等字段

#### Scenario: 模型注册与建表
- **WHEN** `init_db.py` 运行 `db.create_all()`
- **THEN** 系统 SHALL 创建全部 8 张土壤数据表，表名使用复数形式（如 `third_survey_topsoils`）
- **AND** `third_survey_topsoils` 和 `third_survey_profiles` 表 SHALL 包含新增的 Model-4/5 字段

## ADDED Requirements

### Requirement: Area code region mapping model

系统 SHALL 提供 `AreaCodeRegionMap` SQLAlchemy 模型，映射行政区划代码到农业区参数。模型 SHALL 包含字段：`area_code`（String(10)，唯一约束）、`region_name`（String(64)）、`primary`（String(10)，一级农业区代码）、`secondary`（String(10)，二级农业区代码）、`ejnyq_idx`（Integer，二级农业区索引）、`enabled`（Boolean，默认 true）、`created_at`（DateTime）、`updated_at`（DateTime）。

#### Scenario: area_code_region_map 建表
- **WHEN** `init_db.py` 运行 `db.create_all()`
- **THEN** `area_code_region_map` 表 SHALL 被创建，包含上述所有字段
- **AND** `area_code` 列 SHALL 有唯一约束

#### Scenario: 初始数据
- **WHEN** 建表后执行初始化脚本
- **THEN** `area_code_region_map` 表 SHALL 包含 440281（乐昌市）和 440233（新丰县）两条映射记录
