# 基础能力接口契约

## 运行方式

当前实现提供两类调用方式：

- Python API：适合后续 Agent 工具封装直接导入。
- 标准库 HTTP Server：适合前端或外部流程先做轻量联调。

CLI 示例：

```powershell
$env:PYTHONPATH="src"
python -m ai_culti_demo.cli overview
python -m ai_culti_demo.cli diagnose --topic acidification
python -m ai_culti_demo.cli report --topic improvement
python -m ai_culti_demo.cli models
python -m ai_culti_demo.cli model --model-id acidification-governance
python -m ai_culti_demo.cli verify
```

HTTP Server 示例：

```powershell
$env:PYTHONPATH="src"
python -m ai_culti_demo.http_server
```

## `GET /api/county/overview`

用途：返回乐昌市县域总览、可用图层、图层来源和可靠性说明。

查询参数：

| 参数          | 必填 | 默认值      | 说明             |
| ------------- | ---- | ----------- | ---------------- |
| `area_code` | 否   | `lechang` | 当前仅支持乐昌市 |

关键响应字段：

| 字段                  | 说明                         |
| --------------------- | ---------------------------- |
| `status`            | `ok` 或 `error`          |
| `area`              | 区域编码、名称、层级         |
| `layers[]`          | 可用图层列表                 |
| `layers[].source[]` | 图层来源资产                 |
| `lineage`           | 数据目录、源根路径和隐私说明 |
| `reliability`       | 可靠性等级与说明             |

## `POST /api/county/diagnose`

用途：执行县域结构化诊断，当前首版使用规则占位结果，后续可替换真实模型。

请求体：

```json
{
  "topic": "acidification",
  "area_code": "lechang",
  "longitude": 113.35,
  "latitude": 25.13
}
```

参数说明：

| 参数           | 必填 | 说明                                                |
| -------------- | ---- | --------------------------------------------------- |
| `topic`      | 是   | 支持`acidification`、`quality`、`improvement` |
|  `area_code` | 否   | 当前仅支持`lechang`                               |
| `longitude`  | 否   | 缺失时使用县域级诊断                                |
| `latitude`   | 否   | 缺失时使用县域级诊断                                |

关键响应字段：

| 字段                     | 说明                 |
| ------------------------ | -------------------- |
| `diagnosis_id`         | 诊断结果标识         |
| `topic`                | 诊断主题             |
| `summary`              | 诊断摘要             |
| `evidence[]`           | 判定依据             |
| `key_areas[]`          | 重点区域提示         |
| `recommended_layers[]` | 建议联动图层         |
| `fallback`             | 回退字段与策略       |
| `lineage`              | 来源和运行时依赖说明 |

错误码：

| 错误码               | 场景                     |
| -------------------- | ------------------------ |
| `INVALID_TOPIC`    | `topic` 不在支持列表内 |
| `UNSUPPORTED_AREA` | 当前区域不支持           |

## `POST /api/report/summary`

用途：将一次成功诊断结果整理为可被前端或未来 Agent 二次加工的摘要。

请求体：直接传入 `POST /api/county/diagnose` 的成功响应。

关键响应字段：

| 字段                  | 说明       |
| --------------------- | ---------- |
| `summary`           | 结论摘要   |
| `findings[]`        | 关键发现   |
| `recommendations[]` | 治理建议   |
| `actions[]`         | 后续行动项 |
| `source`            | 摘要来源   |

## `GET /api/runtime/verify`

用途：验证当前仓库独立运行状态和非侵入式约束。

关键响应字段：

| 字段                     | 说明                                       |
| ------------------------ | ------------------------------------------ |
| `checks[]`             | 本地目录、外部运行依赖和只读参考约束检查   |
| `reference_projects[]` | 历史项目路径是否存在，以及是否为运行时依赖 |

## `GET /api/models`

用途：返回当前仓库可供大模型或 Agent 调用的模拟专题模型目录。

