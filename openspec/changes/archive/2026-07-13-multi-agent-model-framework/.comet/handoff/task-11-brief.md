# Task 11: 更新 /api/v1/chat/ 接口返回多智能体结构化结果

## 项目位置
这是 Comet Build 阶段 Task 11，修改 `/api/v1/chat/` 端点以返回多智能体结构化结果。前序 Task 1-10 已完成所有智能体、AgentManager 和 LangGraph 集成。当前 HEAD 提交为 `412aa99`。

## 文件操作
- Modify: `framework/api/routes/chat.py`（仅修改 `chat()` 函数的响应构造部分）
- Test: `tests/test_agent_integration.py`（追加 API 集成测试）

## 接口契约
- Consumes: `multi_agent_orchestrator.run` 返回的 `model_results` 中现在包含 AgentManager 的结构化结果（`status`、`data.role`、`data.agents_invoked`、`data.summary`、`data.details`、`data.recommendations`）
- Produces: `/api/v1/chat/` POST 响应 `data` 中新增 `role`、`agents_invoked`、`recommendations` 字段

## 现有代码结构

`framework/api/routes/chat.py` 的 `chat()` 函数（第 49-102 行）当前：
1. 获取用户、对话、消息
2. 调用 `multi_agent_orchestrator.run()`
3. 从 result 提取 `answer`, `sources`, `model_results`, `question_type`
4. 创建 assistant_message 并返回响应

**本任务只需修改第 79 行开始的响应构造部分**（从 `answer = result.get(...)` 到函数末尾）。保留前面的用户/对话/消息处理逻辑不变。

## Step 1: 追加 API 集成测试

在 `tests/test_agent_integration.py` 末尾 `if __name__ == "__main__":` 之前追加：

```python
def test_chat_api_returns_structured_multi_agent_result():
    """通过 Flask test client 验证 /api/v1/chat/ 返回多智能体结构化结果"""
    from framework.api.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        from framework.models.user import db
        db.create_all()

        # 注册测试用户并获取 token
        from framework.models.user import User
        user = User(username="tester", password="x", email="t@t.com")
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    # 用 JWT 装饰器要求登录；此处直接 patch jwt_required 跳过鉴权以聚焦结构验证
    import flask_jwt_extended
    real_jwt_required = flask_jwt_extended.jwt_required
    real_get_jwt_identity = flask_jwt_extended.get_jwt_identity

    class _Dummy:
        def __call__(self, fn):
            return fn

    flask_jwt_extended.jwt_required = _Dummy()
    flask_jwt_extended.get_jwt_identity = lambda: 1

    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "我的田施氮肥施多少？"},
            )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "ok"
        data = payload["data"]
        # 多智能体结构化字段
        assert data.get("role") == "farmer"
        assert data.get("agents_invoked") == ["model-4", "model-5", "model-6"]
        assert isinstance(data.get("recommendations"), list)
        assert "answer" in data
    finally:
        flask_jwt_extended.jwt_required = real_jwt_required
        flask_jwt_extended.get_jwt_identity = real_get_jwt_identity

    print("✓ /api/v1/chat/ 返回多智能体结构化结果")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_chat_api_returns_structured_multi_agent_result()
```

并更新最后一行打印为：

```python
    print("\n所有 LangGraph 与 API 集成测试通过！")
```

## Step 2: 运行测试确认失败

Run: `python tests/test_agent_integration.py`
Expected: FAIL —— 当前 `chat()` 端点未返回 `role` / `agents_invoked` / `recommendations` 字段。

## Step 3: 修改 chat.py 的 chat() 端点

打开 `framework/api/routes/chat.py`，将 `chat()` 函数中**从第 79 行开始**的处理 `result` 与构造响应的部分替换为：

```python
    answer = result.get("answer", result.get("llm_response", ""))
    sources = result.get("sources", [])
    model_results = result.get("model_results", {})
    question_type = result.get("question_type", 0)

    # 解析 AgentManager 结构化结果（若存在）
    agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
    role = agent_data.get("role")
    agents_invoked = agent_data.get("agents_invoked", [])
    recommendations = agent_data.get("recommendations", [])
    multi_agent_summary = agent_data.get("summary", "")

    assistant_message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content=answer or multi_agent_summary,
        sources=sources if sources else None,
    )
    db.session.add(assistant_message)
    db.session.commit()

    response_data = {
        "answer": answer or multi_agent_summary,
        "sources": sources,
        "question_type": question_type,
        "model_results": model_results,
        "message_id": assistant_message.id,
    }
    if role:
        response_data["role"] = role
    if agents_invoked:
        response_data["agents_invoked"] = agents_invoked
    if recommendations:
        response_data["recommendations"] = recommendations

    return jsonify({
        "status": "ok",
        "data": response_data,
    })
```

**重要**：保留文件顶部的 import 与其他端点函数（`get_conversations`、`create_conversation` 等）不变。只替换 `chat()` 函数中从 `answer = result.get(...)` 开始到函数末尾的部分。

## Step 4: 运行测试确认通过

Run: `python tests/test_agent_integration.py`
Expected: PASS，输出 `所有 LangGraph 与 API 集成测试通过！`

## Step 5: Commit

```bash
git add framework/api/routes/chat.py tests/test_agent_integration.py
git commit -m "feat(api): /api/v1/chat/ 返回多智能体结构化结果"
```

## Global Constraints

- 保留 `chat()` 函数前面的用户/对话/消息处理逻辑不变
- 保留文件中其他端点函数不变
- 不引入新的第三方依赖
- 测试沿用"脚本式测试"风格
- TDD 模式：先写失败测试，运行确认 RED，再写实现，运行确认 GREEN

## 关键注意事项

1. **只修改 `chat()` 函数的响应构造部分**（第 79 行起），不修改前面的逻辑
2. `model_results` 现在是 AgentManager 返回的结构：`{"status": "ok", "data": {"role", "agents_invoked", "summary", "details", "recommendations"}}`
3. 当 `model_results` 不包含 AgentManager 结构时（如回退到 fallback），`role`/`agents_invoked`/`recommendations` 字段不会出现在响应中（使用 `if` 条件判断）
4. 测试中使用 patch `jwt_required` 跳过鉴权，聚焦于响应结构验证
5. `flask_jwt_extended.get_jwt_identity` 需要 patch 返回用户 ID（1）
