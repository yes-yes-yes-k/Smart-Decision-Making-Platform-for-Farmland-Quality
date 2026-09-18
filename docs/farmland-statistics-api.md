# 耕地统计接口设计与口径

## 已确定口径

- 统计范围支持行政区域和当前地图视窗。行政区域已支持县、镇、村；地图缩放或平移后，前端在 `moveend` 事件调用视窗统计即可联动更新。
- 地块与范围只要实际相交即纳入“地块数”，面积按裁剪到范围内的部分计算，避免跨行政边界或视窗边缘的面积被重复计入。
- 平均值按裁剪后的地块面积加权。接口同时返回有效指标面积/数量和未分类面积/数量，缺失值或非正值不会悄悄进入最低档。
- 柱状图和饼图共用 `distribution`，柱状图使用 `parcelCount`，饼图可按 `areaMu` 或 `parcelCount` 展示。
- 所有最高档不设上限。有机质大于 40、有效磷大于 40 均继续使用各自“高”档颜色，不新增颜色。
- 有效土层厚度的规范字段为 `effective_soil_depth`；兼容读取历史误用字段 `topsoil_thickness`。
- 韶关范围内 373 个村间争议面以 `zone` 保存并标记为不可选择，不强行归入任何普通村。
- 地块详情和点选响应中的 `areaMu` 是完整地块测地面积换算的亩数，不受当前视窗或行政区边界裁剪；几何缺失时为 `null`。
- 指标配置、聚合统计和地块详情统一返回 `classificationVersion`。客户端发现版本变化时应刷新图例和专题样式缓存。
- 行政区统计支持单区域、同层级多区域联合，以及用户圈选的 Polygon/MultiPolygon；联合区域先去重合并再裁剪地块。

## 接口输入输出示例

所有接口使用现有 JWT 鉴权，统一前缀为 `/api/v1/farmland-statistics`。以下响应中的统计值取自当前开发数据库，仅用于说明字段结构；数据库更新后数值可能变化。

请求头：

```http
Authorization: Bearer <token>
Content-Type: application/json
```

### 1. 获取指标配置

**GET** `/api/v1/farmland-statistics/metrics`

用途：返回 8 项指标的名称、单位、精度、分档边界、颜色和配置版本。前端图例应直接使用此接口，避免重复维护分档。

输入示例：

```http
GET /api/v1/farmland-statistics/metrics
Authorization: Bearer <token>
```

该接口没有查询参数和请求体。

成功输出（200，以下只展示 `soil_ph`；实际 `data` 包含全部 8 项指标）：

```json
{
  "status": "ok",
  "data": [
    {
      "key": "soil_ph",
      "metricKey": "soil_ph",
      "classificationVersion": "2026-09-18.1",
      "label": "酸化 pH 情况",
      "sourceField": "soil_ph",
      "unit": "pH",
      "decimals": 2,
      "buckets": [
        {
          "key": "very_strong_acid",
          "label": "极强酸性",
          "rangeLabel": "<4.5",
          "color": "#B2182B",
          "lower": null,
          "upper": 4.5,
          "lowerInclusive": false,
          "upperInclusive": false
        },
        {
          "key": "strong_acid",
          "label": "强酸性",
          "rangeLabel": "[4.5,5.5)",
          "color": "#EF8A62",
          "lower": 4.5,
          "upper": 5.5,
          "lowerInclusive": true,
          "upperInclusive": false
        },
        {
          "key": "acid",
          "label": "酸性",
          "rangeLabel": "[5.5,6.5)",
          "color": "#FDDBC7",
          "lower": 5.5,
          "upper": 6.5,
          "lowerInclusive": true,
          "upperInclusive": false
        },
        {
          "key": "neutral",
          "label": "中性",
          "rangeLabel": "[6.5,7.5]",
          "color": "#92C5DE",
          "lower": 6.5,
          "upper": 7.5,
          "lowerInclusive": true,
          "upperInclusive": true
        },
        {
          "key": "alkaline",
          "label": "碱性",
          "rangeLabel": ">7.5",
          "color": "#2166AC",
          "lower": 7.5,
          "upper": null,
          "lowerInclusive": false,
          "upperInclusive": false
        }
      ]
    }
  ]
}
```