查询参数：

| 参数        | 必填 | 默认值      | 说明             |
| ----------- | ---- | ----------- | ---------------- |
| `area_code` | 否   | `lechang` | 当前仅支持乐昌市 |

响应示例：

```json
{
  "status": "ok",
  "area": {
    "code": "lechang",
    "name": "乐昌市",
    "level": "county",
    "province": "广东省"
  },
  "models": [
    {
      "model_id": "spatial-structure-analysis",
      "name": "耕地质量空间结构解析模型",
      "purpose": "按区域、类型和图层组织县域耕地质量空间结构，用于总览和空间分区研判。",
      "minimum_inputs": ["area_code"],
      "recommended_layers": ["boundary", "cropland", "quality-overview"]
    },
    {
      "model_id": "soil-indicator-analysis",
      "name": "土壤关键指标多维解析模型",
      "purpose": "围绕 pH、有机质和养分等关键指标做多维占位解析，用于支撑专题判断。",
      "minimum_inputs": ["area_code"],
      "recommended_layers": ["soil_points", "organic-matter", "acidification-risk"]
    },
    {
      "model_id": "obstacle-factor-identification",
      "name": "耕地质量主要障碍因素识别模型",
      "purpose": "识别限制耕地质量提升的主要障碍因素，并输出分级治理方向。",
      "minimum_inputs": ["area_code"],
      "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"]
    },
    {
      "model_id": "acidification-governance",
      "name": "土壤酸化治理模型",
      "purpose": "对酸化问题进行占位识别、治理需求分析和措施匹配。",
      "minimum_inputs": ["area_code"],
      "recommended_layers": ["acidification-risk", "soil_points"]
    },
    {
      "model_id": "organic-matter-improvement",
      "name": "土壤有机质提升模型",
      "purpose": "对有机质不足问题进行占位识别、提升需求分析和措施匹配。",
      "minimum_inputs": ["area_code"],
      "recommended_layers": ["organic-matter", "soil_points", "cropland"]
    },
    {
      "model_id": "multi-factor-collaborative-improvement",
      "name": "耕地质量多项协同提升模型",
      "purpose": "综合多个专题模型的占位结果，形成分区分类的综合提升建议。",
      "minimum_inputs": ["area_code"],
      "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
      "dependent_models": [
        "acidification-governance",
        "organic-matter-improvement",
        "obstacle-factor-identification"
      ]
    }
  ],
  "lineage": {
    "catalog": "data/lechang/catalog.json",
    "runtime_dependency": "none"
  },
  "reliability": {
    "level": "demo_stub",
    "message": "当前专题模型结果仅用于 Demo 演示多模型调用契约，不代表真实专业模型结论。"
  }
}
```

关键响应字段：

| 字段                  | 说明                               |
| --------------------- | ---------------------------------- |
| `status`              | `ok` 或 `error`                    |
| `area`                | 当前模型目录对应区域               |
| `models[]`            | 可调用模型清单                     |
| `models[].model_id`   | 模型唯一标识                       |
| `models[].purpose`    | 模型用途说明                       |
| `models[].minimum_inputs` | 模型最小输入字段列表          |
| `models[].recommended_layers` | 建议联动图层列表         |
| `models[].dependent_models` | 仅协同模型返回的依赖模型列表 |
| `lineage`             | 目录来源和运行时依赖说明           |
| `reliability`         | Demo 可靠性说明                    |

## `POST /api/models/run`

用途：按 `model_id` 调用单个模拟专题模型，返回统一结构化结果。

请求体示例：

```json
{
  "model_id": "multi-factor-collaborative-improvement",
  "area_code": "lechang"
}
```

参数说明：

