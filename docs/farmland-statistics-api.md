# 耕地地图统计 API

统一前缀：`/api/v1/farmland-statistics`。所有接口需要 JWT。

## 版本与口径

- 指标配置版本：`2026-09-21.1`。
- 不指定 `year` 时使用 `/years` 返回的 `defaultYear`。
- 年度指标来自 `parcel_history_snapshot`，地块几何来自 `parcel_info`。
- 统计响应必须回传规范化后的 `scope`；当前 `scopeVersion=1`。
- 数值指标按范围内裁剪面积加权，分类指标返回分类计数和面积分布。
- 未入库的污染监测指标返回 `availability=unavailable`，不得生成或推断数值。

## 1. 指标目录

`GET /metrics`

响应 `data` 为对象：

```json
{
  "classificationVersion": "2026-09-21.1",
  "groups": [
    {
      "key": "soil_nutrients",
      "label": "土壤养分",
      "order": 20,
      "metrics": ["organic_matter", "total_nitrogen", "available_phosphorus", "available_potassium"]
    }
  ],
  "metrics": [
    {
      "metricKey": "soil_ph",
      "label": "土壤 pH",
      "groupKey": "physical_properties",
      "order": 10,
      "valueType": "number",
      "availability": "available",
      "dataYears": [2024, 2021, 2018],
      "coverageByYear": {
        "2024": {"valueCount": 5488, "parcelCount": 5488, "percent": 100.0}
      }
    }
  ],
  "availableYears": [
    {"year": 2024, "parcelCount": 5488, "selectable": true}
  ],
  "defaultYear": 2024
}
```

分组顺序固定为：质量评价、土壤养分、理化性质、污染状况、农田条件。`availability` 取值为 `available`、`partial`、`unavailable` 或数据库不可访问时的 `unknown`。

## 2. 可选年份

`GET /years`

```json
{
  "status": "ok",
  "data": {
    "years": [
      {"year": 2024, "parcelCount": 5488, "selectable": true},
      {"year": 2021, "parcelCount": 5488, "selectable": true},
      {"year": 2018, "parcelCount": 5488, "selectable": true}
    ],
    "defaultYear": 2024
  }
}
```

## 3. 层级行政区域

`GET /regions?parent_type=county&parent_id=440281`

支持 `province`、`city`、`county`、`township`、`village` 和争议区 `zone`。`parent_type` 与 `parent_id` 必须同时提供；默认排除 `zone`。

## 4. 行政边界

`GET /boundaries?region_type=township&parent_type=county&parent_id=440281&zoom=10`

可选参数：

- `bbox=minLon,minLat,maxLon,maxLat`
- `zoom=0..24`

响应为 GeoJSON `FeatureCollection`，并返回 `selectable`、父级、最小显示层级和是否截断。

## 5. 统一统计范围

所有统计和批量地块查询共用以下三种 `scope`：

```json
{"type": "administrative_region", "region_type": "county", "region_id": "440281"}
```

```json
{"type": "viewport", "bbox": [113.0, 24.0, 114.0, 25.0]}
```

```json
{"type": "parcel", "parcel_id": "1007"}
```

服务端会验证并在响应中回传规范化的范围，例如：

```json
{
  "scopeVersion": 1,
  "type": "administrative_region",
  "regionType": "county",
  "regionId": "440281",
  "displayName": "乐昌市"
}
```

## 6. 按范围和年份统计

`POST /aggregate`

```json
{
  "scope": {"type": "viewport", "bbox": [113.0, 24.0, 114.0, 25.0]},
  "year": 2021,
  "metrics": ["soil_ph", "organic_matter", "soil_texture"]
}
```

响应包含：

- `classificationVersion`
- `dataYear`
- 规范化 `scope`
- `scopeSummary`
- 按指标返回的 `table`、`distribution` 和 `unclassified`

数值指标的 `table.average` 为面积加权平均；分类指标的 `average` 为 `null`，`distribution` 返回各类别地块数、面积和百分比。

## 7. 按范围查询地块

`POST /parcels/query`

```json
{
  "scope": {"type": "administrative_region", "region_type": "township", "region_id": "440281001"},
  "year": 2024,
  "metrics": ["quality_grade", "soil_ph", "soil_texture"],
  "geometry": "centroid",
  "limit": 100,
  "offset": 0
}
```

`geometry` 支持 `centroid` 和 `none`；`limit` 最大 500。响应回传 `scope`、`dataYear`、地块指标、几何和分页状态。

## 8. 地块详情和地图点选

- `GET /parcels/{parcel_id}?year=2021`
- `POST /parcels/pick`

点选请求：

```json
{"longitude": 113.084486, "latitude": 25.094996, "year": 2021}
```

详情响应返回完整指标对象，每项包含名称、分组、值类型、值、单位和可用的分级/颜色信息，同时保留原有 `qualityGrade`、`organicMatter`、`soilPh`、`availablePhosphorus` 兼容字段。

## 9. 数据规范化

历史数据可先预览再执行字段规范化：

```powershell
python scripts/migrate_farmland_indicator_data.py
python scripts/migrate_farmland_indicator_data.py --apply
```

脚本只进行现有值的别名复制：

- `topsoil_thickness` → `effective_soil_depth`
- `total_n` → `total_nitrogen`

脚本不会填造重金属监测值、污染风险结论或其他源数据中不存在的指标。

## 错误码

| HTTP | code | 含义 |
|---:|---|---|
| 400 | `invalid_scope`、`invalid_metrics`、`invalid_year`、`invalid_bbox` | 请求参数无效 |
| 404 | `year_not_available`、`parcel_year_not_found`、`region_not_found`、`parcel_not_found` | 对象或年度数据不存在 |
| 409 | `region_geometry_missing`、`parcel_geometry_missing` | 对象存在但缺少几何 |
| 503 | `statistics_unavailable` | 数据库或空间统计服务暂时不可用 |
