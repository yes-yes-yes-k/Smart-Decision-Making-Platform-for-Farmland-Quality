# 重金属 Cd 空间分析（阶段 3）

对应 OpenSpec change：`add-heavy-metal-cd-spatial-analysis`（路线图阶段 3 / 7）。

## 一、端点（在 `/api/v1/heavy-metal-cd` 下，全部 JWT）

- `GET /spatial/townships?model=&min_count=&region_type=&parent_type=&parent_id=` — 按区域聚合的统计列表（默认 township）
- `GET /spatial/regions/<object_type>/<object_id>/statistics?model=` — 单个区域统计
- `GET /spatial/points?model=&bbox=&limit=` — 点位 GeoJSON（`application/json`，含 `FeatureCollection`）

区域边界**不在这里**：直接用 `GET /api/v1/farmland-statistics/boundaries?region_type=township`（已带拓扑简化与 zoom 抑制）。

## 二、地块归属规则：最大面积归属

数据来源是既有的 `farmland_region_parcel_area`（预计算「区域 × 地块 × 面积亩」），不是点面包含判断。

```sql
-- 每个地块只取面积最大的区域（窗口函数实现，PG/SQLite 通用）
ROW_NUMBER() OVER (PARTITION BY parcel_id ORDER BY area_mu DESC, region_id)
```

**为什么不用原系统的 `ST_Contains(town.geometry, point(lon,lat))`**：

- 实测 township 级 **530 个地块跨乡镇**（492 跨 2 个、37 跨 3 个、1 跨 4 个，占 9.6%）
- 按面积相交全部计入会让这些地块的 Cd 结果在多个乡镇重复统计，乡镇均值与样本数都会失真
- 点面包含的"落点在哪算哪个"依赖点坐标选择，不可复现；最大面积归属是确定性的
- 不做面积比例分摊：Cd 预测值是地块级单一值，拆分会造出"半块地的浓度"这种不存在的结果

响应里固定带 `assignment_rule="max_area"` 与 `borderline_parcel_count`（实测 530），让人知道有多少地块的归属是"选出来的"。

## 三、坐标来源：地块质心

结果表没有坐标列（阶段 1 决策 3：不记录追踪元数据），可用坐标只有 `parcel_info.centroid_lon/lat`（5488 个地块全部非空）。

- 响应声明 `coordinate_source="parcel_centroid"`
- 与原系统差异：原系统用**采样点** `lon/lan`，我们用**地块质心**；对狭长地块会有几十米到几百米偏移
- 该偏移只影响点位展示，不影响乡镇统计（统计走面积归属表）

## 四、统计口径

乡镇/区域统计**复用阶段 2 的函数**：

- 8 项基础统计：`heavy_metal_cd_statistics.basic_statistics()`（总体标准差、下标直取分位数、round 6）
- 作物三档分布：`crop_cd_distribution()`（`0.0~0.2` / `0.2~0.3` / `≥0.3`，负值计入超标）
- 有效态 Cd **不带任何分箱**

排序与过滤：`regions` 按样本数降序、`region_id` 升序；`min_count` 默认 1。

## 五、点位 GeoJSON 结构

```json
{
  "type": "FeatureCollection",
  "model_id": "crop_cd",
  "coordinate_source": "parcel_centroid",
  "boundary_endpoint": "/api/v1/farmland-statistics/boundaries",
  "bbox": null,
  "limit": 5000,
  "count": 2,
  "omitted": 1,
  "unit": "mg/kg",
  "unit_status": "unverified",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [114.6383, 25.1235]},
      "properties": {
        "parcel_id": "1", "sample_id": "S1",
        "value": 0.2665, "ln_value": -1.3223,
        "unit": "mg/kg", "unit_status": "unverified"
      }
    }
  ]
}
```

properties 只有数值与来源，**不含等级、颜色或超标判定**——着色规则属于前端与阶段 4。

## 六、错误码

- 400：`unknown_model`、`invalid_region_type`、`invalid_parent`、`invalid_min_count`、`invalid_bbox`、`invalid_limit`
- 401：未认证
- 404：`region_not_found`（区域目录里不存在该标识）
- 500：`spatial_failed`

## 七、实测验证记录（2026-10-31，真实库）

- 归属映射：**5488 个地块**都有 township 归属
- 跨乡镇计数：**530**，与面积表实测基线一致
- 空结果表：`has_data=false`、`borderline_parcel_count=530` 仍返回、点位 `count=0`
- 插入 3 条探针行（0.11 / 0.26 / 0.34）→ 分属梅坑镇 / 坪田镇 / 全安镇，三档分别为安全 / 预警 / 超标
- 单区域统计：梅坑镇地块数 77、样本数 1
- 点位 `limit=2` → `count=2`、`omitted=1`，坐标与 `parcel_info` 质心逐位核对一致
- 探针行已清理，结果表回到 0 行
- 单测 `tests/test_heavy_metal_cd_spatial.py`：**17 passed**

## 八、当前限制

结果表为空，乡镇统计的真实数值仍待输入到位；本阶段只能证明归属、聚合、点位链路正确。
