# Task 10: 在 LangGraph execute_models 节点集成 AgentManager

## 项目位置
这是 Comet Build 阶段 Task 10，将 AgentManager 集成到 LangGraph 的 `execute_models` 节点。前序 Task 1-9 已完成所有 6 个专业智能体和 AgentManager。当前 HEAD 提交为 `c238b37`。

## 文件操作
- Modify: `framework/agents/__init__.py`（当前为空）
- Modify: `framework/agents/nodes.py`（仅修改 `execute_models` 函数，第 218 行）
- Create: `tests/test_agent_integration.py`

## 接口契约
- Consumes: `agent_manager`（Task 3 产物，模块级单例）、`MultiAgentState`
- Produces: `execute_models` 优先调用 `agent_manager.process`，将结果写入 `state["model_results"]` 与 `state["status"] = "model_completed"`。失败时回退到原 `_execute_models_fallback`

## 现有代码结构（重要上下文）

`framework/agents/nodes.py` 当前 `execute_models` 函数（第 218-257 行）逻辑：
1. 检查 `CORE_ENGINE_AVAILABLE`，若不可用调用 `_execute_models_fallback`
2. 若可用，映射 `question_type` 到 `model_id`，调用 `core_engine.run_thematic_model`
3. 返回 `model_results` dict

**本任务将替换整个 `execute_models` 函数体**，改为：
1. 优先调用 `agent_manager.process(question, context)`
2. 成功时返回 `status: "model_completed"`
3. 失败时回退到 `_execute_models_fallback`（保留不变）

`_execute_models_fallback` 函数（第 259-325 行）保持不变，它使用 asyncio 并发执行 domain 模型。

`framework/agents/__init__.py` 当前为空文件。

`MultiAgentState` 定义在 `framework/agents/state.py`，包含字段：`request, data, model_results, llm_response, rag_response, conversation_history, status, error, question_type, relevance`。

## Step 1: 编写失败测试

创建 `tests/test_agent_integration.py`：

```python
"""测试 AgentManager 与 LangGraph 节点集成"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.state import MultiAgentState
from framework.agents.nodes import execute_models


def _make_state(question: str, question_type: int = 1) -> MultiAgentState:
    return {
        "request": {"question": question, "area_code": "lechang"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": question_type,
        "relevance": 0.8,
    }


def test_execute_models_invokes_agent_manager_farmer():
    """execute_models 应通过 AgentManager 路由到 farmer 智能体组合"""
    state = _make_state("我的田施氮肥施多少？")
    result = execute_models(state)
    assert result["status"] == "model_completed"
    mr = result["model_results"]
    assert mr.get("status") == "ok"
    data = mr.get("data", {})
    assert data.get("role") == "farmer"
    assert data.get("agents_invoked") == ["model-4", "model-5", "model-6"]
    print("✓ execute_models 通过 AgentManager 路由到 farmer")


def test_execute_models_invokes_agent_manager_province():
    state = _make_state("全省耕地酸化程度如何？")
    result = execute_models(state)
    assert result["status"] == "model_completed"
    data = result["model_results"].get("data", {})
    assert data.get("role") == "province"
    assert set(data.get("agents_invoked", [])) == {"model-1", "model-3"}
    print("✓ execute_models 通过 AgentManager 路由到 province")


def test_execute_models_writes_structured_result():
    state = _make_state("我的田质量怎么样？")
    result = execute_models(state)
    data = result["model_results"].get("data", {})
    assert "summary" in data
    assert "details" in data
    assert "recommendations" in data
    # 每个智能体详情应携带 simulated 标记
    for aid, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ execute_models 写入结构化多智能体结果")


if __name__ == "__main__":
    test_execute_models_invokes_agent_manager_farmer()
    test_execute_models_invokes_agent_manager_province()
    test_execute_models_writes_structured_result()
    print("\n所有 LangGraph 集成测试通过！")
```

## Step 2: 运行测试确认失败

Run: `python tests/test_agent_integration.py`
Expected: FAIL —— 当前 `execute_models` 不调用 `agent_manager`，`status` 不会是 `model_completed`，且 `model_results` 结构不同。

## Step 3: 更新 framework/agents/__init__.py

将 `framework/agents/__init__.py`（当前为空）修改为：

```python
from .base import BaseAgent
from .router import RoleRouter
from .manager import agent_manager, AgentManager

__all__ = ["BaseAgent", "RoleRouter", "AgentManager", "agent_manager"]
```

## Step 4: 修改 execute_models 节点函数

打开 `framework/agents/nodes.py`，找到现有的 `execute_models` 函数（第 218 行附近），**将整个函数体替换为**：

```python
def execute_models(state: MultiAgentState) -> MultiAgentState:
    # 优先调用 AgentManager 进行多智能体协作
    try:
        from framework.agents.manager import agent_manager

        question = state["request"].get("question", "")
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
        }
        # 透传可能的土壤参数
        for key in ("longitude", "latitude", "target_ph", "context"):
            if key in state["request"]:
                context[key] = state["request"][key]

        result = agent_manager.process(question, context)
        if result.get("status") == "ok":
            return {
                **state,
                "model_results": result,
                "status": "model_completed",
                "error": None,
            }
    except Exception:
        # AgentManager 失败时回退到原模型执行逻辑
        pass

    return _execute_models_fallback(state)
```

**重要**：保留原 `_execute_models_fallback` 函数（第 259-325 行）与文件中其他函数（`route_models`、`rag_chat_node`、`llm_generate`、`aggregate_results`、`finalize` 等）不变。只替换 `execute_models` 函数体。

## Step 5: 运行测试确认通过

Run: `python tests/test_agent_integration.py`
Expected: PASS，输出 `所有 LangGraph 集成测试通过！`

## Step 6: 重新运行既有测试套件确保未回归

依次运行：
```
python tests/test_agent_base.py
python tests/test_agent_manager.py
python tests/test_agent_specialized.py
python tests/test_multi_agent.py
```
Expected: 全部 PASS。

## Step 7: Commit

```bash
git add framework/agents/__init__.py framework/agents/nodes.py tests/test_agent_integration.py
git commit -m "feat(agents): 在 execute_models 节点集成 AgentManager"
```

## Global Constraints

- 所有智能体输出 SHALL 包含 `simulated: True` 标记
- `execute_models` 优先调用 `agent_manager.process`，失败时回退到 `_execute_models_fallback`
- 不引入新的第三方依赖
- 测试沿用"脚本式测试"风格（`assert` + `print` + `if __name__ == "__main__":`）
- 测试运行命令为 `python tests/<file>.py`
- TDD 模式：先写失败测试，运行确认 RED，再写实现，运行确认 GREEN
- 保留 `_execute_models_fallback` 和其他节点函数不变

## 关键注意事项

1. **只替换 `execute_models` 函数体**，不要修改 `_execute_models_fallback` 或其他函数
2. `framework/agents/__init__.py` 当前为空，直接写入新内容
3. `agent_manager` 是模块级单例，从 `framework.agents.manager` 导入
4. `agent_manager.process(question, context)` 返回 `{"status": "ok", "data": {"role", "agents_invoked", "summary", "details", "recommendations"}}`
5. 测试中 `test_execute_models_invokes_agent_manager_province` 使用 `set()` 比较，因为 province 角色路由到 `["model-1", "model-3"]`，顺序可能因实现而异