| 参数        | 必填 | 说明                           |
| ----------- | ---- | ------------------------------ |
| `model_id`  | 是   | 6 个已注册模拟专题模型之一     |
| `area_code` | 否   | 当前仅支持 `lechang`           |
| `longitude` | 否   | 缺失时按县域级占位结果返回     |
| `latitude`  | 否   | 缺失时按县域级占位结果返回     |
| `indicators`| 否   | 关键指标模型或协同模型可选使用 |
| `context`   | 否   | 调用方透传的附加上下文         |

响应示例：

```json
{
  "status": "ok",
  "model": {
    "model_id": "multi-factor-collaborative-improvement",
    "name": "耕地质量多项协同提升模型",
    "purpose": "综合多个专题模型的占位结果，形成分区分类的综合提升建议。",
    "minimum_inputs": ["area_code"],
    "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
    "dependent_models": [
      "acidification-governance",
      "organic-matter-improvement",
      "obstacle-factor-identification"
    ]
  },
  "area": {
    "code": "lechang",
    "name": "乐昌市",
    "level": "county",
    "province": "广东省"
  },
  "summary": "多项协同提升模型已综合多个专题模型的 Demo 结果，形成分区分类的综合建议。",
  "findings": [
    {
      "title": "协同组合",
      "content": "协同提升模型综合酸化治理、障碍识别和有机质提升等专题结果生成总建议。"
    },
    {
      "title": "分区分类",
      "content": "首版按全县重点治理区、常规提升区和持续监测区三类输出综合方向。"
    }
  ],
  "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"],
  "recommendations": [
    "先按主要障碍与提升主题划分重点治理区。",
    "后续可在镇域或格网尺度叠加真实模型输出做精细分区。"
  ],
  "lineage": {
    "catalog": "data/lechang/catalog.json",
    "referenced_assets": [
      "D:\\work\\AcidMap",
      "D:\\work\\suan\\AcidificationModel\\api"
    ],
    "runtime_dependency": "none",
    "recommended_layers": ["quality-overview", "acidification-risk", "organic-matter"]
  },
  "reliability": {
    "level": "demo_stub",
    "message": "当前专题模型结果仅用于 Demo 演示多模型调用契约，不代表真实专业模型结论。"
  },
  "fallback": {
    "used": true,
    "fields": ["longitude", "latitude", "indicators"],
    "strategy": "缺少坐标时按县域级占位结果返回；缺少指标时使用 Demo 默认上下文补齐。"
  },
  "dependent_models": [
    "acidification-governance",
    "organic-matter-improvement",
    "obstacle-factor-identification"
  ],
  "zoning_recommendations": [
    {
      "zone": "重点治理区",
      "focus": "酸化风险与综合障碍叠加区域优先核验并治理。"
    },
    {
      "zone": "常规提升区",
      "focus": "以有机质提升和耕地培肥措施为主，保持常态化改良。"
    },
    {
      "zone": "持续监测区",
      "focus": "维持监测和图层复核，为后续真实模型替换保留比对基线。"
    }
  ]
}
```

关键响应字段：

| 字段                     | 说明                                 |
| ------------------------ | ------------------------------------ |
| `status`                 | `ok` 或 `error`                      |
| `model`                  | 当前调用模型的元数据                 |
| `summary`                | 本次模型调用的摘要                   |
| `findings[]`             | 关键发现列表                         |
| `recommended_layers[]`   | 建议联动图层                         |
| `recommendations[]`      | 治理或分析建议                       |
| `lineage`                | 来源目录、参考资产和运行时依赖说明   |
| `reliability`            | Demo 可靠性说明                      |
| `fallback`               | 缺失字段时的回退说明                 |
| `dependent_models[]`     | 协同模型返回的依赖模型列表           |
| `zoning_recommendations[]` | 协同模型返回的分区分类建议         |

错误码：

| 错误码               | 场景                             |
| -------------------- | -------------------------------- |
| `MISSING_MODEL_ID`   | 请求体缺少 `model_id`            |
| `INVALID_MODEL_ID`   | `model_id` 不在 6 个模型目录中   |
| `UNSUPPORTED_AREA`   | 当前区域不支持                   |
