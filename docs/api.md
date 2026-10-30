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
| `file` | file | 是 | 文档文件（支持 .txt, .md, .pdf, .caj, .docx, .xlsx, .xls, .csv, .dat） |
| `domain_labels` | string/string[] | 是 | 至少一个一级领域标签；不提供自动分类 |
| `document_kind` | string | 否 | `academic_paper`、`standard`、`policy`、`method_guideline` 或 `other` |
| `title` | string | 否 | 文献标题 |
| `authors` | JSON string[] | 否 | 作者数组 |
| `doi` | string | 否 | DOI，服务端会规范化 |
| `journal` | string | 否 | 期刊名称 |
| `publication_date` | date | 否 | ISO 8601 日期 |
| `standard_number` | string | 否 | 标准号 |
| `issuing_authority` | string | 否 | 发布机构 |
| `source_url` | string | 否 | 来源 URL，仅保存、不自动请求 |
| `source_category` | string | 否 | 来源目录分类，不替代领域标签 |
| `cross_categories` | JSON string[] | 否 | 来源交叉分类 |
| `language` | string | 否 | 文献语言 |
| `idempotency_key` | string | 否 | 用户范围幂等键，最长 128 字符 |

文献不支持私有发布。省略 `visibility_scope` 或提交 `public` 均表示：审核期仅上传者和管理员可见，管理员批准且索引完成后进入公共知识库。显式提交 `private` 返回 `visibility_not_configurable`。

成功接收（202）：
```json
{
    "status": "ok",
    "data": {
        "document": {
            "id": 2,
            "doc_name": "test.pdf",
            "status": 0,
            "review_status": "pending",
            "processing_stage": "awaiting_admin_review",
            "visibility_scope": "private"
        },
        "ingestion": {
            "state": "pending",
            "stage": "awaiting_admin_review",
            "progress": 0,
            "review_status": "pending",
            "status_url": "/api/v1/docs/2/ingestion"
        },
        "knowledge_graph": {
            "state": "not_eligible",
            "latest_job_id": null,
            "schema_version": null,
            "backend_name": null,
            "extractor_version": null,
            "retryable": false,
            "failure_code": null
        }
    },
    "message": "文献上传成功，等待管理员审核"
}
```

常见错误：`unsupported_file_type`（415）、`content_type_mismatch`（422）、`encrypted_document`（422）、`invalid_metadata`（422）、`domain_label_required`（422）、`visibility_not_configurable`（422）、`duplicate_document`（409）、`idempotency_conflict`（409）、`processor_unavailable`（503）。

---

### 查询文献入库状态

**GET** `/api/v1/docs/{id}/ingestion`

仅上传者或管理员可查询。响应包含 `state`、`stage`、`progress`、`review_status`、`attempt`、质量摘要、失败码和 `retryable`。独立的 `knowledge_graph` 子状态只返回任务状态、稳定失败码和组件版本，不返回模型原始输出、候选内容、堆栈或内部路径。

### 重试失败入库

**POST** `/api/v1/docs/{id}/retry`

仅上传者或管理员可以重试已审核通过、`status=3` 且 `retryable=true` 的文档。成功返回 202；已完成、被驳回或不可重试时返回 409。

### 管理员文献审核

- **GET** `/api/v1/docs/reviews?state=pending`：分页查看待审核文献。
- **POST** `/api/v1/docs/{id}/review`：批准或驳回。

批准示例：

```json
{
    "decision": "approve",
    "domain_labels": ["cultivated_land_quality"],
    "review_note": "标签与正文一致",
    "idempotency_key": "review-2-v1"
}
```

驳回时 `review_note` 必填。审核通过后才启动转换、解析、OCR、分块和索引；成功完成时文档与全部 chunk 的 `visibility_scope` 为 `public`。
审核标准、政策或方法指南时可提交 `authority_status`。设为 `verified_current` 时必须同时提交 `authority_verification_source`，系统会保存核验人、核验时间和来源；未核验资料默认 `unverified`。