`lower` 或 `upper` 为 `null` 表示该方向不设边界。最高档的 `upper` 均为 `null`，例如有机质超过 40 仍使用“高”档颜色。

### 2. 查询行政区域目录

**GET** `/api/v1/farmland-statistics/regions`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent_type` | string | 否 | 父级类型，必须和 `parent_id` 同时提供 |
| `parent_id` | string | 否 | 父级对象 ID，必须和 `parent_type` 同时提供 |
| `include_disputes` | boolean | 否 | 是否包含不可选择的争议区，默认 `false` |

输入示例——查询乐昌市下的镇：

```http
GET /api/v1/farmland-statistics/regions?parent_type=county&parent_id=440281
Authorization: Bearer <token>
```

成功输出（200，节选）：

```json
{
  "status": "ok",
  "data": [
    {
      "regionType": "township",
      "regionId": "440281001",
      "displayName": "乐城街道",
      "areaCode": "440281001",
      "parentType": "county",
      "parentId": "440281",
      "selectable": true,
      "hasGeometry": true
    },
    {
      "regionType": "township",
      "regionId": "440281102",
      "displayName": "北乡镇",
      "areaCode": "440281102",
      "parentType": "county",
      "parentId": "440281",
      "selectable": true,
      "hasGeometry": true
    }
  ]
}
```

查询乐城街道下的村：

```http
GET /api/v1/farmland-statistics/regions?parent_type=township&parent_id=440281001
```

默认不返回 `zone` 类型的村间争议区。仅管理或核查界面需要时传 `include_disputes=true`。

### 2.1 获取行政边界 GeoJSON

**GET** `/api/v1/farmland-statistics/boundaries`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `region_type` | string | 是 | `province`、`city`、`county`、`township`、`village` 或 `zone` |
| `parent_type` / `parent_id` | string | 否 | 父级过滤，二者必须同时提供 |
| `bbox` | string | 否 | WGS84 范围，格式 `minLon,minLat,maxLon,maxLat` |
| `zoom` | number | 否 | 地图缩放级别，范围 0–24；低于该层级 `minZoom` 时返回空要素集 |

示例：

```http
GET /api/v1/farmland-statistics/boundaries?region_type=township&parent_type=county&parent_id=440281&zoom=10
```

响应是标准 GeoJSON `FeatureCollection`。每个要素包含 `regionType`、`regionId`、`displayName`、`areaCode`、父级、`selectable`、`minZoom` 和 `maxZoom`。当前最小缩放级别为省 3、市 5、县 7、镇 9、村/争议区 12；指定 `zoom` 时服务端按像素尺度简化几何。单次最多返回 5000 个要素，超过时 `truncated=true`，客户端应增加父级或 bbox 过滤。

### 3. 聚合耕地统计

**POST** `/api/v1/farmland-statistics/aggregate`

用途：按单个行政区域、多个同级行政区域、自定义多边形或地图视窗裁剪地块，生成表格、柱状图和饼图共用的数据。

输入示例 A——按村统计 pH：

```json
{
  "scope": {
    "type": "administrative_region",
    "region_type": "village",
    "region_id": "440281001201"
  },
  "metrics": ["soil_ph"]
}
```

输入示例 B——按当前地图视窗统计多个指标：

```json
{
  "scope": {
    "type": "viewport",
    "bbox": [113.0, 24.0, 114.0, 25.0]
  },
  "metrics": [
    "soil_ph",
    "organic_matter",
    "available_phosphorus"
  ]
}
```

`bbox` 使用 WGS84（EPSG:4326），顺序为 `[minLon, minLat, maxLon, maxLat]`。`metrics` 可传 `"all"`，也可传非空指标 key 数组；省略时统计全部 8 项。

输入示例 C——多个同级行政区联合统计：

```json
{
  "scope": {
    "type": "administrative_regions",
    "region_type": "county",
    "region_ids": ["440281", "440282"]
  },
  "metrics": ["soil_ph", "organic_matter"]
}
```

`region_ids` 不允许空值或重复值，一次最多 100 个，且必须全部属于同一 `region_type`。后端使用 `ST_Collect` + `ST_UnaryUnion` 消除重叠后再统计，响应 `scope.regions` 按请求顺序返回所选区域。

输入示例 D——圈选多边形统计：

```json
{
  "scope": {
    "type": "polygon",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[113.0, 24.0], [113.1, 24.0], [113.1, 24.1], [113.0, 24.0]]]
    }
  },
  "metrics": "all"
}
```

仅接受 WGS84 `Polygon` / `MultiPolygon`。线性环必须首尾闭合；最多 5000 个顶点、面积不超过 200000 平方公里。服务端使用 PostGIS 检查几何合法性并统一环方向。响应 `scope` 会返回几何类型、顶点数、面积和 SRID，但不会回传完整坐标。

成功输出（200，对应输入示例 A）：

```json
{
  "status": "ok",
  "data": {
    "classificationVersion": "2026-09-18.1",
    "dataAsOf": "2026-09-08T19:52:36.326614+08:00",
    "scopeSummary": {
      "parcelCount": 1,
      "totalAreaMu": 88.6022
    },
    "metrics": [
      {
        "key": "soil_ph",
        "metricKey": "soil_ph",
        "label": "酸化 pH 情况",
        "unit": "pH",
        "table": {
          "average": 5.32,
          "totalAreaMu": 88.6022,
          "parcelCount": 1,
          "validAreaMu": 88.6022,
          "validParcelCount": 1,
          "range": {
            "min": 5.32,
            "max": 5.32
          }
        },
        "distribution": [
          {
            "key": "very_strong_acid",
            "label": "极强酸性",
            "rangeLabel": "<4.5",
            "color": "#B2182B",
            "lower": null,
            "upper": 4.5,
            "lowerInclusive": false,
            "upperInclusive": false,
            "parcelCount": 0,
            "areaMu": 0.0,
            "countPercent": 0.0,
            "areaPercent": 0.0
          },
          {
            "key": "strong_acid",
            "label": "强酸性",
            "rangeLabel": "[4.5,5.5)",
            "color": "#EF8A62",
            "lower": 4.5,
            "upper": 5.5,
            "lowerInclusive": true,
            "upperInclusive": false,
            "parcelCount": 1,
            "areaMu": 88.6022,
            "countPercent": 100.0,
            "areaPercent": 100.0
          },
          {
            "key": "acid",
            "label": "酸性",
            "rangeLabel": "[5.5,6.5)",
            "color": "#FDDBC7",
            "lower": 5.5,
            "upper": 6.5,
            "lowerInclusive": true,
            "upperInclusive": false,
            "parcelCount": 0,
            "areaMu": 0.0,
            "countPercent": 0.0,
            "areaPercent": 0.0
          },
          {
            "key": "neutral",
            "label": "中性",
            "rangeLabel": "[6.5,7.5]",
            "color": "#92C5DE",
            "lower": 6.5,
            "upper": 7.5,
            "lowerInclusive": true,
            "upperInclusive": true,
            "parcelCount": 0,
            "areaMu": 0.0,
            "countPercent": 0.0,
            "areaPercent": 0.0
          },
          {
            "key": "alkaline",
            "label": "碱性",
            "rangeLabel": ">7.5",
            "color": "#2166AC",
            "lower": 7.5,
            "upper": null,
            "lowerInclusive": false,
            "upperInclusive": false,
            "parcelCount": 0,
            "areaMu": 0.0,
            "countPercent": 0.0,
            "areaPercent": 0.0
          }
        ],
        "unclassified": {
          "parcelCount": 0,
          "areaMu": 0.0
        }
      }
    ],
    "scope": {
      "type": "administrative_region",
      "regionType": "village",
      "regionId": "440281001201",
      "displayName": "榴村"
    }
  }
}
```

主要输出字段：

| 字段 | 用途 |
|------|------|
| `scopeSummary` | 当前统计范围内的全部地块数和裁剪后总面积 |
| `table.average` | 当前指标按裁剪后面积加权的平均值 |
| `table.totalAreaMu` / `parcelCount` | 表格展示的总面积和地块数 |
| `table.validAreaMu` / `validParcelCount` | 当前指标有有效值的面积和地块数 |
| `table.range` | 当前指标有效值的最小值和最大值 |
| `distribution` | 等级有序数组；柱状图使用 `parcelCount`，饼图可使用 `areaMu` 或 `parcelCount` |
| `unclassified` | 缺失、无法解析或未落入有效正值区间的数据 |
| `dataSource` / `measurementYear` / `isImputed` | 范围内来源一致时返回单值；混合来源时 `dataSource` 为 `mixed` |
| `provenanceSummary` | 范围内各来源字段的计数分布 |

地图缩放或平移后，前端在 `moveend` 使用新 bbox 重新调用本接口。建议做 300–500 ms 防抖并取消已经过期的请求。

### 4. 获取地块详情

**GET** `/api/v1/farmland-statistics/parcels/{parcel_id}`

输入示例：

```http
GET /api/v1/farmland-statistics/parcels/1007
Authorization: Bearer <token>
```

成功输出（200）：

```json
{
  "status": "ok",
  "data": {
    "classificationVersion": "2026-09-18.1",
    "parcelId": "1007",
    "areaCode": "440281",
    "areaMu": 379.8501,
    "qualityGrade": 8,
    "organicMatter": 19.178225,
    "soilPh": 5.578967,
    "availablePhosphorus": 27.682971,
    "availablePotassium": 82.5,
    "bulkDensity": 1.31,
    "plowLayerThickness": 20.0,
    "effectiveSoilDepth": 80.0,
    "metrics": {
      "available_potassium": {
        "metricKey": "available_potassium",
        "value": 82.5,
        "unit": "mg/kg",
        "bucketKey": "medium_low",
        "bucketLabel": "中低",
        "rangeLabel": "(50,100]",
        "color": "#FC8D59",
        "dataSource": "model1_shapefile",
        "measurementYear": 2024,
        "isImputed": false,
        "imputationMethod": null,
        "qualityFlag": "source_unverified"
      }
    }
  }
}
```

`areaMu` 为完整地块面积，单位为亩并保留 4 位小数；它不同于聚合统计中按范围裁剪后的面积。地块几何缺失时 `areaMu` 返回 `null`。指标缺失时，相应字段也返回 `null`，字段本身不会省略。每个 `metrics` 项还返回 `dataSource`、`measurementYear`、`isImputed`、`imputationMethod` 和 `qualityFlag`。

### 5. 按经纬度点选地块

**POST** `/api/v1/farmland-statistics/parcels/pick`

输入示例：

```json
{
  "longitude": 113.084486,
  "latitude": 25.094996,
  "metric": "soil_ph",
  "toleranceMeters": 8
}
```

成功输出（200）：

```json
{
  "status": "ok",
  "data": {
    "classificationVersion": "2026-09-18.1",
    "parcelId": "1007",
    "areaCode": "440281",
    "areaMu": 379.8501,
    "metric": {
      "metricKey": "soil_ph",
      "value": 5.58,
      "unit": "pH",
      "bucketKey": "acid",
      "bucketLabel": "酸性",
      "rangeLabel": "[5.5,6.5)",
      "color": "#FDDBC7",
      "dataSource": "model1_shapefile",
      "measurementYear": 2024,
      "isImputed": false,
      "imputationMethod": null,
      "qualityFlag": "source_unverified"
    },
    "hit": {
      "mode": "exact",
      "distanceMeters": 0.0,
      "toleranceMeters": 8.0
    }
  }
}
```

`metric` 省略时仍返回原有全部 8 项指标结构，以保持兼容。`toleranceMeters` 默认为 0、最大 50 米；精确命中优先，否则返回容差内最近地块。若多个地块同时覆盖该点，返回面积最小的地块；未命中返回 404。接口有 5 秒短时缓存和每用户 120 次/分钟保护，不应由浏览器无防抖地逐次响应 `mousemove`。

### 6. 当前视口轻量地块要素

**GET** `/api/v1/farmland-statistics/parcels/viewport`

```http
GET /api/v1/farmland-statistics/parcels/viewport?bbox=113,24,114,25&metric=soil_ph&geometry=centroid&limit=2000
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `bbox` | 是 | WGS84 `minLon,minLat,maxLon,maxLat` |
| `metric` | 是 | 8 项规范指标之一 |
| `geometry` | 否 | `centroid`（默认）、`simplified` 或 `none` |
| `zoom` | 否 | `simplified` 模式的简化尺度，默认 14 |
| `limit` | 否 | 默认 2000，最大 5000 |

