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

请求体：
```json
{
    "message": "我的田有机质培肥施用量多少？",
    "conversation_id": 1,
    "area_code": "lechang",
    "parcel_id": "1",
    "parcel_code": "A0001",
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
| `message` | string | 是 | 用户问题 |
| `conversation_id` | int | 否 | 对话 ID，不传则创建新对话 |
| `area_code` | string | 否 | 区域代码（默认 "lechang"，model-1/3/4 按 area_code 查 DB） |
| `parcel_id` | string | 否 | 地块 ID（数字字符串，给 model-1/3/4 查 DB），农户端问题或 type 5 问题建议携带 |
| `parcel_code` | string | 否 | 地块代码（字母数字，给 model-2 质量等级评价使用） |
| `land_type` | string | 否 | 土地利用类型（`upland` 旱地 / `paddy` 水田；model-5 韶关区域按此选择 RF 子模型，默认 `upland`） |
| `fertilizer_type` | string | 否 | 肥料类型（`compound` 复合肥 / `urea` 尿素，默认 `compound`，酸化改良 model-4 使用，与 `land_type` 组合选择 4 子模型） |
| `context` | object | 否 | 专业模型参数 |

context 参数说明：
| 参数 | 类型 | 说明 |
|------|------|------|
| `target_ph` | float | 目标 pH 值（默认 6.0） |
| `soil_depth` | float | 土壤深度（cm，默认 20） |
| `bulk_density` | float | 土壤容重（g/cm³，默认 1.2） |
| `safety_factor` | float | 安全系数（默认 1.3） |
| `current_ph` | float | 当前 pH 值（默认 5.5） |
| `nitrogen_rates` | array | 氮肥施用量序列（kg/ha，默认 [0, 50, 100, 150, 200]） |
| `area_code` | string | 区域代码（默认 "lechang"） |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "answer": "根据评估结果，建议施用石灰...",
        "sources": [{"doc_name": "土壤治理指南.pdf"}],
        "question_type": 5,
        "model_results": {
            "status": "ok",
            "data": {
                "question_type": 5,
                "agents_invoked": ["model-5"],
                "summary": "[model-5] 有机质培肥模型已完成结构化分析",
                "details": {
                    "model-5": {
                        "answer": "SOC约 24.1 g/kg，建议施用量约 312.4 t/ha",
                        "evidence": [{"metric": "model_version", "value": "SG_RF_v2_20260804"}],
                        "confidence": 0.96,
                        "simulated": false
                    }
                },
                "recommendations": ["预测结果仅供辅助决策，请结合田间试验复核"]
            }
        },
        "agents_invoked": ["model-5"],
        "recommendations": ["预测结果仅供辅助决策，请结合田间试验复核"],
        "message_id": 3
    }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `answer` | string | 综合回答内容 |
| `sources` | array | RAG 引用文档列表（仅 type 0 或 RAG 命中时返回） |
| `question_type` | int | 问题类型（0-6），见上方路由说明 |
| `model_results` | object | 多智能体框架返回的结构化结果（type 1-6 时返回） |
| `agents_invoked` | array | 调用的智能体 ID 列表（1:1 映射，仅含单一模型） |
| `recommendations` | array | 综合建议列表 |
| `message_id` | int | 本次回答的消息 ID |

> 注：API 响应不再包含 `role` 字段（已移除）。客户端应使用 `question_type` 字段判断问题类型。

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

#### 响应字段

`question_type=2` 时，`model_results.data.details["model-4"]` 返回 `acidification_detail` 对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| `acidification_detail.status` | string | 执行状态：`success` / `rejected` |
| `acidification_detail.result.ytk` | float | 亿土康施用量（kg/ha），rejected 时为 `null` |
| `acidification_detail.result.mbnt` | float | 木本泥炭施用量（kg/ha），rejected 时为 `null` |
| `acidification_detail.result.sub_model` | string | 命中的子模型名称（如 `upland_compound`） |
| `acidification_detail.result.customized_params` | object | API 覆盖的可配参数，空对象表示全用默认值 |
| `acidification_detail.metadata.model_version` | string | 过程模型版本号（`process_v2_20260801`） |
| `acidification_detail.metadata.warning` | string | 警告信息（如 land_type/fertilizer_type 非法回退），无警告时缺省 |
| `acidification_detail.metadata.reason` | string | rejected 原因：`missing_input` / `input_out_of_range` / `cannot_get_ph` / `model_unavailable` |

#### 响应示例（question_type=2 酸化改良）

```json
{
    "status": "ok",
    "data": {
        "answer": "基于过程模型（upland_compound）计算，建议亿土康（YTK）施用量约 6413.6 kg/ha，木本泥炭（MBNT）约 11814.1 kg/ha（土地利用类型：upland，肥料类型：compound）。",
        "sources": [],
        "question_type": 2,
        "model_results": {
            "status": "ok",
            "data": {
                "question_type": 2,
                "agents_invoked": ["model-4"],
                "summary": "[model-4] 酸化改良：亿土康 6413.6 kg/ha, 木本泥炭 11814.1 kg/ha (upland_compound)",
                "details": {
                    "model-4": {
                        "answer": "基于过程模型（upland_compound）计算，建议亿土康（YTK）施用量约 6413.6 kg/ha，木本泥炭（MBNT）约 11814.1 kg/ha（土地利用类型：upland，肥料类型：compound）。",
                        "evidence": [
                            {"metric": "ytk", "value": 6413.6, "unit": "kg/ha"},
                            {"metric": "mbnt", "value": 11814.1, "unit": "kg/ha"},
                            {"metric": "sub_model", "value": "upland_compound"},
                            {"metric": "land_type", "value": "upland"},
                            {"metric": "fertilizer_type", "value": "compound"}
                        ],
                        "confidence": 0.88,
                        "acidification_detail": {
                            "status": "success",
                            "result": {
                                "ytk": 6413.6,
                                "mbnt": 11814.1,
                                "sub_model": "upland_compound",
                                "customized_params": {}
                            },
                            "metadata": {
                                "model_version": "process_v2_20260801",
                                "warning": null,
                                "reason": null
                            }
                        },
                        "simulated": false
                    }
                },
                "recommendations": ["建议施用亿土康（YTK）约 6413.6 kg/ha 调节土壤酸度", "配合木本泥炭（MBNT）约 11814.1 kg/ha 提升有机质"]
            }
        },
        "agents_invoked": ["model-4"],
        "recommendations": ["建议施用亿土康（YTK）约 6413.6 kg/ha 调节土壤酸度", "配合木本泥炭（MBNT）约 11814.1 kg/ha 提升有机质"],
        "message_id": 4
    }
}
```

#### rejected 响应示例（缺少必填输入）

```json
{
    "acidification_detail": {
        "status": "rejected",
        "result": {"ytk": null, "mbnt": null, "sub_model": null, "customized_params": {}},
        "metadata": {
            "model_version": "process_v2_20260801",
            "reason": "cannot_get_ph"
        }
    }
}
```

> `reason` 取值：`missing_input`（SJD/JHX/JLA 任一缺失）、`input_out_of_range`（pHstart 不在 [3,10] 或 Hex/Alex < 0）、`cannot_get_ph`（parcel_id 查 DB 未取到 SJD）、`model_unavailable`（acidification 模块不可用，优雅降级）。

---

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

请求 `model_id` 使用公开标识 `organic-matter-improvement`。韶关区域按 `land_type` 选择旱地/水田 RF；规范字段也可以替换为外部模型字段 `SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX`。

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
    "Fertilizer type": 1
}
```

响应中的 `model_id` 为 `model-5`，并包含 `soc_prediction`、`dose_prediction`、`dose_confidence`、`model_version=SG_RF_v2_20260804` 和 `simulated=false`。缺少特征、模型文件或依赖时，响应会明确标记 `fallback`/`simulated` 与 `fallback_reason`，不会伪装为 RF 成功结果。`model_id=placeholder` 对应 model-6 占位能力，不调用该 RF 引擎。

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
    "area_code": "lechang",
    "target_ph": 6.0
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `area_code` | string | 否 | 区域代码（默认 "lechang"） |
| `target_ph` | float | 否 | 目标 pH 值（默认 6.0） |

成功响应（200）：
```json
{
    "status": "ok",
    "data": {
        "area": "lechang",
        "assessment": {
            "level": "中度",
            "ph": 5.2
        },
        "calculation": {
            "lime_demand": 1800,
            "target_ph": 6.0,
            "safety_factor": 1.3
        }
    }
}
```

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
