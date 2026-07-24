# Comet Design Handoff

- Change: import-lechang-soil-data
- Phase: design
- Mode: compact
- Context hash: 2403d36852be322be8040526fad7a0dd29a960f88627b1543f00a57e43adbe2e

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/import-lechang-soil-data/proposal.md

- Source: openspec/changes/import-lechang-soil-data/proposal.md
- Lines: 1-26
- SHA256: 938983bb98057efe62547f516ff1c22e7e29eb5f18f0ac1d7a16fdcfcaf84cb6

```md
## Why

当前系统的土壤数据（三普表层土、二普、测土配方等）以 Excel 文件形式存放在 `data/lechang/` 目录下，运行时由 `soil_data_loader.py` 直接读取文件；文件缺失时回退到 mock 随机数据。这导致数据无法被高效查询、过滤和关联，模型 4/5/6 在缺失文件时只能使用假数据。将乐昌市土壤数据导入数据库可建立可查询的土壤数据底座，让模型从 DB 读取真实数据而非 mock。

## What Changes

- 新增按数据源分表的土壤数据 SQLAlchemy 模型：三普表层土、三普剖面理化、三普立地条件、三普容重、二普点、测土配方、农业化学化、粮食产量
- 新增导入脚本 `scripts/import_lechang_data.py`，从 `data/lechang/` 目录的 Excel/xls 文件批量导入到数据库，支持幂等执行（先清除后导入）
- 修改 `framework/domain/data/soil_data_loader.py`，从数据库读取真实乐昌数据替代文件读取和 mock 生成逻辑
- **BREAKING**: `soil_data_loader.py` 的 `load_soil_data` 返回的数据将来自 DB 而非文件/mock，字段结构可能因数据源不同而变化

## Capabilities

### New Capabilities
- `soil-data-ingestion`: 土壤数据导入与存储能力——按数据源分表存储乐昌市土壤三普、二普、测土配方、农业化学化、粮食产量数据，提供幂等导入脚本和 DB 查询接口

### Modified Capabilities
- `database-models`: 新增土壤数据表模型（三普表层土、三普剖面理化、三普立地条件、三普容重、二普点、测土配方、农业化学化、粮食产量），扩展现有 SQLAlchemy 模型集合

## Impact

- **新增代码**: `framework/models/soil_data.py`（土壤数据模型）、`scripts/import_lechang_data.py`（导入脚本）
- **修改代码**: `framework/domain/data/soil_data_loader.py`（改为从 DB 读取）、`framework/models/__init__.py`（注册新模型）、`init_db.py`（创建新表）
- **依赖**: 需要现有的 pandas、openpyxl、SQLAlchemy 依赖，无新增第三方依赖
- **数据库**: 开发环境 SQLite (`development.db`) 新增 8 张表；生产环境 MySQL 同步建表
- **运行时影响**: 首次需运行导入脚本填充数据；导入后模型 4/5/6 读取真实乐昌数据

```

## openspec/changes/import-lechang-soil-data/design.md

- Source: openspec/changes/import-lechang-soil-data/design.md
- Lines: 1-73
- SHA256: f322ab36301be4dfcdc9de1994888b07f47ae73ea0d40c2818add0d4893747c8