响应 `data` 是 GeoJSON `FeatureCollection`。每个要素仅包含地块 ID、区域代码、当前指标值、等级、颜色、来源信息，以及所选形式的几何。超过 `limit` 时 `truncated=true`。该接口按用户限制为 60 次/分钟，适合前端批量加载后进行本地悬浮拾取。

### 7. 指标质量审计

**GET** `/api/v1/farmland-statistics/quality/audit`

返回全部 8 项指标的非空率、可解析数量、最小值、最大值、唯一值数量、未分类数量、质量标记及来源分布，结果缓存 5 分钟。当前审计识别出：

- 耕层厚度全部为 20 cm，`qualityFlags` 包含 `constant_value`。
- 有效土层厚度仅 4 个唯一值，`qualityFlags` 包含 `low_variability`。
- `isImputed=false` 只表示后端未执行回填，不代表数据提供方已确认田间实测。

离线报告可通过以下命令生成：

```powershell
.venv\Scripts\python.exe scripts/audit_farmland_indicators.py --format markdown
```

### 错误输出

统计业务错误使用统一包络：

```json
{
  "status": "error",
  "code": "invalid_scope",
  "message": "请求必须包含 scope 对象"
}
```

区域存在但尚未导入边界时：

```json
{
  "status": "error",
  "code": "region_geometry_missing",
  "message": "指定行政区域尚未导入边界"
}
```

