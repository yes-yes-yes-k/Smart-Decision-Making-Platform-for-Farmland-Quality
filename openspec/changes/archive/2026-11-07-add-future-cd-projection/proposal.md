# add-future-cd-projection Proposal

## Why

阶段 5/6 已能算出净通量与当年浓度，但业务方最关心的问题是「照这个通量再走 N 年，Cd 会变成多少」。原系统有这条链路（`predict_future_cd`，公式 `Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bd020_90)`），本项目尚未迁移。

核验原系统实现时确认两处问题：① `area` 参数只进日志、**查询实际是全量**（源码里明写 TODO），区域筛选从未生效；② 统计用 `pandas.DataFrame.std()`（样本标准差，n−1），与阶段 2 已确立的总体标准差口径不一致。

## What Changes

- 新增未来 Cd 浓度预测：基于 `cd_flux_input`（含阶段 6 写回的移除项）与阶段 5 的净通量，按 `Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bd020_90)` 计算。
- 支持多年份情景对比：一次请求可传多个年份（如 1/5/10/20），返回各年份统计与逐点值。
- 区域/来源过滤真实生效（修正原系统 TODO）；统计统一阶段 2 口径（总体标准差、下标直取分位数）。
- 新增未来空间分布：点位 GeoJSON、地图/直方图、CSV 导出（复用阶段 4 引擎）。
- 新增 HTTP 端点：预测 / 统计 / 点位 / 导出 / 可视化。

## Capabilities

### New Capabilities

- `cd-future-projection`: 未来 N 年 Cd 浓度预测、多年份情景对比、统计与空间分布、导出。

### Modified Capabilities

无。复用阶段 5 的输入表与净通量、阶段 2 的统计口径、阶段 3 的归属依据、阶段 4 的渲染引擎，不改变其行为。

## Impact

- 代码：新增 `framework/domain/other_models/cd_projection.py`、路由增补、`tests/test_cd_projection.py`。
- 数据：只读 `cd_flux_input` / `cd_flux_output`，不新增表、不写业务数据。
- 接口：新增 `/api/v1/cd-flux/projection*` 端点（JWT）。
- 依赖：复用现有 numpy/pandas/rasterio/matplotlib。

## Roadmap

- 阶段：**7 / 7**（阶段 0–6 与 D1 已归档）
- 前置：`add-cd-flux-accounting`（阶段 5）、`add-cd-removal-calculation`（阶段 6）、阶段 3 空间归属（均已归档）
- 后续：无（Cd 迁移 8 个阶段收口）
- 单一真相源：`docs/cd-migration-roadmap.md`；归档时需回填该文件状态

## Non-Goals

- 不做气候变化/管理措施的情景建模（只按恒定净通量线性外推，与原系统一致）。
- 不落库预测结果（按需计算；需要留存时用 CSV 导出）。
- 不改变阶段 5/6 的计算与分箱口径。
