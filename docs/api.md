# API 文档

> 版本: v1
> 前缀: `/api/v1/`
> 认证: JWT Token（放在 `Authorization: Bearer <token>` 头中）

---

## 基础响应格式

所有接口统一返回 JSON 格式：

```json
{
    "status": "ok",
    "data": {},
    "message": "操作成功"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `ok` 或 `error` |
| `data` | any | 返回数据 |
| `message` | string | 提示信息（error 时为错误原因） |

---

## 认证接口

### 登录

**POST** `/api/v1/auth/login`

请求体：
```json
{
    "username": "admin",
    "password": "your_password"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 用户名 |
| `password` | string | 是 | 密码 |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
        "user": {
            "id": 1,
            "username": "admin",
            "nickname": "系统管理员",
            "role": "admin",
            "status": 1
        }
    },
    "message": "登录成功"
}
```

失败响应（401）：
```json
{
    "status": "error",
    "message": "用户名或密码错误"
}
```

---

### 注册用户

**POST** `/api/v1/auth/register`

> 需要管理员权限（admin）

请求体：
```json
{
    "username": "newuser",
    "password": "password123",
    "nickname": "新用户",
    "role": "user"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 用户名 |
| `password` | string | 是 | 密码 |
| `nickname` | string | 否 | 昵称（默认等于 username） |
| `role` | string | 否 | 角色（`admin` 或 `user`，默认 `user`） |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "id": 2,
        "username": "newuser",
        "nickname": "新用户",
        "role": "user",
        "status": 1
    },
    "message": "用户创建成功"
}
```

---

### 获取当前用户

**GET** `/api/v1/auth/me`

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "id": 1,
        "username": "admin",
        "nickname": "系统管理员",
        "role": "admin",
        "status": 1
    }
}
```

---

## 聊天接口

### 获取对话列表

**GET** `/api/v1/chat/conversations`

成功响应（200）：
```json
{
    "status": "ok",
    "data": [
        {
            "id": 1,
            "title": "如何治理强酸性耕地？",
            "user_id": 1,
            "create_time": "2026-07-13 10:00:00",
            "update_time": "2026-07-13 10:05:00"
        }
    ]
}
```

---

### 创建对话

**POST** `/api/v1/chat/conversations`

请求体：
```json
{
    "title": "新对话"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 否 | 对话标题（默认"新对话"） |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "id": 2,
        "title": "新对话",
        "user_id": 1,
        "create_time": "2026-07-13 11:00:00",
        "update_time": "2026-07-13 11:00:00"
    },
    "message": "对话创建成功"
}
```

---

### 删除对话

**DELETE** `/api/v1/chat/conversations/{id}`

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 对话 ID |

成功响应（200）：
```json
{
    "status": "ok",
    "message": "对话删除成功"
}
```

---

### 获取对话消息

**GET** `/api/v1/chat/conversations/{id}/messages`

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 对话 ID |

成功响应（200）：
```json
{
    "status": "ok",
    "data": [
        {
            "id": 1,
            "conversation_id": 1,
            "role": "user",
            "content": "如何治理强酸性耕地？",
            "sources": null,
            "create_time": "2026-07-13 10:00:00"
        },
        {
            "id": 2,
            "conversation_id": 1,
            "role": "assistant",
            "content": "根据评估结果...",
            "sources": [{"doc_name": "土壤治理指南.pdf"}],
            "create_time": "2026-07-13 10:01:00"
        }
    ]
}
```

---

### 智能问答（核心接口）

**POST** `/api/v1/chat/`

统一智能路由入口，根据问题类型（question_type）自动路由：
- **question_type=0** → RAG 链（知识性问题，如「什么是土壤酸化」「耕地质量等级是什么意思」）
- **question_type=1** → model-1 稳定性风险识别（等级稳定性/退化风险）
- **question_type=2** → model-2 耕地质量等级评价（综合指数/质量等级/障碍度排序）
- **question_type=3** → model-3 障碍诊断（障碍因素/主要问题/障碍组合）
- **question_type=4** → model-4 酸化改良（酸化程度/调理剂/改良方案）
- **question_type=5** → model-5 有机质培肥 ML（SOC/Dose/预测置信度）
- **question_type=6** → model-6 占位能力（不加载肥力 RF）

> 路由采用 1:1 映射：每个 question_type 仅调用对应的单一专业智能体，不再按用户角色固定调用多个模型组合。

#### Schema 协议

本接口响应遵循 **Schema 2.0** 信封，通过请求体可选字段切换投影：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `response_schema` | string | `"2.0"` | 响应信封版本，取值 `"1.0"` 或 `"2.0"`；其他值返回 400 |
| `include_model_results` | bool | `false` | 是否在响应中返回 `models` 投影。`true` 且 `question_type≠0` 时返回 `chat_compact` 投影 |

- **Schema 2.0**（默认）：返回规范信封，含 `schema_version`、`trace_id`、`routing`、`analysis_context`、`provenance` 等字段
- **Schema 1.0**（兼容期）：将 `models` 转换为旧 `model_results.findings/evidence` 结构，并附 `deprecation` 警告。建议尽快迁移到 2.0

#### 请求体