点选未命中时：

```json
{
  "status": "error",
  "code": "parcel_not_found",
  "message": "该位置未命中地块"
}
```

| HTTP 状态码 | 常见 code | 说明 |
|-------------|-----------|------|
| 400 | `invalid_parent`、`invalid_request`、`invalid_scope`、`invalid_metrics`、`invalid_metric`、`invalid_coordinate`、`invalid_tolerance`、`invalid_bbox`、`invalid_zoom`、`invalid_geometry`、`invalid_geometry_mode`、`invalid_limit` | 输入参数或几何无效 |
| 401 | JWT 默认 `msg` 响应 | 未携带或无法验证 Token |
| 404 | `region_not_found`、`parcel_not_found` | 区域或地块不存在，或点选未命中 |
| 409 | `region_geometry_missing` | 区域存在但尚未导入边界 |
| 413 | `too_many_regions`、`geometry_too_complex`、`geometry_too_large` | 选择范围超过服务限制 |
| 429 | `rate_limited` | 点选或视口请求超过当前用户频率限制 |
| 500 | `internal_error` | 统计服务内部错误 |
| 503 | `statistics_unavailable` | 区域目录、空间统计或点选服务暂时不可用 |

## 当前数据结论与后续替换点

- 当前 5488 个地块不是单一县数据，而是分布在韶关多个县区并少量延伸到英德；此前 `area_code` 全部硬编码为新丰县 `440233`。
- 已按广东县界做空间审计，自动纠正仅限主导县覆盖比例不低于 95% 的地块。低置信地块保留原值并进入人工复核清单。
- 当前地块指标来自测试数据，接口可用于开发联调，但生产展示前仍需确认正式地块和指标数据源。
- 当前乐昌边界已切换登记为土壤所提供的广东 L2/L3/L4 数据源。该数据的几何沿袭信息指向 2016 年、导出元数据为 2020 年；它与此前乐昌独立边界逐要素完全相同。拿到真正更新的权威边界后，应沿用同一导入和差异审计流程替换。
