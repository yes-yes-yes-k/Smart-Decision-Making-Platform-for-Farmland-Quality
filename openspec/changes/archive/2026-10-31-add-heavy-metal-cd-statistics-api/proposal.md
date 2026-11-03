# add-heavy-metal-cd-statistics-api Proposal

## Why

阶段 1 已让 Cd 结果能落库（`cd_crop_prediction_result` / `cd_effective_prediction_result`，2026-10-31 归档），但目前**只能写、不能读**：没有任何统计、查询或导出能力，前端和报告拿不到数据。

原 AcidMap 的对应能力在 `app/services/cd_prediction_statistics_service.py`，实测口径如下：

- 基础统计固定 8 项：数据点总数、均值、中位数、标准差、最小值、最大值、25% 分位数、75% 分位数，全部 `round(…, 6)`
- 标准差是**总体标准差**（除以 n），分位数是**按下标直取** `sorted[int(count*q)]`，不是线性插值
- 只有作物 Cd 有分布分箱：`0.0~0.2` 安全区间、`0.2~0.3` 预警区间、`≥0.3` 超标区间，负值归入超标；有效态 Cd **只有 8 项基础统计、没有分箱**
- 综合统计给出"数据完整性 + 两模型对比"
- 统计端点 `GET /crop-cd/statistics`、`/effective-cd/statistics`、`/combined-statistics`，无数据时抛 404

当前系统的差距：本仓库没有任何 Cd 统计服务或 HTTP 端点（`framework/api/routes/` 下无 Cd 路由）。另外实测发现原系统 `get_crop_cd_statistics(area=...)` 的 `area` 参数**没有参与 SQL 查询**，区域过滤实际不生效——本阶段需要真正实现它。

## What Changes

- 新增统计领域服务：8 项基础统计（对齐原系统算法）、作物 Cd 三档分布、双模型综合统计、明细查询、CSV 导出
- 新增 HTTP 蓝图 `/api/v1/heavy-metal-cd/*`：统计、明细、CSV、模型清单四类端点，沿用现有 JWT 认证
- 区域过滤真正生效：按 `parcel_info.area_code` 关联结果表过滤（原系统的 `area` 参数是失效的）
- 空数据返回结构化空态，不用 404 区分"没数据"和"出错"

## Capabilities

### New Capabilities

- **heavy-metal-cd-statistics**：Cd 结果的统计、明细查询、CSV 导出与模型契约查询，通过 HTTP 提供。

### Modified Capabilities

- 无（阶段 1 归档的四条要求不变；本阶段只在其上增加读取能力）

## Impact

- **代码**：新增 `framework/domain/other_models/heavy_metal_cd_statistics.py`、`framework/api/routes/heavy_metal_cd.py`，并在 `framework/api/app.py` 注册蓝图
- **接口**：新增 4 组端点（统计 3 个 + 明细/CSV/模型清单），全部 `jwt_required`
- **数据库**：只读，不新增表、不改 schema
- **契约**：响应字段沿用原系统中文键名与 6 位小数，避免前端二次适配；新增 `has_data`、`unit_status`、`statistics_scope` 三个说明性字段
- **不产生** 地图、栅格、直方图（阶段 4）

## Roadmap

- 阶段：**2 / 7**（阶段 0、1 已归档）
- 前置：`add-heavy-metal-cd-database-backend`（已归档，提供两张结果表与读取入口）
- 后续：`add-heavy-metal-cd-spatial-analysis`（阶段 3：空间与乡镇统计）
- 单一真相源：`docs/cd-migration-roadmap.md`；归档时需回填该文件状态

## Non-Goals

- 不做空间统计、乡镇聚合、GeoJSON（阶段 3）
- 不做地图、直方图、栅格、插值（阶段 4）
- 不做通量、移除过程、未来情景（阶段 5–7）
- 不做前端页面（本项目无前端工程）
- 不对有效态 Cd 做任何阈值分箱
