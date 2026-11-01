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

用途：执行县域结构化诊断。当前在缺少可验证统计或专业模型结果时，仅返回安全降级的定性建议，不返回固定模板数字。

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
| `status`               | `ok` 或 `degraded`；模板建议为 `degraded` |
| `result_kind`          | 模板建议为 `advisory_only` |
| `topic`                | 诊断主题             |
| `summary`              | 诊断摘要             |
| `evidence[]`           | 判定依据             |
| `key_areas[]`          | 重点区域提示         |
| `recommended_layers[]` | 建议联动图层         |
| `fallback`             | 回退字段与策略       |
| `lineage`              | 来源和运行时依赖说明 |
| `reliability`          | 包含 `predictive` 和 `quantitative_available` |
| `quantitative_estimates` | 定量结果可用状态与原因 |

模板建议中的 `period`、`improve`、`effect`、`cost` 和问题 `percent` 为 `null`，同时在相邻 `metric_meta` 中标记 `status=unavailable` 和机器可读原因。没有可靠空间统计时，`regions` 与 `base_data` 返回空数组。

非空定量字段只有在 `metric_meta` 同时提供以下依据时才可返回：

- `source`：数据来源。
- `method`：计算或统计方法。
- `calculated_at`：计算时间。
- `scope`：适用范围。
- `model_version`：使用模型时的模型版本。

旧客户端必须把 `degraded` 作为安全降级状态处理，对 `null` 显示“暂无可靠估计”，不得回填本地默认数字、固定周期或历史占位值。

错误码：

| 错误码               | 场景                     |
| -------------------- | ------------------------ |
| `INVALID_TOPIC`    | `topic` 不在支持列表内 |
| `UNSUPPORTED_AREA` | 当前区域不支持           |

## `POST /api/report/summary`

用途：将一次结构完整的 `ok` 或 `degraded` 诊断结果整理为可被前端或未来 Agent 二次加工的摘要。

请求体：直接传入 `POST /api/county/diagnose` 响应中的诊断结果。摘要保留原始 `status`、`result_kind`、`reliability` 和定量不可用状态，不会从 `null` 推断数字。

关键响应字段：

| 字段                  | 说明       |
| --------------------- | ---------- |
| `summary`           | 结论摘要   |
| `findings[]`        | 关键发现   |
| `recommendations[]` | 治理建议   |
| `actions[]`         | 后续行动项 |
| `source`            | 摘要来源   |
| `result_kind`       | 原诊断结果性质 |
| `reliability`       | 原诊断可靠性状态 |
| `quantitative_estimates` | 原诊断定量可用状态 |

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

## `POST /api/v1/report/generate` 的状态与数字审计

报告生成的响应在原有字段之外新增三项，调用方需按下表理解：

| 字段          | 说明                                                                 |
| ------------- | -------------------------------------------------------------------- |
| `status`      | 可能为 `ok` 或 `degraded`。生成后审计发现无依据定量内容时为 `degraded` |
| `audit`       | 审计结果：`checked_claims`、`grounded_claims`、`ungrounded_claims`、`issues[]` |
| `issues[]`    | 稳定问题码列表，当前为 `UNGROUNDED_QUANTITATIVE_CLAIM`               |

审计口径：

- 白名单来源是报告上下文与 `data` 章节渲染结果，语言模型章节只允许引用其中已有的数值；
- 被审计的表述限定为带单位或非 0 数值语义的内容（百分比、`g/kg`、`mg/kg`、`kg/亩`、`元/亩`、`cm`、pH 数值，以及预测性句子中的时长）；
- 无法追溯的数值在正文中替换为“暂无可靠估计”，并在 `audit.issues[]` 记录章节、原始数值和说明；
- 数据章节不参与替换，只作为白名单来源。

被回填输入的披露：报告的“数据来源与计算依据”小节会列出被区域平均回填或使用默认值的输入字段（来自模型结果的 `imputed_features` / `imputed_inputs` 与地块来源标记），该内容由数据驱动，不由语言模型生成。

兼容说明：旧调用方若只判断 `status == "ok"`，需要同时接受 `degraded`，并按 `audit` 判断报告是否需要人工复核；不解析 `audit` 时，正文中的“暂无可靠估计”已是安全表述。