```json
{
    "message": "我的田有机质培肥施用量多少？",
    "conversation_id": 1,
    "area_code": "lechang",
    "parcel_id": "1460",
    "parcel_code": "A0001",
    "land_type": "upland",
    "fertilizer_type": "compound",
    "response_schema": "2.0",
    "include_model_results": true,
    "context": {
        "target_ph": 6.0,
        "soil_depth": 20,
        "bulk_density": 1.2,
        "safety_factor": 1.3,
        "current_ph": 5.5,
        "nitrogen_rates": [0, 50, 100, 150, 200],
        "area_code": "lechang"
    }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 用户问题（非空字符串） |
| `conversation_id` | int | 否 | 对话 ID，不传则创建新对话（标题取 message 前 50 字符） |
| `area_code` | string | 否 | 区域代码（默认 `lechang`，model-1/3/4 按 area_code 查 DB） |
| `parcel_id` | string | 否 | 地块 ID（数字字符串，model-1/3/4 查 DB；农户端问题或 type 5 问题建议携带） |
| `parcel_code` | string | 否 | 地块代码（字母数字，model-2 质量等级评价使用） |
| `land_type` | string | 否 | 土地利用类型（`upland` 旱地 / `paddy` 水田；model-5 韶关区域按此选择 RF 子模型，默认 `upland`） |
| `fertilizer_type` | string | 否 | 肥料类型（`compound` 复合肥 / `urea` 尿素，默认 `compound`；model-4 与 `land_type` 组合选择 4 子模型） |
| `response_schema` | string | 否 | 响应信封版本（`"1.0"` 或 `"2.0"`，默认 `"2.0"`） |
| `include_model_results` | bool | 否 | 是否返回 `models` 投影（默认 `false`） |
| `analysis_context` | object | 否 | 分析对象上下文（含 `action`/`expected_version`/`object`，详见[聊天分析对象与情景试算](#聊天分析对象与情景试算)） |
| `calculation_mode` | string | 否 | `"scenario"` 触发无空间对象的情景试算（默认走 spatial 模式） |
| `context` | object | 否 | 专业模型参数（如下表） |

`context` 参数说明：

| 参数 | 类型 | 说明 |
|------|------|------|
| `target_ph` | float | 目标 pH 值（默认 6.0） |
| `soil_depth` | float | 土壤深度（cm，默认 20） |
| `bulk_density` | float | 土壤容重（g/cm³，默认 1.2） |
| `safety_factor` | float | 安全系数（默认 1.3） |
| `current_ph` | float | 当前 pH 值（默认 5.5） |
| `nitrogen_rates` | array | 氮肥施用量序列（kg/ha，默认 [0, 50, 100, 150, 200]） |
| `area_code` | string | 区域代码（默认 `lechang`） |

> 顶层字段（如 `area_code`、`parcel_id`、`land_type`、`fertilizer_type`、`pH`、`SOCbe`、`SJD`、`YJZ` 等）会被合并到 orchestrator_request，优先级高于 `context` 内的同名字段。RF 特征字段（`pH`/`SOCbe`/`SOMbe`/`TN`/`TP`/`TK`/`AP`/`AK`/`Gap`/`Dose`/`SJD`/`YJZ`/`TD`/`TL`/`TJ`/`YXL`/`SXJ`/`YJZTSZ`/`YJFLX`）由顶层传入。

#### 成功响应（200）

```json
{
    "schema_version": "2.0",
    "trace_id": "01H...XYZ",
    "status": "ok",
    "data": {
        "message_id": 3,
        "answer": "根据评估结果，建议施用...",
        "sources": [{"doc_name": "土壤治理指南.pdf"}],
        "recommendations": ["预测结果仅供辅助决策，请结合田间试验复核"],
        "routing": {
            "question_type": 5,
            "status": "normal"
        },
        "interaction_state": "completed",
        "analysis_context": {
            "mode": "spatial",
            "version": 1,
            "object": {
                "type": "parcel",
                "id": "1460",
                "display_name": "乐昌市-耕地1460",
                "area_code": "lechang",
                "parent_path": [
                    {"type": "province", "id": "GD", "display_name": "广东省", "area_code": null},
                    {"type": "city", "id": "SG", "display_name": "韶关市", "area_code": null},
                    {"type": "county", "id": "LC", "display_name": "乐昌市", "area_code": "lechang"}
                ],
                "source": "parcel_registry",
                "validated_at": "2026-09-02T10:00:00+08:00"
            },
            "trace_id": "01H...XYZ",
            "provenance": { "...见 provenance 结构..." : "..." }
        },
        "provenance": {
            "trace_id": "01H...XYZ",
            "model_id": "organic-matter-improvement",
            "model_version": "SG_RF_v2_20260804",
            "data_as_of": "2026-08-04T00:00:00+08:00",
            "data_version": "v1",
            "calculated_at": "2026-09-02T02:00:00+00:00",
            "key_inputs": {"parcel_id": "1460", "area_code": "lechang", "land_type": "upland"},
            "scenario_result": false,
            "spatial_object": { "...同 analysis_context.object..." : "..." },
            "object_title": "分析对象：乐昌市-耕地1460"
        },
        "scenario_result": false,
        "spatial_object": { "...同 analysis_context.object..." : "..." },
        "object_title": "分析对象：乐昌市-耕地1460",
        "required_object_types": [],
        "missing_inputs": [],
        "models": {
            "model-5": {
                "model_id": "organic-matter-improvement",
                "status": "ok",
                "subject": {"type": "parcel", "id": "1460"},
                "result": {
                    "soc_prediction": 24.1,
                    "dose_prediction": 312.4,
                    "soc_confidence": 0.96,
                    "dose_confidence": 0.88,
                    "region": "lechang",
                    "land_type": "upland",
                    "imputed_features": []
                },
                "meta": {
                    "data_source": "database",
                    "simulated": false,
                    "model_version": "SG_RF_v2_20260804"
                },
                "issues": []
            }
        },
        "trace_id": "01H...XYZ"
    }
}
```

> `models` 仅在 `include_model_results=true` 且 `question_type≠0` 时返回。`include_model_results=false` 时响应中无 `models` 字段。

#### 响应字段说明

**顶层信封**

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | string | 响应信封版本（`"1.0"` 或 `"2.0"`） |
| `trace_id` | string | 全链路追踪 ID（用于日志关联） |
| `status` | string | `"ok"` 或 `"error"` |
| `data` | object | 响应数据 |

**`data` 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `message_id` | int | 本次回答的消息 ID（已持久化到 message 表） |
| `answer` | string | 综合回答内容（model 输出由 LLM 总结；若 provenance 流式补充，会前置 `object_title`） |
| `sources` | array | RAG 引用文档列表（仅 question_type=0 或 RAG 命中时返回） |
| `recommendations` | array | 综合建议列表 |
| `routing` | object | 路由信息 `{question_type, status}` |
| `routing.question_type` | int | 0-6（见路由说明） |
| `routing.status` | string | `normal` / `fallback` / `degraded` 等路由状态 |
| `interaction_state` | string | 交互状态，决定前端是否需要补充输入（见下表） |
| `analysis_context` | object | 本次请求的分析上下文快照（见下表） |
| `provenance` | object | 结果溯源信息（见下表） |
| `scenario_result` | bool | 是否为情景试算结果（无具体空间对象） |
| `spatial_object` | object\|null | 空间对象详情（情景试算时为 null） |
| `object_title` | string | 对象标题（"分析对象：xxx" 或 "情景试算，非具体空间对象结果"） |
| `required_object_types` | array | 当 `interaction_state=needs_analysis_object` 时返回，提示可接受的对象类型 |
| `missing_inputs` | array | 当 `interaction_state=needs_scenario_inputs` 时返回，提示缺失的输入字段名 |
| `models` | object | 仅当 `include_model_results=true` 且 `question_type≠0` 时返回，键为 agent_id（如 `"model-5"`） |
| `trace_id` | string | 与顶层 trace_id 相同 |

RAG 回答在正文中使用 `[1]`、`[2]` 顺序编码，并在末尾按 GB/T 7714 常用格式附加“参考文献”，不再展示“文档1”、“文档2”。`data.sources` 中的每个命中片段保留 `doc_name`、`chunk_index`、`page`；有书目元数据时还包含 `citation_number`、`citation`、`title`、`authors`、`journal`、`publication_year` 和 `doi`。同一篇文献的多个片段共用同一 `citation_number`；缺失字段不会由模型自行补写。

> Schema 1.0 模式下，`models` 字段会被 `legacy_projection` 转换为 `model_results` 旧结构（含 `findings`/`evidence`/`reliability`/`fallback` 等），并在顶层附加 `deprecation` 字段。

#### `interaction_state` 状态码

| 取值 | 含义 | 触发条件 | 前端处理建议 |
|------|------|----------|-------------|
| `completed` | 正常完成 | 通过 guard 校验，模型成功执行 | 直接展示 `answer` |
| `needs_analysis_object` | 需要空间对象 | 专业能力要求 spatial 模式但 `analysis_context.object` 缺失或类型不匹配 | 提示用户选择地块/区域；`required_object_types` 列出可接受类型 |
| `needs_scenario_inputs` | 需要补充情景试算输入 | 情景模式但缺少能力声明的必填输入 | 提示用户补充；`missing_inputs` 列出缺失字段 |

#### `analysis_context` 结构

```json
{
    "mode": "spatial",         // "spatial" 或 "scenario"
    "version": 1,              // scenario 模式为 null
    "object": {                // scenario 模式为 null
        "type": "parcel",      // province | city | county | zone | parcel
        "id": "1460",
        "display_name": "乐昌市-耕地1460",
        "area_code": "lechang",
        "parent_path": [
            {"type": "province", "id": "GD", "display_name": "广东省", "area_code": null}
        ],
        "source": "parcel_registry",
        "validated_at": "2026-09-02T10:00:00+08:00"
    },
    "trace_id": "01H...XYZ",
    "provenance": { "...同顶层 provenance..." : "..." }
}
```

#### `provenance` 结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | string | 链路追踪 ID |
| `model_id` | string | 能力标识（如 `organic-matter-improvement`） |
| `model_version` | string | 模型版本号（如 `SG_RF_v2_20260804`）；缺失时为 `"unknown"` |
| `data_as_of` | string\|null | 数据时间戳（ISO-8601） |
| `data_version` | string\|null | 数据版本 |
| `calculated_at` | string | 计算时间（ISO-8601，UTC） |
| `key_inputs` | object | 安全白名单内的输入字段（`parcel_id`/`area_code`/`land_type`/`fertilizer_type`/`pH`/`SOCbe`/`SJD`/`YJZ` 等） |
| `scenario_result` | bool | 是否为情景试算（无空间对象） |
| `spatial_object` | object\|null | 空间对象（同 `analysis_context.object`）；scenario 模式为 null |
| `object_title` | string | 对象标题（"分析对象：xxx" 或 "情景试算，非具体空间对象结果"） |

> `provenance` 仅在 `interaction_state=completed` 且存在 `trace_id` 与能力匹配时生成；其他情况可能缺失。

#### `models` 字段（`include_model_results=true` 时）

`models` 是以 agent_id（如 `model-5`）为键的对象，值为 `chat_compact` 投影：

```json
{
    "model-5": {
        "model_id": "organic-matter-improvement",
        "status": "ok",
        "subject": {"type": "parcel", "id": "1460"},
        "result": { "...模型特定业务结果..." : "..." },
        "meta": {
            "data_source": "database",
            "simulated": false,
            "model_version": "SG_RF_v2_20260804"
        },
        "issues": []
    }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `model_id` | string | 能力标识 |
| `status` | string | `ok` / `degraded` / `rejected` / `unavailable` / `error` |
| `subject` | object | 主体 `{type: parcel\|area\|unknown, id: str}` |
| `result` | object\|null | 模型特定业务结果（失败时为 null） |
| `meta` | object | `{data_source, simulated, model_version}` |
| `issues` | array | 问题列表 `[{code, severity, message, field?, details?}]` |

**`status` 取值**

| 取值 | 含义 |
|------|------|
| `ok` | 模型成功执行 |
| `degraded` | 部分结果或使用替代数据 |
| `rejected` | 输入不满足模型约束（如缺少必填字段、超出范围） |
| `unavailable` | 模型能力不可用（如 sklearn 缺失、模型文件不存在） |
| `error` | 执行异常 |

**各 model 的 `result` 字段结构**（`chat_compact` 投影后）

| model | result 字段 |
|-------|------------|
| `model-1` | `region`, `score`, `grade`, `modules`（仅保留 `score`/`grade`/`risk_level`/`退化风险等级`/`稳定性得分`） |
| `model-2` | `quality_grade`, `composite_index`, `indicators`, `obstacle_degree` |
| `model-3` | `obstacle_type`, `primary_factors`, `secondary_factors`, `obstacle_degrees`, `obstacle_levels`, `obstacle_combination` |
| `model-4` | `acidification_level`, `background_acid`, `acid_deposition_input`, `crop_acid_output`, `nitrogen_cycle_acid`, `agricultural_acid`, `soil_conditioner_dosage` (ytk), `woody_peat_dosage` (mbnt), `sub_model` |
| `model-5` | `soc_prediction`, `dose_prediction`, `soc_confidence`, `dose_confidence`, `region`, `land_type`, `imputed_features` |
| `model-6` | 始终为 `unavailable`，result 为 null |

#### 错误响应

**Schema 协议错误（400）**

```json
{
    "schema_version": "2.0",
    "status": "error",
    "error": {
        "code": "INVALID_RESPONSE_SCHEMA",
        "message": "response_schema 仅支持 1.0 或 2.0"
    }
}
```

**分析上下文错误（409 / 422 / 503）**

```json
{
    "status": "error",
    "error": {
        "code": "analysis_object_invalid",
        "message": "会话不存在或无权访问",
        "details": {}
    }
}
```

| HTTP 状态码 | code | 触发场景 |
|-------------|------|----------|
| 409 | `analysis_context_conflict` | 分析上下文冲突 |
| 422 | `analysis_object_invalid` | 请求体非法或会话不存在/无权访问 |
| 422 | `legacy_identifier_ambiguity` | 旧标识符歧义 |
| 503 | `analysis_object_validation_unavailable` | 对象校验服务不可用 |

> 注：API 响应不再包含 `role` 字段（已移除）。客户端应使用 `routing.question_type` 字段判断问题类型。

---

### 流式智能问答

**POST** `/api/v1/chat/stream`

与 `/api/v1/chat/` 行为一致，但响应为 **SSE（Server-Sent Events）** 流式输出，便于前端逐 token 渲染。

#### 请求

与 `/api/v1/chat/` 完全相同的请求体（含 `response_schema` / `include_model_results`）。

#### 响应

`Content-Type: text/event-stream`，每行 `data: {JSON}\n\n`，事件类型如下：

| 事件 | payload | 说明 |
|------|---------|------|
| `token` | `{event: "token", content: "..."}` | 增量生成的文本 token |
| `meta` | `{event: "meta", data: {...}}` | 路由/元信息（如 question_type 提前告知前端） |
| `done` | `{event: "done", data: {...}}` | 完整响应数据，`data` 结构与 `/api/v1/chat/` 的 `data` 一致 |
| `error` | `{event: "error", message: "..."}` | 流式过程中发生的错误 |

**示例 token 事件**

```
data: {"event":"token","content":"根据"}

data: {"event":"token","content":"评估"}
```

**示例 done 事件**

```
data: {"event":"done","data":{"message_id":3,"answer":"...","sources":[...],"routing":{"question_type":5,"status":"normal"},"interaction_state":"completed","analysis_context":{...},"provenance":{...},"trace_id":"01H...XYZ"}}
```

#### 注意事项

- 请求和响应信封结构与 `/api/v1/chat/` 完全一致
- SSE 响应头：`Cache-Control: no-cache, no-transform, must-revalidate, max-age=0`、`Connection: keep-alive`、`Content-Encoding: identity`（关闭 gzip 以防缓冲）
- 生成器内部已手动推入 Flask 应用上下文，db 写入不会触发 "Working outside of application context"

---

### 酸化改良（model-4，question_type=2）

酸化改良模型已从规则导向（GB/T 42817-2023 石灰剂量）替换为**过程模型**（移植自模型5源码），按 `land_type` × `fertilizer_type` 组合选择 4 个子模型之一，计算亿土康（YTK）与木本泥炭（MBNT）需求量。

#### 4 个子模型

| land_type | fertilizer_type | sub_model 名称 |
|-----------|-----------------|----------------|
| `paddy`（水田） | `urea`（尿素） | `paddy_urea` |
| `paddy`（水田） | `compound`（复合肥） | `paddy_compound` |
| `upland`（旱地） | `urea`（尿素） | `upland_urea` |
| `upland`（旱地） | `compound`（复合肥） | `upland_compound` |

#### 输入参数

模型输入通过 `context.data`（或 `context.task`）传递，`land_type` / `fertilizer_type` / `parcel_id` 也可在请求体顶层传递（顶层优先级高于 context）。

**必填输入：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `SJD` | float | 土壤 pH 值（三普标准指标代码，对应 pHstart） |
| `JHX` | float | 交换性氢（cmol/kg，对应 Hex） |
| `JLA` | float | 交换性铝（cmol/kg，对应 Alex） |

**可选输入：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `land_type` | string | `upland` | 土地利用类型（`upland` 旱地 / `paddy` 水田），非法值回退 `upland` 并发 warning |
| `fertilizer_type` | string | `compound` | 肥料类型（`compound` 复合肥 / `urea` 尿素），非法值回退 `compound` 并发 warning |
| `parcel_id` | string | - | 地块 ID；当 `SJD` 缺失时自动从 DB 查询 SJD（基于 `evaluation_results` 表） |
| `RPH` | float | 5.5 | 降水 pH 年均值（可配参数白名单） |
| `R` | float | 1893.0 | 年降水量 mm（可配参数白名单） |
| `Y` | float | 6700.0（旱地）/ 5109.0（水田） | 籽粒产量 kg/ha/yr（可配参数白名单） |
| `S` | float | 6968.0（旱地）/ 5109.0（水田） | 秸秆产量 kg/ha/yr（可配参数白名单） |
| `FertN` | float | 180.0 | 施肥量（以 N 计）kg/ha（可配参数白名单） |
| `Ndep` | float | 47.6 | N 沉降 kg/ha（可配参数白名单） |
| `pHtarget` | float | 6.0（旱地）/ 6.5（水田） | 目标 pH（可配参数白名单） |

> 可配参数白名单为 `{RPH, R, Y, S, FertN, Ndep, pHtarget}`，覆盖后的值记入响应 `customized_params`；元素含量等内置参数不允许 API 覆盖。

#### 响应字段（Schema 2.0 信封）

`question_type=2` 时，`data.models["model-4"]`（仅当 `include_model_results=true` 时返回）按 `chat_compact` 投影返回：

| 字段 | 类型 | 说明 |
|------|------|------|
| `model_id` | string | 固定为 `acidification-remediation` |
| `status` | string | `ok` / `rejected` / `unavailable` / `error`（见 [`models.status` 取值](#models-字段include_model_resultstrue-时)） |
| `subject` | object | `{type: parcel\|area\|unknown, id: str}` |
| `result` | object\|null | 成功时见下表；`rejected` / `unavailable` / `error` 时为 `null` |
| `meta` | object | `{data_source, simulated, model_version="process_v2_20260801"}` |
| `issues` | array | 失败时含一条 `{code, severity, message}` |

**`result` 字段（成功时）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `result.ytk` | float | 亿土康施用量（kg/ha） |
| `result.mbnt` | float | 木本泥炭施用量（kg/ha） |
| `result.sub_model` | string | 命中的子模型名称（如 `upland_compound`） |
| `result.customized_params` | object | API 覆盖的可配参数，空对象表示全用默认值 |
| `result.acidification_level` | string | 酸化程度 |
| `result.background_acid` | float | 背景酸 |
| `result.acid_deposition_input` | float | 酸沉降输入 |
| `result.crop_acid_output` | float | 作物酸输出 |
| `result.nitrogen_cycle_acid` | float | 氮循环酸 |
| `result.agricultural_acid` | float | 农业酸 |

> 顶层 `answer` / `recommendations` 由 LLM 总结生成，与 `models["model-4"].result` 并存。`provenance` 中 `model_id="acidification-remediation"`、`model_version="process_v2_20260801"`。

#### 响应示例（question_type=2 成功）

```json
{
    "schema_version": "2.0",
    "trace_id": "01H...ABC",
    "status": "ok",
    "data": {
        "message_id": 4,
        "answer": "基于过程模型（upland_compound）计算，建议亿土康（YTK）施用量约 6413.6 kg/ha，木本泥炭（MBNT）约 11814.1 kg/ha（土地利用类型：upland，肥料类型：compound）。",
        "sources": [],
        "recommendations": [
            "建议施用亿土康（YTK）约 6413.6 kg/ha 调节土壤酸度",
            "配合木本泥炭（MBNT）约 11814.1 kg/ha 提升有机质"
        ],
        "routing": {"question_type": 2, "status": "normal"},
        "interaction_state": "completed",
        "analysis_context": { "...见 analysis_context 结构..." : "..." },
        "provenance": {
            "trace_id": "01H...ABC",
            "model_id": "acidification-remediation",
            "model_version": "process_v2_20260801",
            "calculated_at": "2026-09-02T02:00:00+00:00",
            "scenario_result": false,
            "spatial_object": { "...同 analysis_context.object..." : "..." },
            "object_title": "分析对象：乐昌市-耕地1460",
            "key_inputs": {"parcel_id": "1460", "land_type": "upland", "fertilizer_type": "compound"}
        },
        "scenario_result": false,
        "spatial_object": { "...同 analysis_context.object..." : "..." },
        "object_title": "分析对象：乐昌市-耕地1460",
        "models": {
            "model-4": {
                "model_id": "acidification-remediation",
                "status": "ok",
                "subject": {"type": "parcel", "id": "1460"},
                "result": {
                    "ytk": 6413.6,
                    "mbnt": 11814.1,
                    "sub_model": "upland_compound",
                    "customized_params": {},
                    "acidification_level": "中度",
                    "background_acid": 1.2,
                    "acid_deposition_input": 0.5,
                    "crop_acid_output": 0.8,
                    "nitrogen_cycle_acid": 1.0,
                    "agricultural_acid": 2.3
                },
                "meta": {
                    "data_source": "database",
                    "simulated": false,
                    "model_version": "process_v2_20260801"
                },
                "issues": []
            }
        },
        "trace_id": "01H...ABC"
    }
}
```

#### rejected 响应示例（缺少必填输入）

`models["model-4"]` 投影如下，顶层信封仍为 Schema 2.0：

```json
{
    "models": {
        "model-4": {
            "model_id": "acidification-remediation",
            "status": "rejected",
            "subject": {"type": "parcel", "id": "1460"},
            "result": null,
            "meta": {
                "data_source": "database",
                "simulated": false,
                "model_version": "process_v2_20260801"
            },
            "issues": [
                {
                    "code": "CANNOT_GET_PH",
                    "severity": "error",
                    "message": "无法获取地块 pH 值"
                }
            ]
        }
    }
}
```

> `issues[].code` 取值（来自 `_status_and_issue` 的 reason 映射）：
> - `MISSING_INPUT` — SJD/JHX/JLA 任一缺失
> - `INPUT_OUT_OF_RANGE` — pHstart 不在 [3,10] 或 Hex/Alex < 0
> - `CANNOT_GET_PH` — parcel_id 查 DB 未取到 SJD
> - `MODEL_UNAVAILABLE` — acidification 模块不可用（优雅降级）

---

### 聊天分析对象与情景试算

专业问题不再相信客户端传入的名称或区域属性，只接受对象引用并由后端权威目录解析。
会话保存当前对象和递增版本；历史消息保存创建时的不可变快照。

设置对象（首次会话版本为 `0`）：

```bash
curl -X POST http://localhost:5000/api/v1/chat/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"分析这块地的质量等级","conversation_id":1,"analysis_context":{"action":"set","expected_version":0,"object":{"type":"parcel","id":"P001"}}}'
```

后续请求使用 `{"analysis_context":{"action":"inherit"}}` 继承；清除时使用
`{"analysis_context":{"action":"clear","expected_version":1}}`。`expected_version`
不匹配返回 `409 analysis_context_conflict`，且不会保存消息。

Model-4 无空间对象情景试算：

```json
{
  "message": "试算酸化改良",
  "calculation_mode": "scenario",
  "SJD": 5.2,
  "JHX": 0.8,
  "JLA": 1.1,
  "land_type": "upland",
  "fertilizer_type": "urea"
}
```

缺少对象或情景参数是可恢复交互，返回 HTTP 200，`interaction_state` 分别为
`needs_analysis_object` 或 `needs_scenario_inputs`；服务会保存用户消息和确定性助手提示，
但不执行专业模型。SSE 仅发送 `meta`、`done`，不发送 `token`。

完成响应中的 `analysis_context`、`provenance`、`scenario_result`、`spatial_object`
和 `object_title` 为后端结构化字段。`provenance` 包含同一次执行的 `trace_id`、模型和
数据版本、计算时间及实际关键输入。

错误响应统一为：

```json
{"status":"error","error":{"code":"analysis_object_invalid","message":"地块不存在","details":{}}}
```

| HTTP | code | 含义与持久化 |
|---|---|---|
| 422 | `analysis_object_invalid` / `legacy_identifier_ambiguity` | 对象非法；不保存消息 |
| 409 | `analysis_context_conflict` | 版本冲突；不保存消息 |
| 503 | `analysis_object_validation_unavailable` | 权威验证不可用；旧对象保持不变，不保存消息 |

旧 `parcel_id`、`parcel_code`、`area_code` 仅用于迁移兼容并已弃用。双地块 ID 只有在
`parcel_info` 权威映射中指向同一对象时才会接受；无法映射时拒绝，绝不猜测或补默认对象。

## 模型接口

### 获取可用模型列表

**GET** `/api/v1/models/`

成功响应（200）：
```json
{
    "status": "ok",
    "data": [
        {"name": "stability-risk-evaluation", "description": "基于3期历史数据，通过九模块综合评价耕地质量稳定性和退化风险（model-1）。"},
        {"name": "quality-grade-evaluation", "description": "耕地质量等级评价，输出综合指数、等级和障碍度（model-2）。"},
        {"name": "obstacle-diagnosis", "description": "主要问题与障碍诊断（model-3）。"},
        {"name": "acidification-remediation", "description": "基于过程模型（4 子模型：水田/旱地 × 尿素/复合肥）计算酸化改良剂需求，输出亿土康（YTK）与木本泥炭（MBNT）施用量（model-4）。"},
        {"name": "organic-matter-improvement", "description": "有机质培肥 ML：韶关旱地/水田 RF + 全局 ETR，返回 SOC、Dose、版本和降级状态（model-5）。"},
        {"name": "placeholder", "description": "占位能力，暂不加载肥力 RF（model-6）。"}
    ]
}
```

> 注：默认列表仅返回 6 个正式专业模型，均与一个专业智能体一一对应。传入 `include_non_professional=true` 可查看辅助空间能力、辅助指标能力和实验性协同提升能力；它们不参与聊天路由。

> `obstacle-factor-identification` 与 `acidification-governance` 为旧模型标识，仍可调用但响应会返回规范模型 ID 和弃用提示。`spatial-structure-analysis`、`soil-indicator-analysis` 为辅助能力，`multi-factor-collaborative-improvement` 为实验性能力。

### 有机质培肥 ML（model-5）

**POST** `/api/v1/models/run`

请求 `model_id` 使用公开标识 `organic-matter-improvement`。韶关区域按 `land_type` 选择旱地/水田 RF；规范字段也可以替换为外部模型字段 `SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX`。真实预测要求模型所需输入完整，SOC 模型使用的 `Dose` 也必须由调用方提供，服务端不再使用训练均值补齐缺失特征。

```json
{
    "model_id": "organic-matter-improvement",
    "area_code": "lechang",
    "land_type": "upland",
    "pH": 6.2,
    "SOCbe": 22.0,
    "TN": 1.1,
    "TP": 0.8,
    "TK": 18.0,
    "AP": 25.0,
    "AK": 80.0,
    "Gap": 5.0,
    "Dose": 300.0,
    "Fertilizer type": 1
}
```

成功响应包含 `soc_prediction`、`dose_prediction`、`dose_confidence`、真实 `model_version` 和 `simulated=false`。缺少特征、模型文件、运行依赖或预测异常时，响应为 `degraded` 或 `unavailable`，`issues` 包含 `MODEL5_QUANTITATIVE_UNAVAILABLE`；`soc_prediction`、`dose_prediction`、`dose`、`manure_dosage` 和 `potential_increase` 均为 `null`。客户端不得使用历史等级表或本地默认数字回填。`potential_increase` 在建立并验证独立预测模型前始终不可用。

报告只展示能够关联到执行日志、`simulated=false`、真实 RF/ETR 来源且模型版本完整的施用量。模拟、规则降级、来源不明或孤立历史记录均显示“暂无可靠估计”；旧 `potential_increase` 不再作为有效预期提升展示。

---

## 文档管理接口

### 获取文档列表

**GET** `/api/v1/docs/`

成功响应（200）：
```json
{
    "status": "ok",
    "data": [
        {
            "id": 1,
            "doc_name": "土壤治理指南.pdf",
            "file_path": "uploads/20260713_abc.pdf",
            "file_type": "pdf",
            "file_size": 102400,
            "chunk_count": 5,
            "status": 1,
            "category": "report",
            "create_by": 1,
            "create_time": "2026-07-13 10:00:00",
            "update_time": "2026-07-13 10:00:00"
        }
    ]
}
```

---

### 上传文档

**POST** `/api/v1/docs/upload`

> Content-Type: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | 是 | 文档文件（支持 .txt, .md, .pdf, .docx, .xlsx） |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "id": 2,
        "doc_name": "test.pdf",
        "file_path": "uploads/20260713_xyz.pdf",
        "file_type": "pdf",
        "file_size": 51200,
        "chunk_count": 3,
        "status": 1,
        "category": "report",
        "create_by": 1
    },
    "message": "文档上传成功"
}
```

---

### 获取文档详情

**GET** `/api/v1/docs/{id}`

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 文档 ID |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "id": 1,
        "doc_name": "土壤治理指南.pdf",
        "file_type": "pdf",
        "file_size": 102400,
        "chunk_count": 5,
        "status": 1
    }
}
```

