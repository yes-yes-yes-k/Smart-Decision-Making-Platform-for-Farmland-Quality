# add-cd-flux-accounting Proposal

## Why

Cd 通量核算（输入/输出/净通量、当年浓度）是原系统 AcidMap 的核心业务能力（`app/services/cd_flux_service.py`，2089 行；`app/api/cd_flux.py`，1125 行），本项目尚未迁移。原系统实现有两处必须修正的问题：① `net_cd` 分布分箱中「负值（v<0）」「接近平衡（-5~5）」「正值（v>0）」互相重叠，同一记录可同时计入两档、占比之和可超过 100%；② CSV 模式与数据库模式的输出通量/当年浓度公式不一致（CSV 模式用固定常量 0.023/0.368/0.0/0.0 与固定 2000 kg/ha，数据库模式从输入表读实际值并乘 `bd020_90`）。

本 change 迁移计算、统计、持久化与导出链路；输入数据本身依赖外部供给（实测新库无 flux 表、`third_survey_bulk_densities` 空表）。

## What Changes

- 新增两张结果表：`cd_flux_input`（初始 Cd + 7 项通量分量 + `bd020_90`）与 `cd_flux_output`（In/Out/Net/End），与原系统同构，另加 `(parcel_id, sample_id)` 唯一约束。
- 新增 CSV 导入：把完整输入行灌入 `cd_flux_input`（按输入文件覆盖同键行），导入时校验字段与数值。
- 新增通量计算：输入表 → 输出表（公式与原系统数据库模式一致；缺失 `bd020_90` 回退 1.0、缺失 `initial_cd` 回退 0，回退计数进响应）。
- 新增统计：区域/乡镇聚合（复用阶段 3 归属依据）、8 项基础统计（复用阶段 2 口径）、四类分布（`end_cd` 三档、`net_cd` 互斥三档、`in/out` 相对三档）。
- 新增空间结果：点位 GeoJSON + 分级地图/直方图（复用阶段 4 的栅格化与渲染引擎，不改其规格）。
- 新增 CSV 导出与 HTTP 端点（导入/计算/统计/明细/导出）。

## Capabilities

### New Capabilities

- `cd-flux-accounting`: Cd 通量输入行导入、输入/输出/净通量与当年浓度计算、区域统计与分布、空间点位与可视化、结果持久化与 CSV 导出。

### Modified Capabilities

无。本 change 复用既有统计口径（`heavy-metal-cd-statistics`）、区域归属（`heavy-metal-cd-spatial-analysis`）与渲染引擎（`heavy-metal-cd-visualization`），不改变它们的行为与响应。

## Impact

- 代码：新增 `framework/models/cd_flux.py`、`framework/domain/other_models/cd_flux.py`（计算/统计）、`framework/api/routes/cd_flux.py`、`scripts/migrate_cd_flux_tables.py`（建表）、`tests/test_cd_flux.py`。
- 数据：新增两张表；只写 flux 结果，不触碰 Cd 预测结果表。
- 接口：新增 `/api/v1/cd-flux/*` 端点（JWT）。
- 依赖：复用 numpy/pandas/geopandas/rasterio/matplotlib（阶段 4 已装）。

## Roadmap

- 阶段：**5 / 7**（阶段 0–4 与 D1 已归档）
- 前置：阶段 2 的统计口径与阶段 3 的归属依据（已归档）；可与阶段 2 并行，实际在阶段 4 之后实施
- 后续：`add-cd-removal-calculation`（阶段 6：籽粒/秸秆移除、地下渗流、地表径流，触发通量重算）
- 单一真相源：`docs/cd-migration-roadmap.md`；归档时需回填该文件状态

## Non-Goals

- 不做籽粒/秸秆移除、地下渗流、地表径流的独立计算（阶段 6）；本阶段输出通量直接取输入行提供的分量。
- 不做未来 N 年情景预测（阶段 7）。
- 不从第三方数据自动推导大气沉降/灌溉/农化投入（新库无数据源，输入依赖外部供给）。
- 不改动 Cd 预测结果表与既有统计/空间/可视化端点。