```md
## Context

当前系统通过 `framework/domain/data/soil_data_loader.py` 在运行时直接读取 `data/lechang/` 目录下的 Excel 文件。文件缺失时回退到 `_generate_mock_data()` 生成随机 mock 数据。模型 4/5/6 调用 `load_soil_data()` 获取土壤理化指标。

`data/lechang/` 目录包含以下数据文件：
- 乐昌市土壤三普表层土点位数据（xlsx）
- 乐昌市三普土壤容重（xlsx）
- 乐昌市土壤三普剖面理化和基本数据（xlsx）
- 乐昌市土壤三普立地条件（xlsx）
- 乐昌市二普点数据（xlsx）
- 乐昌市测土配方表层土数据2008（xlsx）
- 各县(区)农村电气化和农业化学化情况 2020-2024（5个 xls）
- 各县(区)粮食作物播种面积和产量 2020-2024（5个 xls）

现有数据库仅含 User/Conversation/Message/Document 四张应用表，无土壤数据表。

## Goals / Non-Goals

**Goals:**
- 按数据源分表存储乐昌市土壤数据到数据库
- 提供幂等导入脚本（先清除后导入，可重复执行）
- 改造 `soil_data_loader.py` 从 DB 读取真实数据，淘汰 mock 生成逻辑

**Non-Goals:**
- 不修改六种专业模型的定义和代码逻辑（属于拆分项 B）
- 不做空间分析和 GIS 可视化
- 不训练新的 ML 模型
- 不处理韶关市级别数据（仅乐昌市）

## Decisions

### D1: 按数据源分表 vs 统一宽表
**选择**: 按数据源分表
**理由**: 各数据源字段结构差异大（三普表层土有 pH/有机质等理化指标，农业化学化有化肥施用量等社会经济指标），统一宽表会导致大量空值。分表结构清晰，各表字段独立，查询效率高。
**备选**: 统一宽表——字段稀疏，维护困难，已排除。

### D2: 导入幂等策略 — 先清除后导入
**选择**: 每次导入前先 DELETE 该表所有行，再批量 INSERT
**理由**: 实现简单，保证数据一致性，避免主键冲突。乐昌市数据量小（千级行），清除重导耗时可忽略。
**备选**: 增量导入（UPSERT）——需要唯一标识判断重复，各数据源主键定义不统一，复杂度高，排除。

### D3: soil_data_loader.py 改造 — 从 DB 读取
**选择**: 修改 `load_soil_data()` 查询 DB 表，保留 fallback 到 mock（DB 表为空时）
**理由**: 保证向后兼容——如果 DB 未导入数据，仍能降级到 mock。模型 4/5/6 调用接口不变。
**备选**: 完全移除 mock——若 DB 未初始化会导致模型报错，风险较高，排除。

### D4: 模型字段映射 — 动态列名处理
**选择**: 导入脚本中硬编码列名映射表（中文列名 → 英文字段名），缺失列允许 NULL
**理由**: Excel 文件列名含中文且不统一，需映射到 SQLAlchemy 模型的英文字段名。硬编码映射表清晰可控。
**备选**: 自动推断列名——不可靠，排除。

### D5: 数据库引擎 — 开发用 SQLite，生产用 MySQL
**选择**: 复用现有 Config 的 SQLAlchemy 配置，模型定义兼容两者
**理由**: 现有架构已支持双数据库，SQLAlchemy ORM 天然兼容。新表通过 `db.create_all()` 自动建表。

## Risks / Trade-offs

- [Excel 列名变化] → 导入脚本硬编码列名映射表，若源文件列名变化需更新映射表
- [xls 格式（非 xlsx）兼容] → 农业化学化和粮食产量文件为 .xls 格式，需确认 pandas `read_excel` 能读取（需 xlrd 引擎）
- [数据脱敏标记] → 三普/测土配方数据已脱敏（文件名含 _fake），导入后不作为生产级空间真值，在导入日志中标注
- [DB 表为空时降级] → soil_data_loader 保留 mock fallback，DB 表为空时降级到 mock，并在日志中 warning

## Migration Plan

1. 新增 `framework/models/soil_data.py` 定义 8 张表的 SQLAlchemy 模型
2. 更新 `framework/models/__init__.py` 注册新模型
3. 更新 `init_db.py` 确保 `db.create_all()` 包含新表
4. 新增 `scripts/import_lechang_data.py` 导入脚本
5. 运行 `init_db.py` 创建新表
6. 运行 `scripts/import_lechang_data.py` 导入数据
7. 修改 `soil_data_loader.py` 从 DB 读取
8. 验证模型 4/5/6 能读到真实数据
9. 回滚策略：删除新表、还原 soil_data_loader.py

```

## openspec/changes/import-lechang-soil-data/tasks.md

- Source: openspec/changes/import-lechang-soil-data/tasks.md
- Lines: 1-39
- SHA256: f586fe450fbc8423e034e58daa2b8d461b78399e9484ce965d774a27b30a443d

```md
# Tasks: import-lechang-soil-data

## 1. 土壤数据模型定义

- [ ] 1.1 分析 `data/lechang/` 各 Excel 文件的实际列名和数据类型
- [ ] 1.2 创建 `framework/models/soil_data.py`，定义 8 个 SQLAlchemy 模型（ThirdSurveyTopsoil、ThirdSurveyProfile、ThirdSurveySiteCondition、ThirdSurveyBulkDensity、SecondSurveyPoint、FormulaFertilization、AgriChemicalization、GrainYield）
- [ ] 1.3 为每个模型添加中文字段名到英文字段名的映射注释
- [ ] 1.4 更新 `framework/models/__init__.py` 注册新模型
- [ ] 1.5 更新 `init_db.py` 确保 `db.create_all()` 包含新表

## 2. 数据导入脚本

- [ ] 2.1 创建 `scripts/import_lechang_data.py` 导入脚本骨架
- [ ] 2.2 实现各数据源的 Excel 读取逻辑（含 .xls 格式兼容，需 xlrd 引擎）
- [ ] 2.3 实现中文列名到英文字段名的硬编码映射表
- [ ] 2.4 实现幂等导入逻辑（先 DELETE 后 INSERT，按数据源逐表处理）
- [ ] 2.5 添加导入日志：记录各表导入行数、跳过的缺失文件 warning、脱敏数据标注
- [ ] 2.6 添加命令行参数支持：`--area lechang`（默认）、`--dry-run` 预览模式

## 3. soil_data_loader 改造

- [ ] 3.1 修改 `framework/domain/data/soil_data_loader.py` 的 `load_soil_data()`，从 DB 查询土壤数据
- [ ] 3.2 保留 mock fallback：DB 表为空时降级到 `_generate_mock_data()`，并记录 warning
- [ ] 3.3 确保返回字典结构兼容（`third_survey`、`formula_fertilization` 键不变）

## 4. 测试

- [ ] 4.1 创建 `tests/test_soil_data_models.py` 测试模型定义和建表
- [ ] 4.2 创建 `tests/test_import_lechang_data.py` 测试导入脚本的幂等性和列名映射
- [ ] 4.3 创建 `tests/test_soil_data_loader_db.py` 测试从 DB 读取和 mock fallback 降级
- [ ] 4.4 运行全量测试确保不破坏现有功能

## 5. 集成验证

- [ ] 5.1 运行 `init_db.py` 创建新表
- [ ] 5.2 运行 `scripts/import_lechang_data.py` 导入乐昌数据
- [ ] 5.3 验证 `load_soil_data()` 返回真实数据（非 mock）
- [ ] 5.4 验证模型 4/5/6 能读到真实乐昌数据
- [ ] 5.5 验证重复执行导入脚本不产生重复数据

```

