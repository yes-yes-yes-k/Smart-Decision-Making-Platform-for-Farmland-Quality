# Task 12: 端到端角色路由验证与回归测试

## 项目位置
这是 Comet Build 阶段的最后一个任务（Task 12），验证三类角色端到端路由并完成回归测试。前序 Task 1-11 已完成所有智能体、AgentManager、LangGraph 集成和 API 更新。当前 HEAD 提交为 `6acaa32`。

## 文件操作
- Modify: `tests/test_agent_integration.py`（追加 4 个端到端验证测试）
- Modify: `openspec/changes/multi-agent-model-framework/tasks.md`（勾选所有已完成项）

## 接口契约
- 验证 Task 1-11 的整体协同：三类角色（province/county/farmer）均能正确路由并返回结构化结果

## Step 1: 追加端到端验证测试

在 `tests/test_agent_integration.py` 末尾 `if __name__ == "__main__":` 之前追加：

```python
def test_e2e_province_role_routing():
    """省市管理端问题应路由到 model-1 + model-3"""
    state = _make_state("全省耕地质量整体稳定吗？哪些县区有退化风险？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "province"
    assert data["agents_invoked"] == ["model-1", "model-3"]
    # model-3 依赖 model-2，但 model-2 不在 invoked 集合内 —— 应安全跳过
    for aid in ["model-1", "model-3"]:
        assert aid in data["details"]
        assert data["details"][aid]["simulated"] is True
    print("✓ 省市管理端路由正确（model-1 + model-3）")


def test_e2e_county_role_routing():
    """县域执行端问题应路由到 model-1 + model-3 + model-2，model-3 排在 model-2 之后"""
    state = _make_state("本县乡镇任务如何分配？县域耕地质量如何？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "county"
    assert set(data["agents_invoked"]) == {"model-1", "model-2", "model-3"}
    # model-2 应在 model-3 之前（拓扑序）
    assert data["agents_invoked"].index("model-2") < data["agents_invoked"].index("model-3")
    print("✓ 县域执行端路由正确（model-1 + model-2 + model-3，拓扑序正确）")


def test_e2e_farmer_role_routing():
    """农户种植端问题应路由到 model-4 + model-5 + model-6，model-6 排在最后"""
    state = _make_state("我的田施氮肥施多少？这块地质量怎么样？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
    # model-6 应排在最后
    assert data["agents_invoked"][-1] == "model-6"
    # model-6 应消费了 model-4 与 model-5 的结果
    m6_evidence = str(data["details"]["model-6"]["evidence"])
    assert "model-4" in m6_evidence or "model-5" in m6_evidence or "石灰" in m6_evidence or "有机肥" in m6_evidence
    print("✓ 农户种植端路由正确（model-4 + model-5 + model-6，依赖传递正确）")


def test_e2e_recommendations_aggregated():
    """汇总的 recommendations 应来自各智能体 evidence 中的 recommendation/source"""
    state = _make_state("我的田怎么改良？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert isinstance(data["recommendations"], list)
    # 至少应包含一条建议（来自 model-4 或 model-5 或 model-6）
    assert len(data["recommendations"]) >= 1
    print("✓ recommendations 字段已聚合各智能体建议")
```

并在 `if __name__ == "__main__":` 块中追加（在现有测试调用之后）：

```python
    test_e2e_province_role_routing()
    test_e2e_county_role_routing()
    test_e2e_farmer_role_routing()
    test_e2e_recommendations_aggregated()
```

并更新最后一行打印为：

```python
    print("\n所有端到端验证与集成测试通过！")
```

## Step 2: 运行测试确认通过

Run: `python tests/test_agent_integration.py`
Expected: PASS，全部 8 个测试通过（4 个原有 + 4 个新 E2E）。

## Step 3: 运行全部测试套件做最终回归

依次运行：
```
python tests/test_agent_base.py
python tests/test_agent_manager.py
python tests/test_agent_specialized.py
python tests/test_agent_integration.py
python tests/test_multi_agent.py
```
Expected: 全部 PASS，无回归。

## Step 4: 勾选 openspec tasks.md 中已完成项

打开 `openspec/changes/multi-agent-model-framework/tasks.md`，将第 4 节中所有 `- [ ]` 改为 `- [x]`：
- 4.1 编写智能体基类和 Manager 的单元测试
- 4.2 编写每个专业智能体的独立功能测试（验证模拟计算和问题回答）
- 4.3 编写多智能体协同测试（验证依赖调度和结果汇总）
- 4.4 编写 API 集成测试（验证 `/api/v1/chat/` 接口触发多智能体协作）
- 4.5 验证三类用户角色（省市/县域/农户）的问题都能正确路由和返回结果

## Step 5: Commit

```bash
git add tests/test_agent_integration.py openspec/changes/multi-agent-model-framework/tasks.md
git commit -m "test(agents): 端到端验证三类角色路由并完成 tasks.md 勾选"
```

## Global Constraints

- 测试沿用"脚本式测试"风格（`assert` + `print` + `if __name__ == "__main__":`）
- 测试运行命令为 `python tests/<file>.py`
- 不引入新的第三方依赖
- 所有测试必须全部通过，无回归

## 关键注意事项

1. **province 角色**：路由到 `["model-1", "model-3"]`，model-3 依赖 model-2 但 model-2 不在 invoked 集合内，应安全跳过
2. **county 角色**：路由到 `["model-1", "model-2", "model-3"]`，model-2 应在 model-3 之前（拓扑序）
3. **farmer 角色**：路由到 `["model-4", "model-5", "model-6"]`，model-6 应消费 model-4 和 model-5 的结果
4. **recommendations**：应聚合各智能体 evidence 中的建议
5. tasks.md 第 4 节的 5 个测试任务都应勾选
