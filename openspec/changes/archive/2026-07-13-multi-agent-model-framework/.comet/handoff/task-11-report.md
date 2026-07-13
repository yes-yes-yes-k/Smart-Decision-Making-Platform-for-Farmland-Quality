# Task 11 Report: 更新 /api/v1/chat/ 接口返回多智能体结构化结果

## 状态
DONE_WITH_CONCERNS

## 提交 hash
`6acaa32b5cddd7ab1c7dde6f6e68d5acce4e8b63`（短 hash: `6acaa32`）

分支: `feature/20260713/multi-agent-model-framework`

## 修改的文件清单
1. `framework/api/routes/chat.py` — 修改 `chat()` 函数的响应构造部分（第 79 行起），新增从 `model_results.data` 解析 `role`/`agents_invoked`/`recommendations`/`summary` 并条件性写入顶层 `response_data` 的逻辑。
2. `tests/test_agent_integration.py` — 追加 `test_chat_api_returns_structured_multi_agent_result` 测试，并在 `__main__` 块中调用、更新末尾打印文案。

## 测试运行输出

### RED 阶段（实现前）
```
✓ execute_models 通过 AgentManager 路由到 farmer
✓ execute_models 通过 AgentManager 路由到 province
✓ execute_models 写入结构化多智能体结果
Traceback (most recent call last):
  File "D:\17417\Documents\agent_culti_demo\tests\test_agent_integration.py", line 106, in <module>
    test_chat_api_returns_structured_multi_agent_result()
  File "D:\17417\Documents\agent_culti_demo\tests\test_agent_integration.py", line 94, in test_chat_api_returns_structured_multi_agent_result
    assert data.get("role") == "farmer"
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```
失败原因正确：当前端点将 `role`/`agents_invoked`/`recommendations` 嵌套在 `model_results.data` 内，未暴露到响应 `data` 顶层。

### GREEN 阶段（实现后）
```
✓ execute_models 通过 AgentManager 路由到 farmer
✓ execute_models 通过 AgentManager 路由到 province
✓ execute_models 写入结构化多智能体结果
LLM调用失败，使用降级模式: Request timed out.
✓ /api/v1/chat/ 返回多智能体结构化结果

所有 LangGraph 与 API 集成测试通过！
```
退出码 0，全部测试通过。`LLM调用失败，使用降级模式: Request timed out.` 为 orchestrator 在无真实 LLM API key 环境下的预期降级日志，不影响测试结果。

## 顾虑

### 1. 测试代码与 brief 的偏离（上游产物适配）
brief 的测试代码假定可以通过 `flask_jwt_extended.jwt_required = _Dummy()` 跳过鉴权，但实际不可行，原因有二：
- **装饰器已在导入时应用**：`chat.py` 的 `@jwt_required()` 在模块导入时已将 `chat` 函数包装，运行时包装器调用的是 `flask_jwt_extended.view_decorators.verify_jwt_in_request`（模块级名字），patch `flask_jwt_extended.jwt_required` 无法撤销已应用的装饰器。
- **`get_jwt_identity` 的导入绑定**：`chat.py` 使用 `from flask_jwt_extended import get_jwt_identity`，形成局部引用，patch `flask_jwt_extended.get_jwt_identity` 不影响 `chat.py` 内的局部名字。

此外 brief 假定 `User` 模型有 `email` 字段，但实际 `framework/models/user.py` 的 `User` 并无 `email` 列。

**适配方案**（最小化偏离，保留 brief 测试意图）：
- 移除 `User(email=...)` 中不存在的 `email` 参数。
- 用 `create_access_token(identity=str(user_id))` 签发真实 JWT，通过 `Authorization: Bearer <token>` 头通过鉴权（与 `framework/api/routes/auth.py` 中 `login()` 既有做法一致：`create_access_token(identity=str(user.id))`）。
- 复用已存在的 `tester` 用户（若已存在则查询复用），避免 UNIQUE 约束冲突。
- 不再使用 `app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"` 覆盖（因 `db.init_app(app)` 已在 `create_app()` 内完成，且 `SQLALCHEMY_ENGINE_OPTIONS` 的 MySQL 选项与 in-memory SQLite 不兼容），直接使用默认 `development.db`。

### 2. 实现代码与 brief 完全一致
`framework/api/routes/chat.py` 的实现部分（第 79 行起）与 brief Step 3 逐字一致，未做任何偏离。`chat()` 函数前面的用户/对话/消息处理逻辑完全保留。

### 3. 降级场景兼容
按 brief 注意事项 3，当 `model_results` 不包含 AgentManager 结构（如 fallback）时，`role`/`agents_invoked`/`recommendations` 字段不会出现在响应中（使用 `if` 条件判断）。实现已遵循此约定。