### 管理员文献批次

- **POST** `/api/v1/docs/batches`：dry-run 或正式创建批次。
- **GET** `/api/v1/docs/batches/{batch_id}`：查询逐项进度和计数。
- **POST** `/api/v1/docs/batches/{batch_id}/retry`：重试可恢复失败项。
- **POST** `/api/v1/docs/batches/{batch_id}/cancel`：取消尚未开始的项目。

dry-run 请求示例：

```json
{
    "staging_token": "initial",
    "manifest_path": "manifest.jsonl",
    "dry_run": true
}
```

正式执行还必须提供 `batch_key`。`staging_token` 必须预先配置于 `LITERATURE_STAGING_ROOTS_JSON`，API 不接受任意宿主机绝对路径。dry-run 不写数据库、向量库或永久派生文件。
JSONL manifest 的每一项必须声明 `"schema_version":"1.0"`。

---

### 知识图谱任务与审核

接口前缀为 `/api/v1/knowledge-graph`。任务管理只允许管理员；候选、证据和审核允许管理员与 `domain_reviewer`。所有审核请求必须提供非空 `reason` 和唯一 `idempotency_key`。

- **GET** `/jobs`：按 `state`、`backend_name`、`extractor_version`、`document_id` 分页筛选任务。
- **GET** `/jobs/{job_id}`：查询任务详情和候选计数；不返回内部失败文本。
- **POST** `/jobs/{job_id}/retry`：手动重试 `retry` 或 `dead_letter` 任务。
- **POST** `/documents/{document_id}/rerun`：按文档和指定 adapter/schema 重新排队；相同版本复用原任务身份。
- **GET** `/candidates`：按 `kind`、`review_status`、`risk_level`、`relation_type`、`document_id` 筛选。
- **GET** `/candidates/{kind}/{candidate_id}`：查询候选、证据定位和审核历史。
- **GET** `/evidence/{kind}/{evidence_id}`：查询 quote、页码、chunk 和 span 定位。
- **POST** `/entities/{entity_id}/resolve`：提交规范实体 ID 和名称，完成消歧或新实体确认。
- **POST** `/candidates/{kind}/{candidate_id}/review`：批准或拒绝实体、关系或 claim。
- **POST** `/evidence/{kind}/{evidence_id}/review`：批准或拒绝关系/claim 证据。
- **GET** `/releases/preview`：管理员预览追加式差异、变更校验和与全部发布门禁。
- **POST** `/releases`：管理员发布已验证变更并原子切换活动 release；请求体提供 `release_id`。
- **GET** `/releases`：管理员查看发布历史、父版本、差异摘要和验证报告。
- **POST** `/releases/{release_id}/rollback`：管理员回滚到兼容且验证通过的历史 release；请求体必须提供 `reason` 和 `idempotency_key`。
- **POST** `/query`：认证用户执行受限图查询；支持 `relation_types`、`direction`、`max_hops`（1–2）、`top_k`（1–100）、`timeout_ms` 和 `max_result_bytes`。证据正文始终回到向量库并按公开/所有者权限过滤。

关系或 claim 只有在结构校验通过、端点实体均已批准、所有有效证据均已批准后才能批准。审核记录为追加式不可变审计。`POST /production-relations` 始终返回 405；生产边只能通过已批准候选的 release 流程生成。

发布门禁覆盖 schema 兼容、端点、方向、有效证据、重复、孤点、审核覆盖、代表性查询和变更校验和。发布成功后仅排队 JSON/Parquet 审计导出，不阻塞活动版本切换；运维 worker 使用 `python scripts/export_knowledge_graph_releases.py --limit 10` 处理待导出记录。图查询超时或图存储异常时返回脱敏的 `degraded` 状态，调用方应继续使用向量检索结果。

