# add-heavy-metal-cd-spatial-analysis Design

## Context

阶段 2 的统计是"全表或按 `parcel_info.area_code`"，即区县粒度。本阶段补乡镇（township）粒度与点位输出。

原系统做法（`app/services/cd_prediction_statistics_service.py:640+`）：

```sql
SELECT co."LnCropCd", f."Farmland_ID", f."Sample_ID", f.lon, f.lan
FROM "CropCd_output_data" co
JOIN "Farmland_data" f USING ("Farmland_ID","Sample_ID")
JOIN town t ON ST_Contains(t.geometry, ST_SetSRID(ST_MakePoint(f.lon, f.lan), 4326))
WHERE t.name = :town_name
```

特点：点面包含判断、按乡镇名匹配、命中后重新算 8 项统计。

本项目可用的现成基础设施（2026-10-31 实测）：

- `spatial_region_catalog`：`object_type` ∈ {province, city, county, township, zone, village}，其中 township **103 个**，边界 `geom`（MultiPolygon 4326）全部可用
- `farmland_region_parcel_area`：`(region_type, region_id, parcel_id, area_mu)` 预计算，township 级 6057 条、覆盖 5488 个地块
- `parcel_info.centroid_lon/lat`：5488 个地块全部有值
- `farmland_statistics.list_boundaries(region_type, parent_type, parent_id, bbox, zoom)`：已实现 GeoJSON 输出 + `ST_SimplifyPreserveTopology` + `BOUNDARY_MIN_ZOOM` 抑制

跨乡镇事实：4958 个地块只属 1 个 township，**492 个属 2 个、37 个属 3 个、1 个属 4 个**（合计 530 个，9.6%）。

## Goals / Non-Goals

**Goals:**

- 乡镇级 Cd 统计可直接消费，且同一地块不被重复计数
- 点位与边界都能直接喂地图组件
- 复用既有空间能力，不再实现一套点面判断

**Non-Goals:**

- 不做栅格/插值/图像（阶段 4）
- 不改动 `farmland_statistics` 的既有端点语义
- 不引入新的空间依赖（PostGIS 已在用）

## Decisions

### 1. 乡镇归属用「最大面积归属」，不用点面包含

归属规则：

```sql
-- 每个地块只取面积最大的那个 township
SELECT DISTINCT ON (parcel_id) parcel_id, region_id, area_mu
FROM farmland_region_parcel_area
WHERE region_type = 'township'
ORDER BY parcel_id, area_mu DESC, region_id
```

理由：

- 原系统的点面包含会把一个跨乡镇地块无论落点在哪都只算一次，但落点选择本身是任意的；用"最大面积归属"语义更明确且可复现。
- 若按面积相交全部计入，530 个跨乡镇地块会被重复统计（乡镇均值与总数都会偏）。
- 不做面积比例分摊：Cd 预测值本身是地块级单一值，按比例拆分会制造出"半块地的浓度"这种不存在的结果。

响应里必须披露 `borderline_parcel_count`（跨乡镇地块数，实测 530），让人知道有多少地块的归属是"选出来的"。

### 2. 点位坐标用地块质心

结果表没有坐标（阶段 1 决策 3：不追踪元数据）。可用坐标只有 `parcel_info.centroid_lon/lat`（全部非空）。

与原系统的差异要写进响应：原系统用**样点** `lon/lan`，我们用**地块质心**；对多边形状地块两者会有几十米到几百米偏移。响应带 `coordinate_source: "parcel_centroid"`。

### 3. 区域边界复用既有 `list_boundaries`

不新增边界端点，也不复制 SQL。Cd 点位与原边界是两个独立层，前端分别取：

- 边界：`GET /api/v1/farmland-statistics/boundaries?region_type=township`
- 点位：`GET /api/v1/heavy-metal-cd/spatial/points?model=crop_cd`

这样避免出现两套简化容差、两套 zoom 抑制规则。

### 4. 乡镇统计复用阶段 2 的统计函数

乡镇统计 = 按归属聚合出该乡镇的 Cd 值列表 → 调 `heavy_metal_cd_statistics.basic_statistics()` 与 `crop_cd_distribution()`。口径与阶段 2 完全一致（总体标准差、下标分位数、round 6、三档边界、负值计入超标），不另写一套。

### 5. 乡镇列表默认按「有数据 + 均值降序」，并支持 `min_count`

- 只返回有结果的乡镇；`townships` 数组按 `数据点总数`降序、再按 `region_id` 升序，保证稳定
- 可选 `min_count`（默认 1）过滤样本过少的乡镇，避免 1 个点就出一个"乡镇均值"
- 有效态模型同样可用，但**不带分布统计**

### 6. 点位 GeoJSON 只给数值，不给判定

Feature properties 固定：`parcel_id, sample_id, value, ln_value, unit, unit_status`。不带等级或颜色建议——着色规则属前端与阶段 4 的可视化决策。

## Risks / Trade-offs

- 最大面积归属会让"贴边地块"归到一个乡镇，邻镇统计里看不到它；已用 `borderline_parcel_count` 披露。
- 质心偏移：狭长地块的质心可能落在别的乡镇内；因归属走面积表（不用质心），统计不受影响，只有点位展示有小偏差。
- 乡镇列表在 103 个乡镇 × 结果行数下的聚合成本：先在 SQL 侧做 group 与 count，只为有数据的乡镇取明细值，避免全量进 Python。

## Migration and Rollback

- 无 schema 变更、无迁移。
- 回滚：删除新服务文件与 `/spatial/*` 路由注册即可。

## Open Questions

1. **跨乡镇归属规则**：最大面积归属（本提案默认）还是面积比例分摊？
2. **`min_count` 默认值**：1（全部返回）还是 3/5（过滤小样本）？
3. **乡镇列表排序**：样本数降序（本提案默认）还是按行政区码升序？
4. **点位是否要按 bbox 过滤**：默认支持 `bbox=minLon,minLat,maxLon,maxLat` 还是先全量返回（上限 N 条）？
