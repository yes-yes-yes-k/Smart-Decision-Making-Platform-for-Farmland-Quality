# 修复 /api/v1/chat/ 接口 422 "Not enough segments" 错误 - Product Requirement Document

## Overview
- **Summary**: 修复后端 `/api/v1/chat/` 接口返回 422 状态码和 "Not enough segments" 错误的问题，同时解决前后端参数不匹配的问题，确保前端聊天功能能够正常调用后端接口。
- **Purpose**: 解决当前后端服务启动后聊天接口无法正常使用的问题，使前端 AI 聊天面板能够正常与后端通信。
- **Target Users**: 前端开发者、后端开发者、测试人员

## Goals
- 修复 JWT 认证导致的 422 "Not enough segments" 错误
- 统一前后端聊天接口的参数命名
- 确保前端聊天功能可以正常调用后端接口并获得正确响应
- 提供清晰的错误处理和调试信息

## Non-Goals (Out of Scope)
- 不重构整个认证系统
- 不改变 JWT 认证机制本身
- 不添加新的聊天功能
- 不修改数据库结构

## Background & Context
### 问题现象
后端服务启动后，调用 `POST /api/v1/chat/` 接口返回：
```
HTTP 422
{"msg": "Not enough segments"}
```

### 代码现状
1. **后端 [chat.py](file:///E:/Agent/agent_culti_demo/framework/api/routes/chat.py)**：
   - 第 49-51 行：`/` 路由使用了 `@jwt_required()` 装饰器
   - 第 55 行：从请求体获取 `message` 字段：`message = data.get('message', '')`

2. **前端 [chat.js](file:///E:/Agent/farmland-quality-rag/client/src/api/chat.js)**：
   - 第 42-44 行：`sendMessage` 函数发送 `{ conversation_id, content }`
   - 参数名为 `content`，与后端的 `message` 不匹配

3. **前端 [request.js](file:///E:/Agent/farmland-quality-rag/client/src/utils/request.js)**：
   - 第 21-39 行：请求拦截器从 `sessionStorage` 获取 token 并添加到 Authorization header
   - 如果没有 token，则不添加 Authorization header

### 错误原因分析
**"Not enough segments"** 是 `flask-jwt-extended` 库在解析 JWT token 时抛出的错误。

JWT token 的标准格式是三段式：`header.payload.signature`，用 `.` 分隔。当 token 段数不足时（例如 token 为空、格式错误或只有 1-2 段），就会报此错误。

可能的触发场景：
1. 用户未登录，`sessionStorage` 中没有 token，前端未发送 Authorization header
2. 发送了格式错误的 token（例如不是标准 JWT 格式）
3. 直接用 curl/Postman 测试接口时未提供正确的 Authorization header

**附加问题**：前后端参数不匹配
- 前端发送：`{ conversation_id, content }`
- 后端期望：`{ conversation_id, message }`

## Functional Requirements
- **FR-1**: 后端聊天接口在无有效 JWT token 时应返回清晰的 401 错误信息（而非 422 + "Not enough segments"）
- **FR-2**: 后端聊天接口的请求参数应与前端保持一致（支持 `content` 或同时支持 `message` 和 `content`）
- **FR-3**: 后端应统一错误响应格式，使用 `{ "status": "error", "message": "..." }` 格式

## Non-Functional Requirements
- **NFR-1**: 修复后接口响应时间应保持不变
- **NFR-2**: 不影响其他已有的认证接口
- **NFR-3**: 向后兼容，不破坏现有已登录用户的正常使用

## Constraints
- **Technical**: Python Flask, flask-jwt-extended, Vue3 + Axios
- **Business**: 必须保持现有认证机制，不能移除 JWT 认证
- **Dependencies**: flask-jwt-extended 库的错误处理机制

## Assumptions
- 前端用户应该先登录获取 token，然后再使用聊天功能
- 未登录用户调用聊天接口应该收到明确的未认证提示
- 前后端需要统一参数命名以避免混淆

## Acceptance Criteria

### AC-1: 未提供 token 时返回清晰的 401 错误
- **Given**: 用户未登录或未提供有效的 JWT token
- **When**: 调用 `POST /api/v1/chat/` 接口
- **Then**: 应返回 HTTP 401 状态码，响应体为 `{ "status": "error", "message": "未登录或登录已过期" }` 格式
- **Verification**: `programmatic`

### AC-2: 前后端参数名统一
- **Given**: 前端发送 `{ "conversation_id": 1, "content": "你好" }`
- **When**: 调用 `POST /api/v1/chat/` 接口
- **Then**: 后端应能正确解析并处理消息内容
- **Verification**: `programmatic`

### AC-3: 已登录用户正常使用聊天功能
- **Given**: 用户已登录并持有有效 JWT token
- **When**: 调用 `POST /api/v1/chat/` 接口发送消息
- **Then**: 应正常返回 AI 回答，状态码 200
- **Verification**: `programmatic`

### AC-4: 错误响应格式统一
- **Given**: 接口发生认证错误或参数错误
- **When**: 返回错误响应
- **Then**: 响应体格式应为 `{ "status": "error", "message": "错误描述" }`，与项目其他接口保持一致
- **Verification**: `programmatic`

### AC-5: 不影响其他接口
- **Given**: 修复了聊天接口的错误处理
- **When**: 调用其他需要认证的接口（如 `/api/v1/auth/me`）
- **Then**: 行为应保持不变，正常工作
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要为开发环境提供一个绕过 JWT 认证的开关，方便调试？
- [ ] 前端是否有登录页面和完整的用户认证流程？