---

### 删除文档

**DELETE** `/api/v1/docs/{id}`

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 文档 ID |

成功响应（200）：
```json
{
    "status": "ok",
    "message": "文档删除成功"
}
```

---

## 县域诊断接口

### 获取概览

**GET** `/api/v1/county/overview?area_code=lechang`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `area_code` | string | 否 | 区域代码（默认 "lechang"） |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "area": "lechang",
        "assessment": {
            "level": "中度",
            "ph": 5.2,
            "acidification_rate": 0.05
        }
    }
}
```

---

### 诊断分析

**POST** `/api/v1/county/diagnose`

请求体：
```json
{
    "topic": "acidification",
    "area_code": "lechang",
    "longitude": 113.35,
    "latitude": 25.13
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `area_code` | string | 否 | 区域代码（默认 "lechang"） |
| `topic` | string | 是 | `acidification`、`quality` 或 `improvement` |
| `longitude` | float | 否 | 经度；缺失时仅返回县域级定性建议 |
| `latitude` | float | 否 | 纬度；缺失时仅返回县域级定性建议 |

模板建议响应（HTTP 200）：
```json
{
    "status": "degraded",
    "data": {
        "status": "degraded",
        "result_kind": "advisory_only",
        "topic": {"id": "acidification", "name": "酸化诊断"},
        "problems": [{
            "name": "土壤酸化风险待核验",
            "percent": null,
            "advisory_only": true,
            "basis": "template_guidance",
            "metric_meta": {
                "percent": {
                    "status": "unavailable",
                    "reason": "validated_statistics_unavailable",
                    "unit": "%",
                    "source": null,
                    "method": null,
                    "model_version": null,
                    "calculated_at": null,
                    "scope": {"type": "county", "id": "lechang"}
                }
            }
        }],
        "measures": [{
            "name": "土壤酸化改良措施",
            "cost": null,
            "improve": null,
            "period": null,
            "advisory_only": true,
            "basis": "template_guidance"
        }],
        "regions": [],
        "base_data": [],
        "reliability": {
            "level": "insufficient_evidence",
            "predictive": false,
            "quantitative_available": false
        },
        "quantitative_estimates": {
            "status": "unavailable",
            "reason": "validated_quantitative_results_unavailable"
        }
    }
}
```

未来返回非空定量值时，对应 `metric_meta` 至少必须包含 `source`、`method`、`calculated_at`、`scope`，适用时还要包含 `model_version`；缺少这些依据的数值会被响应契约拒绝。非法主题仍返回 `status=error` 和 `error.code=INVALID_TOPIC`。

#### 旧客户端迁移

- 将 `degraded` 视为 HTTP 请求成功但证据不足的安全降级结果，不要改写为 `ok`。
- `period`、`improve`、`effect`、`cost` 和问题 `percent` 均可能为 `null`，界面应显示“暂无可靠估计”。
- 不要用本地默认数字、固定周期或历史占位值替换 `null`。
- `regions` 和 `base_data` 可能为空数组，表示当前没有可靠的重点区域统计或排序。

### 诊断摘要

**POST** `/api/v1/report/summary`

请求体直接传入县域诊断内部结果，即 `/api/v1/county/diagnose` 响应的 `data`。`status=ok` 和 `status=degraded` 均可接受；摘要会原样传播 `status`、`result_kind`、`reliability` 和 `quantitative_estimates`，不会根据空字段补造数值。

---

## 耕地空间统计接口

接口统一前缀为 `/api/v1/farmland-statistics`，均需携带 JWT。完整字段定义、示例和错误响应已导出到 [`openapi.json`](openapi.json)，可直接导入 Apifox、Swagger UI 等工具；统计口径和前端联动建议见 [`farmland-statistics-api.md`](farmland-statistics-api.md)。

### 获取指标配置

**GET** `/api/v1/farmland-statistics/metrics`

返回指标分组、排序、值类型、可用性、数据年份、覆盖率、规范/兼容来源字段、单位、精度、分级区间、颜色和 `classificationVersion=2026-09-21.1`。前端应以此响应生成图例并在版本变化时刷新缓存。

指标 key：

| key | 指标 | 单位 | 分级区间 |
|-----|------|------|----------|
| `quality_grade` | 耕地质量等级 | 等 | 1–10 等，各等级单独分档 |
| `soil_ph` | 土壤 pH | pH | 极强酸性 `<4.5`；强酸性 `[4.5,5.5)`；酸性 `[5.5,6.5)`；中性 `[6.5,7.5]`；碱性 `>7.5` |
| `organic_matter` | 有机质含量 | g/kg | 低 `(0,10]`；中低 `(10,20]`；中高 `(20,25]`；高 `(25,+∞)` |
| `available_phosphorus` | 有效磷含量 | mg/kg | 低 `(0,10]`；中低 `(10,20]`；中高 `(20,35]`；高 `(35,+∞)` |
| `available_potassium` | 速效钾含量 | mg/kg | 低 `(0,50]`；中低 `(50,100]`；中高 `(100,150]`；高 `(150,+∞)` |
| `bulk_density` | 土壤容重 | g/cm³ | 极低 `(0,0.9)`；低 `[0.9,0.95)`；偏低 `[0.95,1)`；正常 `[1,1.2]`；偏高 `(1.2,1.3]`；高 `(1.3,1.4]`；极高 `(1.4,+∞)` |
| `plow_layer_thickness` | 耕层厚度 | cm | 极低 `(0,10]`；低 `(10,15]`；中 `(15,20)`；高 `[20,+∞)` |
| `effective_soil_depth` | 有效土层厚度 | cm | 极低 `(0,60)`；低 `[60,80)`；中 `[80,100)`；高 `[100,+∞)` |

### 获取可选年份

**GET** `/api/v1/farmland-statistics/years`

返回调查年份、各年度地块数量和 `defaultYear`。不传 `year` 时，统计、详情和点选默认使用最新可选年份。

### 查询行政区域

**GET** `/api/v1/farmland-statistics/regions`

| 查询参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| `parent_type` | string | 否 | 父级类型，必须与 `parent_id` 同时提供 |
| `parent_id` | string | 否 | 父级对象 ID，必须与 `parent_type` 同时提供 |
| `include_disputes` | boolean | 否 | 是否包含不可选择的村间争议区，默认 `false` |

```text
# 查询乐昌市下的镇
GET /api/v1/farmland-statistics/regions?parent_type=county&parent_id=440281

# 查询某镇下的村
GET /api/v1/farmland-statistics/regions?parent_type=township&parent_id=440281001
```

区域对象会返回 `regionType`、`regionId`、`displayName`、`areaCode`、父级信息、`selectable` 和 `hasGeometry`。当前区域代码来自区域目录和空间审计，不再固定为新丰县 `440233`。

### 获取行政边界 GeoJSON

**GET** `/api/v1/farmland-statistics/boundaries`

```text
GET /api/v1/farmland-statistics/boundaries?region_type=township&parent_type=county&parent_id=440281&zoom=10
```

可按 `region_type`、父级、`bbox=minLon,minLat,maxLon,maxLat` 和 `zoom` 查询。响应为 GeoJSON `FeatureCollection`，包含名称、代码、父级、是否可选和层级最小缩放级别。省/市/县/镇/村的 `minZoom` 分别为 3/5/7/9/12；低于该级别时返回空要素集。

### 聚合统计

**POST** `/api/v1/farmland-statistics/aggregate`

按村等行政区域统计：

```json
{
  "scope": {
    "type": "administrative_region",
    "region_type": "village",
    "region_id": "440281001208"
  },
  "year": 2024,
  "metrics": "all"
}
```

按当前地图视窗统计：

```json
{
  "scope": {
    "type": "viewport",
    "bbox": [113.0, 24.0, 114.0, 25.0]
  },
  "metrics": ["soil_ph", "organic_matter", "available_phosphorus"]
}
```

多个同级行政区联合统计：

```json
{
  "scope": {
    "type": "administrative_regions",
    "region_type": "county",
    "region_ids": ["440281", "440282"]
  },
  "metrics": "all"
}
```

自定义圈选区域统计：

```json
{
  "scope": {
    "type": "polygon",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[113.0, 24.0], [113.1, 24.0], [113.1, 24.1], [113.0, 24.0]]]
    }
  },
  "metrics": ["organic_matter"]
}
```

多区域一次最多 100 个且不允许混级；后端先合并并消除重叠。圈选范围仅支持 WGS84 Polygon/MultiPolygon，最多 5000 个顶点、面积最多 200000 平方公里。

`bbox` 坐标系为 WGS84，顺序是 `[minLon, minLat, maxLon, maxLat]`。地图缩放或平移后，前端可用新 bbox 再次请求；建议做 300–500 ms 防抖并取消过期请求。

成功响应（200，节选）：

```json
{
  "status": "ok",
  "data": {
    "classificationVersion": "2026-09-21.1",
    "dataYear": 2024,
    "dataAsOf": "2026-09-11T10:20:30",
    "scopeSummary": {"parcelCount": 2, "totalAreaMu": 18.5},
    "metrics": [{
      "key": "organic_matter",
      "metricKey": "organic_matter",
      "label": "有机质含量",
      "unit": "g/kg",
      "table": {
        "average": 26.42,
        "totalAreaMu": 18.5,
        "parcelCount": 2,
        "validAreaMu": 18.5,
        "validParcelCount": 2,
        "range": {"min": 18.2, "max": 42.0}
      },
      "distribution": [{
        "key": "high",
        "label": "高",
        "rangeLabel": "(25,+∞)",
        "color": "#1A9850",
        "lower": 25,
        "upper": null,
        "lowerInclusive": false,
        "upperInclusive": false,
        "parcelCount": 1,
        "areaMu": 9.5,
        "countPercent": 50.0,
        "areaPercent": 51.3514
      }],
      "unclassified": {"parcelCount": 0, "areaMu": 0.0}
    }],
    "scope": {
      "scopeVersion": 1,
      "type": "administrative_region",
      "regionType": "village",
      "regionId": "440281001208",
      "displayName": "示例村"
    }
  }
}
```

`table.average` 是按裁剪后地块面积加权的平均值；总面积和分档面积单位均为亩。`distribution` 按等级顺序返回，可供柱状图和饼图共用；`unclassified` 单独承载缺值、非法值和未落入有效区间的数据。

### 按经纬度点选地块

**POST** `/api/v1/farmland-statistics/parcels/pick`

点选规则：重叠时取面积最小地块，未命中返回 404；精确覆盖优先，否则在容差内返回最近地块。

请求体（JSON）：

```json
{
  "longitude": 113.35,
  "latitude": 25.13,
  "metric": "soil_ph",
  "toleranceMeters": 8,
  "year": 2024
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `longitude` | number | 是 | 经度，范围 -180 ~ 180 |
| `latitude` | number | 是 | 纬度，范围 -90 ~ 90 |
| `metric` / `metric_key` | string | 否 | 指定主指标（如 `soil_ph`）；省略时返回完整指标响应 |
| `toleranceMeters` / `tolerance_meters` | number | 否 | 容差（米），默认 0、最大 50 |
| `year` | number | 否 | 数据年份，缺省用默认年份 |

成功响应（200）：

```json
{
  "status": "ok",
  "data": {
    "classificationVersion": "2026-09-21.1",
    "parcelId": "3060",
    "areaCode": "440224",
    "areaMu": 2168.29,
    "dataYear": 2024,
    "metrics": {
      "soil_ph": {
        "metricKey": "soil_ph",
        "label": "土壤 pH",
        "value": 5.51,
        "unit": "pH",
        "bucketKey": "acid",
        "bucketLabel": "酸性",
        "color": "#FDDBC7",
        "rangeLabel": "[5.5,6.5)"
      }
    },
    "soilPh": 5.51,
    "organicMatter": 37.17,
    "qualityGrade": 7.0,
    "hit": {
      "mode": "exact",
      "distanceMeters": 0.0,
      "toleranceMeters": 0.0
    }
  }
}
```

`data` 字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `parcelId` | string | 地块编号（位于 `data` 顶层，不在 `metrics` 内） |
| `areaCode` | string/null | 行政区划代码 |
| `areaMu` | number/null | 完整地块面积（亩），几何缺失为 null |
| `dataYear` | int/null | 数据年份 |
| `metrics` | object | 全量指标 `key → {metricKey,label,value,unit,dataSource,measurementYear,isImputed,imputationMethod,qualityFlag,...}` |
| `soilPh` / `organicMatter` / `qualityGrade` / `availablePhosphorus` 等 | any | 常用指标的兼容快捷字段 |
| `hit` | object | 命中方式：`mode=exact`（点在面内）或 `nearest`（容差最近），含距离与容差 |

传 `metric` 时只返回当前指标的值、等级、颜色及来源信息；省略时返回完整指标响应。每项指标均返回 `dataSource`、`measurementYear`、`isImputed`、`imputationMethod` 和 `qualityFlag`。接口有 5 秒短时缓存及每用户 120 次/分钟保护。

失败响应：

```json
{
  "status": "error",
  "code": "parcel_not_found",
  "message": "该位置未命中地块"
}
```

| HTTP 状态码 | code | 场景 |
|------------|------|------|
| 400 | `invalid_coordinate` | 经纬度非数字或越界 |
| 400 | `invalid_tolerance` | tolerance 非数字或超过上限 |
| 404 | `parcel_not_found` | 位置未命中地块 |
| 404 | `parcel_year_not_found` | 指定年份下该地块无数据 |
| 429 | `rate_limited` | 超出限流（响应头带 `Retry-After: 1`） |
| 503 | `statistics_unavailable` | 点选服务不可用（数据库异常） |

### 获取视口轻量地块要素

**GET** `/api/v1/farmland-statistics/parcels/viewport`

```text
GET /api/v1/farmland-statistics/parcels/viewport?bbox=113,24,114,25&metric=soil_ph&geometry=centroid&limit=2000
```

返回 GeoJSON `FeatureCollection`，每个要素只包含地块 ID、当前指标的值/等级/颜色/来源，以及质心、简化几何或空几何。`limit` 默认 2000、最大 5000；超过时 `truncated=true`。该接口用于地图批量渲染和前端本地悬浮拾取，每用户限制为 60 次/分钟。

### 获取指标质量审计

**GET** `/api/v1/farmland-statistics/quality/audit`

返回全部指标的非空率、可解析数、范围、唯一值数、异常/未分类数量和来源分布。结果缓存 5 分钟。

### 获取地块详情

**GET** `/api/v1/farmland-statistics/parcels/{parcel_id}?year=2021`

返回字段与点选接口相同，供已知地块 ID 时直接加载详情。

### 按统一范围查询地块

**POST** `/api/v1/farmland-statistics/parcels/query`

复用聚合接口的 `scope` 和 `year`，支持按行政区域、多区域、自定义多边形、视窗或单地块查询，并回传规范化 `scope`、指标和分页状态。

### 统计接口错误码

错误响应统一为：

```json
{
  "status": "error",
  "code": "invalid_scope",
  "message": "请求必须包含 scope 对象"
}
```

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求体、指标、父级、统计范围或经纬度无效 |
| 401 | 未携带或无法验证 JWT |
| 404 | 区域/地块不存在，或点选位置未命中地块 |
| 409 | 区域存在但尚未导入边界 |
| 413 | 行政区数量、圈选顶点数或圈选面积超过限制 |
| 429 | 点选或视口地块请求超过当前用户频率限制 |
| 500 | 统计服务内部错误 |
| 503 | 区域目录、空间统计或地块点选服务暂时不可用 |

---

## 数据导入接口

### 上传部署专题模型数据

**POST** `/api/v1/data/import`

> 需要管理员权限（admin）
> Content-Type: `multipart/form-data`
> 文件大小限制：200MB

用于上传部署三类专题模型数据（CSV / shapefile / 耕地质量评价 CSV），部署前自动备份现有文件，部署后自动触发对应的处理流程。

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `data_type` | string | 是 | 数据类型：`csv` / `shapefile` / `dat` |
| `file` | file | 是 | 上传的文件 |

#### 数据类型说明

**CSV（data_type=csv）**
- 部署到 `data/farmland_diagnosis/test.csv`（固定文件名）
- 必需 14 列：`一级农业区`、`二级农业区`、`pH`、`有机质`、`有效磷`、`速效钾`、`容重`、`耕层质地`、`灌溉能力`、`排水能力`、`地形部位`、`质地构型`、`有效土层`、`耕层厚度`
- 编码：UTF-8（失败回退 GBK）
- 触发：`bulk_evaluate` 批量评价

**shapefile（data_type=shapefile）**
- 部署到 `data/farmland_stability/`（解压后扁平化）
- 上传格式：zip 包，含 `manifest.json` + 每期 shapefile 5 组件（.shp/.cpg/.dbf/.prj/.shx）
- zip 限制：文件数 ≤ 30、解压后总大小 ≤ 200MB、无路径穿越
- 触发：`precompute.main` 预计算 + 持久化

**耕地质量评价 CSV（data_type=dat）**
- 部署到 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（固定文件名）
- 校验：非空、≤ 200MB、UTF-8 编码、含 20 个必需字段（SiteID/JD/WD/MJ/SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD/JHXLLZ/JHXQLZ/EJNYQcode/XQMCcode/GCZDcode/PSNLcode/GGNLcode/DXBWcode/ZDGXcode）
- 触发：`FarmlandGradeRunner.check_deployment` 部署校验

#### manifest.json 格式（shapefile 必需）

```json
{
    "current_year": 2024,
    "history_years": [2020, 2021],
    "years": [2020, 2021, 2024],
    "current_filename": "current.shp",
    "history_filenames": ["2020.shp", "2021.shp"]
}
```

#### 成功响应（200）

```json
{
    "status": "ok",
    "data": {
        "data_type": "csv",
        "deployed_path": "data/farmland_diagnosis/test.csv",
        "backup_path": "data/farmland_diagnosis/backup/20260725-110000",
        "trigger_result": {"status": "ok", "processed": 100, "errors": []}
    }
}
```

#### 错误码

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 缺少 data_type/file、data_type 不合法、校验失败（缺列/shapefile 组件不全/CSV 为空或编码/字段不符等） |
| 401 | 未携带 JWT |
| 403 | 非 admin 用户 |
| 413 | 文件大小超过 200MB |
| 500 | 触发器异常或返回错误字典（已自动回滚） |
| 504 | 触发器超时（600s，已自动回滚） |

#### curl 示例

```bash
# 登录获取 token（需 admin 账号）
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 上传 CSV
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=csv" \
  -F "file=@/path/to/test.csv"

# 上传 shapefile zip 包
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=shapefile" \
  -F "file=@/path/to/stability_data.zip"

# 上传耕地质量评价 CSV
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=dat" \
  -F "file=@/path/to/Farmland_quality_Level_Database.csv"
```

> 备份策略：部署前备份现有文件到 `backup/YYYYMMDD-HHMMSS/`，保留最近 3 份；触发失败自动回滚到备份。
> 审计日志：`logs/data_import.log`（JSON 行格式）。

---

## 错误码

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求参数错误 |
| 401 | 未认证或认证失败 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 413 | 请求体过大（如数据导入文件超过 200MB） |
| 500 | 服务器内部错误 |
| 504 | 网关超时（如数据导入触发器超过 600s） |

---

## 请求示例

### 使用 curl

```bash
# 登录
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'

# 发送消息（替换 <token>）
curl -X POST http://localhost:5000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"message":"如何治理强酸性耕地？","context":{"target_ph":6.0}}'

# 上传文档
curl -X POST http://localhost:5000/api/v1/docs/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/document.pdf"
```
# 专题模型输出契约

专题模型和聊天接口的 Schema 2.0 结构、兼容请求及旧字段映射见
[`thematic-model-output-contract.md`](thematic-model-output-contract.md)。
