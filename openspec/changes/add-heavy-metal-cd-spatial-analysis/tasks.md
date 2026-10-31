## 1. 空间归属与聚合服务

- [x] 1.1 新增 `framework/domain/other_models/heavy_metal_cd_spatial.py`，`parcel_region_map()` 用窗口函数 `ROW_NUMBER() OVER (PARTITION BY parcel_id ORDER BY area_mu DESC, region_id)` 实现唯一归属（PG/SQLite 通用）
- [x] 1.2 `borderline_parcel_count()`：统计跨多个区域的地块数（真实库实测 530，与基线一致）
- [x] 1.3 `region_statistics(model_id, region_type, region_id)`：归属走面积表，不用点面判断；区域不存在抛 `region_not_found`
- [x] 1.4 `township_statistics(...)`：按区域聚合并复用 `basic_statistics` / `crop_cd_distribution`（作物才有分箱），返回 `assignment_rule` / `borderline_parcel_count` / 排序稳定
- [x] 1.5 复用 `spatial_region_catalog` 取 `display_name` / `area_code` / 上级区域，不新造名称表

## 2. 点位 GeoJSON

- [x] 2.1 `points_geojson(model_id, bbox, limit)`：结果 JOIN `parcel_info` 取质心，输出 `FeatureCollection`
- [x] 2.2 properties 固定 `parcel_id / sample_id / value / ln_value / unit / unit_status`，不含等级或颜色
- [x] 2.3 响应带 `coordinate_source="parcel_centroid"`、`boundary_endpoint`、`omitted`，支持 `bbox` 过滤与 `limit`（上限 20000）

## 3. HTTP 端点

- [x] 3.1 `/spatial/townships`（`model`、`min_count`、`region_type`、`parent_type`+`parent_id`）
- [x] 3.2 `/spatial/regions/<object_type>/<object_id>/statistics`（非法类型 400、区域不存在 404）
- [x] 3.3 `/spatial/points`（`model`、`bbox`、`limit`），返回 GeoJSON
- [x] 3.4 全部 `@jwt_required()`；错误码 400/401/404/500 与阶段 2 约定一致

## 4. 文档与验证

- [x] 4.1 新增 `docs/heavy-metal-cd-spatial.md`：归属规则、跨乡镇披露、质心坐标差异、端点与参数、实测记录
- [x] 4.2 `tests/test_heavy_metal_cd_spatial.py` 17 passed：唯一归属（面积大者胜出）、跨乡镇计数、区域统计口径、排序与 min_count、有效态无分箱、点位结构与 bbox/limit/omitted、错误码、HTTP 401/200/400/404
- [x] 4.3 真实库探针：5488 地块全部有归属；跨乡镇 530（与基线一致）；插入 3 条探针行后分属 3 个乡镇且三档正确（0.11 安全 / 0.26 预警 / 0.34 超标）；单区域梅坑镇 77 地块 1 样本；点位 limit=2 → count=2 omitted=1 且坐标与质心逐位一致；探针已清理
- [x] 4.4 `openspec validate add-heavy-metal-cd-spatial-analysis` = valid；`git diff --check` 通过
- [ ] 4.5 归档时回填 `docs/cd-migration-roadmap.md` 中阶段 3 的状态与归档日期

## 未完成（需人工确认后执行）

- **四个口径已拍板（2026-10-31 用户确认"按推荐"）**：最大面积归属、`min_count` 默认 1、样本数降序、点位支持 bbox + limit 5000。
- **结果表当前为空**：乡镇统计真实数值待输入到位；探针只证明归属与聚合链路。
- **边界端点不新增**：复用 `/api/v1/farmland-statistics/boundaries`；若前端希望 Cd 侧提供同款包装，另开 change。
- **聚合位置与 design 不一致已同步**：实测改为 Python 侧聚合（5488 地块规模），design 的 Risks 段已改写；结果行数进入 10 万级时需改回 SQL 聚合并重验口径。