## openspec/changes/import-lechang-soil-data/specs/database-models/spec.md

- Source: openspec/changes/import-lechang-soil-data/specs/database-models/spec.md
- Lines: 1-28
- SHA256: 87e20d59fa5dcc90eba21ec665acea74bc046ab77b4a19c45488e0bee036fde4

```md
## ADDED Requirements

### Requirement: Soil Data Models
系统 SHALL 提供 8 张土壤数据的 SQLAlchemy 模型，按数据源分表存储乐昌市土壤数据。模型包括：三普表层土（ThirdSurveyTopsoil）、三普剖面理化（ThirdSurveyProfile）、三普立地条件（ThirdSurveySiteCondition）、三普容重（ThirdSurveyBulkDensity）、二普点（SecondSurveyPoint）、测土配方（FormulaFertilization）、农业化学化（AgriChemicalization）、粮食产量（GrainYield）。

#### Scenario: 三普表层土模型
- **WHEN** 数据库表被创建
- **THEN** `ThirdSurveyTopsoil` 模型 SHALL 包含 pH、有机质、有效磷、速效钾、阳离子交换量等土壤理化指标字段，并支持经纬度定位

#### Scenario: 三普剖面理化模型
- **WHEN** 数据库表被创建
- **THEN** `ThirdSurveyProfile` 模型 SHALL 包含剖面深度、土壤质地、容重、孔隙度等剖面理化数据字段

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

```

## openspec/changes/import-lechang-soil-data/specs/soil-data-ingestion/spec.md

- Source: openspec/changes/import-lechang-soil-data/specs/soil-data-ingestion/spec.md
- Lines: 1-42
- SHA256: f5c85a35c9bd91c35c80a40c2b00b984c8e4a557cfa07577d45f0a057e7b9720

```md
## ADDED Requirements

### Requirement: Soil Data Import
系统 SHALL 提供导入脚本，从 `data/lechang/` 目录的 Excel/xls 文件批量导入乐昌市土壤数据到数据库，按数据源分表存储。导入的数据源包括：三普表层土、三普剖面理化、三普立地条件、三普容重、二普点、测土配方、农业化学化、粮食产量。

#### Scenario: 成功导入所有数据源
- **WHEN** 运行 `scripts/import_lechang_data.py` 且 `data/lechang/` 目录文件齐全
- **THEN** 系统 SHALL 将 8 个数据源的数据分别导入到对应的数据库表，每张表行数大于 0

#### Scenario: 部分数据文件缺失
- **WHEN** 运行导入脚本且部分 Excel 文件缺失
- **THEN** 系统 SHALL 跳过缺失文件的数据源，记录 warning 日志，继续导入其他可用数据源

#### Scenario: 列名映射处理
- **WHEN** Excel 文件的中文列名与数据库字段名不一致
- **THEN** 导入脚本 SHALL 使用硬编码列名映射表将中文列名转换为英文字段名，缺失列允许 NULL 值

### Requirement: Idempotent Import
导入脚本 SHALL 支持幂等执行，重复运行不产生重复数据。

#### Scenario: 重复执行导入
- **WHEN** 导入脚本被重复执行
- **THEN** 系统 SHALL 在导入前先清除目标表的所有行，再批量插入新数据，保证结果一致

#### Scenario: 导入中断恢复
- **WHEN** 导入脚本中途失败后重新运行
- **THEN** 系统 SHALL 从头重新导入所有数据源（先清除后导入），不残留部分写入的数据

### Requirement: Soil Data Database Query
系统 SHALL 通过 `soil_data_loader.py` 从数据库读取土壤数据，替代运行时文件读取和 mock 生成逻辑。

#### Scenario: 从 DB 读取真实数据
- **WHEN** `load_soil_data()` 被调用且数据库中有土壤数据
- **THEN** 系统 SHALL 从数据库表查询返回真实乐昌市土壤数据，不读取 Excel 文件

#### Scenario: DB 表为空时降级
- **WHEN** `load_soil_data()` 被调用但数据库表为空（未导入数据）
- **THEN** 系统 SHALL 降级到 mock 数据生成，并在日志中记录 warning 提示数据未导入

#### Scenario: 返回数据字段一致
- **WHEN** `load_soil_data()` 从 DB 读取数据
- **THEN** 返回的字典 SHALL 包含 `third_survey` 和 `formula_fertilization` 键，结构与原有 mock 返回值兼容

```
