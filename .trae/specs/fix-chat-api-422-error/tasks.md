# 修复 /api/v1/chat/ 接口 422 错误 - The Implementation Plan (Decomposed and Prioritized Task List)

## [ ] Task 1: 配置 flask-jwt-extended 统一错误处理
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 [app.py](file:///E:/Agent/agent_culti_demo/framework/api/app.py) 中配置 `JWTManager` 的错误回调函数
  - 自定义 `unauthorized_loader`、`invalid_token_loader`、`expired_token_loader` 等回调
  - 将默认的 `{"msg": "..."}` 格式改为项目统一的 `{"status": "error", "message": "..."}` 格式
  - 确保返回正确的 HTTP 状态码（401 而非 422）
- **Acceptance Criteria Addressed**: AC-1, AC-4
- **Test Requirements**:
  - `programmatic` TR-1.1: 不带 Authorization header 请求 `/api/v1/chat/` 返回 401 和统一错误格式
  - `programmatic` TR-1.2: 带无效 token 请求 `/api/v1/chat/` 返回 401 和统一错误格式
  - `programmatic` TR-1.3: 带过期 token 请求 `/api/v1/chat/` 返回 401 和统一错误格式
  - `human-judgement` TR-1.4: 错误信息清晰易懂，中文提示
- **Notes**: 在 `create_app` 函数中配置 JWTManager 的回调函数，确保所有使用 `@jwt_required()` 的路由都生效

## [ ] Task 2: 统一聊天接口参数命名（向后兼容）
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 修改 [chat.py](file:///E:/Agent/agent_culti_demo/framework/api/routes/chat.py) 的 `chat()` 函数
  - 同时支持 `message` 和 `content` 两个参数名，优先使用 `content`，`message` 作为备选
  - 保持向后兼容，不破坏已有调用方
- **Acceptance Criteria Addressed**: AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-2.1: 发送 `{"content": "你好"}` 能正常处理并返回结果
  - `programmatic` TR-2.2: 发送 `{"message": "你好"}` 也能正常处理（向后兼容）
  - `programmatic` TR-2.3: 同时发送 `content` 和 `message` 时，优先使用 `content`
- **Notes**: 用 `data.get('content') or data.get('message', '')` 的方式实现，保持简单

## [ ] Task 3: 验证所有受影响的接口正常工作
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 运行现有测试套件，确保修改不影响其他功能
  - 验证 `/api/v1/auth/me`、`/api/v1/chat/conversations` 等其他需要认证的接口行为不变
  - 手动测试完整的登录→聊天流程
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 现有测试套件 `pytest tests/` 全部通过
  - `programmatic` TR-3.2: `/api/v1/auth/me` 接口在带/不带 token 时行为正确
  - `programmatic` TR-3.3: `/api/v1/chat/conversations` 接口认证行为正确
  - `human-judgement` TR-3.4: 手动端到端测试：登录→发送消息→收到回复，完整流程正常
- **Notes**: 如果没有完整的用户数据，可以先运行现有测试，再手动验证核心流程
