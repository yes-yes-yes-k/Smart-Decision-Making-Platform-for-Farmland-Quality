## 1. 空间归属与聚合服务

- [ ] 1.1 新增 `framework/domain/other_models/heavy_metal_cd_spatial.py`，提供 `parcel_township_map(region_type="township")`：按 `farmland_region_parcel_area` 取每地块**面积最大**的区域（`DISTINCT ON (parcel_id) ... ORDER BY area_mu DESC, region_id`）
- [ ] 1.2 `borderline_parcel_count(region_type)`：统计跨多个区域的地块数（实测 township 级 530），用于响应披露
- [ ] 1.3 `region_values(model_id, region_type, region_id)`：该区域内全部 Cd 值（`exp` 还原），走归属表而非点面判断
- [ ] 1.4 `township_statistics(model_id, parent_type=None, parent_id=None, min_count=1)`：按乡镇聚合并复用 `heavy_metal_cd_statistics.basic_statistics` / `crop_cd_distribution`（作物才有分箱），返回列表含 `region_id`、`display_name`、`count`、统计、跨乡镇披露
- [ ] 1.5 复用既有区域目录：`spatial_region_catalog` 取 `display_name` / 上级区域，不新造名称表

## 2. 点位 GeoJSON

- [ ] 2.1 `points_geojson(model_id, bbox=None, limit=5000)`：结果 JOIN `parcel_info` 取 `centroid_lon/lat`，输出 FeatureCollection
- [ ] 2.2 properties 固定为 `parcel_id / sample_id / value / ln_value / unit / unit_status`，**不含等级或颜色**
- [ ] 2.3 响应带 `coordinate_source="parcel_centroid"` 与 `omitted`（超过 limit 被截断的条数），并支持 `bbox` 过滤

## 3. HTTP 端点

- [ ] 3.1 在既有 `framework/api/routes/heavy_metal_cd.py` 增加 `/spatial/townships`（参数 `model`、`min_count`、可选 `parent_type`+`parent_id`）
- [ ] 3.2 增加 `/spatial/regions/<object_type>/<object_id>/statistics`（参数 `model`），非法 object_type 返回 400
- [ ] 3.3 增加 `/spatial/points`（参数 `model`、`bbox`、`limit`），返回 `application/geo+json`
- [ ] 3.4 全部 `@jwt_required()`；错误码沿用阶段 2 约定（400/401/413/500）

## 4. 文档与验证

- [ ] 4.1 新增 `docs/heavy-metal-cd-spatial.md`：归属规则（最大面积）、跨乡镇披露、质心坐标系差异、端点与参数
- [ ] 4.2 定向测试 `tests/test_heavy_metal_cd_spatial.py`：唯一归属去重（同一地块多条区域行只取最大面积）、跨乡镇计数、乡镇统计口径与阶段 2 一致、点位 GeoJSON 结构与 bbox 过滤、非法 object_type 400
- [ ] 4.3 真实库探针：用真实 `farmland_region_parcel_area` + `spatial_region_catalog` 验证乡镇归属（103 个乡镇、530 个跨乡镇地块），插入若干探针结果行验证乡镇统计与点位输出后清理
- [ ] 4.4 `openspec validate add-heavy-metal-cd-spatial-analysis` 与 `git diff --check`
- [ ] 4.5 归档时回填 `docs/cd-migration-roadmap.md` 中阶段 3 的状态与归档日期

## 未完成（需人工确认后执行）

- **跨乡镇归属规则**：最大面积归属（本提案默认）vs 面积比例分摊（Open Question 1）。
- **`min_count` 默认值**：1（本提案默认）vs 3/5（Open Question 2）。
- **乡镇列表排序**：样本数降序（本提案默认）vs 行政区码升序（Open Question 3）。
- **点位 bbox/上限**：默认支持 bbox + limit 5000（Open Question 4）。
- **结果表当前为空**：真实乡镇统计需输入到位后才能看到数值；探针只能证明链路与归属正确。
- **边界端点不新增**：直接复用 `/api/v1/farmland-statistics/boundaries`，若前端希望 Cd 侧提供同款包装，另开 change。
