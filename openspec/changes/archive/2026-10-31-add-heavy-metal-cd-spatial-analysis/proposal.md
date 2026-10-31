# add-heavy-metal-cd-spatial-analysis Proposal

## Why

阶段 2 已让 Cd 结果可以按全域/区县统计（2026-10-31 归档），但没有空间维度：拿不到"每个乡镇的 Cd 水平"、也没有点位数据给地图用。

原系统的乡镇统计（`get_crop_cd_statistics_by_town`）用 SQL 空间查询：`JOIN town ON ST_Contains(town.geometry, ST_MakePoint(f.lon, f.lan))`，即**用点与乡镇多边形做包含判断**，且统计逻辑是"再算一遍 8 项基础统计"。

本项目不需要重造这套空间能力——实测已有完整基础设施：

- `spatial_region_catalog`：province 1 / city 1 / county 10 / **township 103** / zone 373 / village 1199，乡镇边界全部可用（`enabled` 且 `geom` 非空）
- `farmland_region_parcel_area`：**30751 行**预计算的「区域 × 地块 × 面积亩」，township 级 6057 条，覆盖全部 5488 个地块
- `parcel_info.centroid_lon/lat`：5488 个地块**全部有质心坐标**
- `framework/api/services/farmland_statistics.py` 已有 `list_boundaries()`（返回 GeoJSON + 拓扑简化 + zoom 抑制）、`list_regions()`

同时实测出一个必须处理的事实：**530 个地块跨乡镇**（492 个跨 2 个、37 个跨 3 个、1 个跨 4 个，占 9.6%）。若按面积相交全部计入，同一地块的 Cd 结果会在多个乡镇重复统计。

## What Changes

- 新增乡镇级 Cd 统计：按地块-乡镇归属聚合，复用阶段 2 的 8 项统计与作物三档分布
- 新增点位查询：结果 + 地块质心坐标，输出 GeoJSON FeatureCollection 供地图消费
- 区域边界直接复用既有 `list_boundaries()`，不新增重复实现
- 明确跨乡镇地块的唯一归属规则，并在响应中披露跨乡镇地块数量

## Capabilities

### New Capabilities

- **heavy-metal-cd-spatial-analysis**：Cd 结果的乡镇级统计、区域统计与点位 GeoJSON 输出。

### Modified Capabilities

- 无（阶段 2 的统计口径与端点不变）

## Impact

- **代码**：新增 `framework/domain/other_models/heavy_metal_cd_spatial.py`；在既有 `heavy_metal_cd` 蓝图下增加 `/spatial/*` 端点
- **接口**：新增 3 个端点（乡镇列表、单区域统计、点位 GeoJSON），全部 `jwt_required`
- **数据库**：只读，不新增表、不改 schema
- **不做**：地图图片、直方图、栅格、插值（阶段 4）

## Roadmap

- 阶段：**3 / 7**（阶段 0–2 已归档）
- 前置：`add-heavy-metal-cd-statistics-api`（已归档，提供 8 项统计与分箱）
- 后续：`add-heavy-metal-cd-visualization`（阶段 4：地图、直方图、栅格）
- 单一真相源：`docs/cd-migration-roadmap.md`；归档时需回填该文件状态

## Non-Goals

- 不做地图渲染、直方图、栅格化、空间插值（阶段 4）
- 不做通量/移除/未来情景（阶段 5–7）
- 不重写区域边界查询（直接复用 `farmland_statistics.list_boundaries`）
- 不引入 GeoServer（本项目边界与点位由自身 API 提供）