已进入图谱证据链的文献删除会转为可审计撤回：对应文档哈希的关系/claim 证据失效，关系支持文档数重算；仍有其他支持文献时保留关系，最后一条证据失效时只创建待审核移除候选，不直接改变活动 release。重新解析会自动失效同一文档的旧内容哈希证据。历史文献回填可先执行 `python scripts/archive/backfill_knowledge_graph.py --dry-run --batch-size 100`，正式运行使用固定 `--run-key`；命令按文档 ID 保存 checkpoint，可重复调用续跑且复用已有幂等 outbox。

实体消歧请求示例：

```json
{
    "canonical_id": "measure:straw-returning",
    "canonical_name": "秸秆还田",
    "reason": "确认是新的治理措施实体",
    "idempotency_key": "resolve-entity-102-v1"
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

返回 8 项指标的名称、来源字段、单位、精度、分级区间和颜色。前端应以此响应生成图例，避免重复硬编码。所有最高档均不封顶，例如有机质大于 40 仍属于“高”档并使用统一颜色。

指标 key：

| key | 指标 | 单位 | 分级区间 |
|-----|------|------|----------|
| `quality_grade` | 耕地质量等级 | 等 | 1–10 等，各等级单独分档 |
| `soil_ph` | 酸化 pH 情况 | pH | 极强酸性 `<4.5`；强酸性 `[4.5,5.5)`；酸性 `[5.5,6.5)`；中性 `[6.5,7.5]`；碱性 `>7.5` |
| `organic_matter` | 有机质含量 | g/kg | 低 `(0,10]`；中低 `(10,20]`；中高 `(20,25]`；高 `(25,+∞)` |
| `available_phosphorus` | 有效磷含量 | mg/kg | 低 `(0,10]`；中低 `(10,20]`；中高 `(20,35]`；高 `(35,+∞)` |
| `available_potassium` | 速效钾含量 | mg/kg | 低 `(0,50]`；中低 `(50,100]`；中高 `(100,150]`；高 `(150,+∞)` |
| `bulk_density` | 土壤容重 | g/cm³ | 极低 `(0,0.9)`；低 `[0.9,0.95)`；偏低 `[0.95,1)`；正常 `[1,1.2]`；偏高 `(1.2,1.3]`；高 `(1.3,1.4]`；极高 `(1.4,+∞)` |
| `plow_layer_thickness` | 耕层厚度 | cm | 极低 `(0,10]`；低 `(10,15]`；中 `(15,20)`；高 `[20,+∞)` |
| `effective_soil_depth` | 有效土层厚度 | cm | 极低 `(0,60)`；低 `[60,80)`；中 `[80,100)`；高 `[100,+∞)` |

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

`bbox` 坐标系为 WGS84，顺序是 `[minLon, minLat, maxLon, maxLat]`。地图缩放或平移后，前端可用新 bbox 再次请求；建议做 300–500 ms 防抖并取消过期请求。

成功响应（200，节选）：

```json
{
  "status": "ok",
  "data": {
    "dataAsOf": "2026-09-11T10:20:30",
    "scopeSummary": {"parcelCount": 2, "totalAreaMu": 18.5},
    "metrics": [{
      "key": "organic_matter",
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

```json
{
  "longitude": 113.35,
  "latitude": 25.13
}
```

返回命中地块的 `parcelId`、`areaCode`、`areaMu`、`qualityGrade`、`organicMatter`、`soilPh` 和 `availablePhosphorus`。`areaMu` 是完整地块测地面积换算的亩数，保留 4 位小数，不按当前视窗裁剪；几何缺失时为 `null`。未命中返回 404；多个地块重叠时优先返回面积较小的地块。

### 获取地块详情

**GET** `/api/v1/farmland-statistics/parcels/{parcel_id}`

返回字段与点选接口相同，供已知地块 ID 时直接加载详情。

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
  -F "file=@/path/to/document.pdf" \
  -F "document_kind=academic_paper" \
  -F "domain_labels=cultivated_land_quality" \
  -F "idempotency_key=paper-upload-001"
```
# 专题模型输出契约

专题模型和聊天接口的 Schema 2.0 结构、兼容请求及旧字段映射见
[`thematic-model-output-contract.md`](thematic-model-output-contract.md)。
# 文献证据检索与异步对照（M1，显式配置）

新增蓝图前缀`/api/v1/literature-evidence`，所有接口要求有效JWT及活动身份。配置`LITERATURE_EVIDENCE_DATABASE_URI`并显式准备研究存储后才可使用；未配置返回503，不在应用初始化时创建研究表。本轮没有启用生产配置。已有聊天接口语义保留。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/sources` | 当前可访问的已登记来源与抽取覆盖 |
| POST | `/search` | 同步来源全文检索，返回文献ID、版本、页码、分块和原文，单列图谱状态 |
| GET | `/sources/{document_id}/chunks/{chunk_index}?content_sha256=...` | 按当前来源版本回看原文，过期/不可见拒绝 |
| POST | `/comparisons` | 排队或复用同一身份/有效签名的证据对照，未完成返回202 |
| GET | `/comparisons/{id}` | 查询自己的任务；完成结果返回前重验有效性 |
| DELETE | `/comparisons/{id}` | 取消自己的queued/running任务 |
| POST | `/records/{id}/reject` | admin/domain_reviewer拒绝待审记录，相关完成缓存随后失效 |

检索/对照请求包含`query`（必填，最多500字）、`document_ids`（M1范围1—10篇）、可选`measure/indicator/soil_type/conditions`及`limit`（1—30）。示例：`{"query":"石灰 产量","document_ids":[1149],"soil_type":"红壤","limit":10}`。未知条件单列unknown，不冒称条件吻合；当前筛选是来源选定文字的明确匹配，不提供语义等价或因果推断。

对照字段包含原文值和精确证据；全部新增记录pending。任务状态包括queued/running/completed/failed/cancelled/invalidated。completed表示任务执行完成，不表示每篇有正例或抽取完整；结果单列每篇覆盖、拒收选择及行数上限。没有匹配不能解释为无效应。接口不提供新断言批准或发布操作。

原文及结果读取执行当前权限、内容和来源字节检查。缓存签名同时绑定研究记录状态、来源版本、请求和生成版本；权限收紧、候选拒绝等变化不会继续返回旧结果。部署及实际性能验证仍按阶段进行，详情见`docs/knowledge-engineering-m1-results.md`。

#### 全库证据检索的文献列表与片段列表

接入`PublishedCorpusSearch`的`/search`路径另返回`documents`文献列表，按已通过两次当前来源校验的候选计算文献级RRF；同一文献多个分块不重复投票。每条包含`document_id`、`content_sha256`、`title`、文献排序信息和`evidence_candidates`定位列表。定位列表保留同文献的多个段落，可通过上述原文接口读取；`support_verified:false`表示尚未核实其是否支持问题。`sources`继续返回分块级RRF排序的原文片段；两份列表分别截取`limit`，文献列表中的证据位置不受最终片段窗口截断。二者都受同一有界融合候选窗口及来源资格约束。

全库路径默认启用版本化的土壤领域词法概念扩展。原查询仍只生成一个查询向量；词法候选配额在原词法与概念词法间平分，两路交错去重，不扩大原候选上限。措施、指标及已识别的时长/酸性/作物概念保留为独立约束，同一概念的别名用OR连接。概念路对多指标采用联合匹配，原词法和向量路继续保留仅涉及部分指标的候选；此策略不进行语义支持、条件适用或错误前提判断。具体别名、配额、命中数和版本位于`retrieval.lexical.expansion`；未识别措施时沿用原词法路，失败通过检索降级状态表达。

应用可设置Flask配置`LITERATURE_EVIDENCE_DOMAIN_EXPANSION=False`关闭词法扩展，或构建`PublishedCorpusSearch(..., enhance_recall=False)`。这是词法策略回退，独立的`documents`输出仍保留；既有聊天检索默认策略未改。以上为代码能力，生产启用及质量验收分别记录。
