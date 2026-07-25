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

统一智能路由入口，根据问题类型自动路由：
- **question_type=0** → RAG 链（通用问答）
- **question_type=1** → 酸化评估模型
- **question_type=2** → 石灰需求量计算（包含酸化评估）
- **question_type=3** → 氮肥影响模拟

请求体：
```json
{
    "message": "如何治理强酸性耕地？",
    "conversation_id": 1,
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
        "question_type": 2,
        "model_results": {
            "acidification_assessment": {
                "success": true,
                "result": {"level": "严重", "ph": 4.5}
            },
            "lime_calculation": {
                "success": true,
                "result": {"lime_demand": 2500}
            }
        },
        "message_id": 3
    }
}
```

---

## 模型接口

### 获取可用模型列表

**GET** `/api/v1/models/`

成功响应（200）：
```json
{
    "status": "ok",
    "data": [
        {"name": "acidification_assessment", "description": "酸化程度评估模型"},
        {"name": "lime_calculation", "description": "石灰需求量计算模型"},
        {"name": "nitrogen_impact", "description": "氮肥影响模拟模型"},
        {"name": "model_4", "description": "模型4"},
        {"name": "model_5", "description": "模型5"},
        {"name": "model_6", "description": "模型6"}
    ]
}
```

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

用于上传部署三类专题模型数据（CSV / shapefile / .dat），部署前自动备份现有文件，部署后自动触发对应的处理流程。

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

**.dat（data_type=dat）**
- 部署到 `bin/farmland_quality_eval/Farmlands_Quality_Level_Database.dat`（固定文件名）
- 校验：非空、≤ 200MB
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
| 400 | 缺少 data_type/file、data_type 不合法、校验失败（缺列/shapefile 组件不全/.dat 为空等） |
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

# 上传 .dat 数据库
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=dat" \
  -F "file=@/path/to/Farmlands_Quality_Level_Database.dat"
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
