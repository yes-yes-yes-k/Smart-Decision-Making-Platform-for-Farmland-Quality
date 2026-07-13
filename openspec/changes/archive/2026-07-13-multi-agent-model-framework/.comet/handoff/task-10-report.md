# Task 10 报告：在 LangGraph execute_models 节点集成 AgentManager

## 状态

**DONE**

## 提交 hash

- 完整：`412aa99d3fb22e063e8488636065ecb07bdea8a1`
- 短：`412aa99`
- 分支：`feature/20260713/multi-agent-model-framework`
- 父提交：`c238b37`（Task 9 HEAD）

## 修改的文件清单

1. `framework/agents/__init__.py`（修改：从空文件改为导出 `BaseAgent`、`RoleRouter`、`AgentManager`、`agent_manager`）
2. `framework/agents/nodes.py`（修改：仅替换 `execute_models` 函数体，第 218-245 行；`_execute_models_fallback` 及其他节点函数保持不变）
3. `tests/test_agent_integration.py`（新建：3 个 LangGraph 集成测试，脚本式风格）

变更统计：3 files changed, 92 insertions(+), 34 deletions(-)

## 测试运行输出

### RED 阶段（确认失败）

命令：`python tests/test_agent_integration.py`

```
Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given
Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given
Traceback (most recent call last):
  File "D:\17417\Documents\agent_culti_demo\tests\test_agent_integration.py", line 62, in <module>
    test_execute_models_invokes_agent_manager_farmer()
  File "D:\17417\Documents\agent_culti_demo\tests\test_agent_integration.py", line 29, in test_execute_models_invokes_agent_manager_farmer
    assert result["status"] == "model_completed"
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

**RED 确认**：测试因 `execute_models` 返回的 `status` 不等于 `model_completed` 失败，符合预期（旧实现不调用 `agent_manager`，未设置 `model_completed` 状态）。退出码 1。

### GREEN 阶段（集成测试通过）

命令：`python tests/test_agent_integration.py`

```
Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given
Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given
✓ execute_models 通过 AgentManager 路由到 farmer
✓ execute_models 通过 AgentManager 路由到 province
✓ execute_models 写入结构化多智能体结果

所有 LangGraph 集成测试通过！
```

退出码 0，3/3 通过。

### 回归测试 1：test_agent_base.py

命令：`python tests/test_agent_base.py`

```
✓ BaseAgent 抽象类阻止直接实例化
✓ 子类未实现全部抽象方法时抛出 TypeError
✓ BaseAgent 完整子类构造与方法调用正常
✓ MockDataLoader.merge_defaults 优先使用输入值
✓ MockDataLoader.mark_simulated 添加标记且不污染原对象
✓ MockDataLoader.apply_threshold 按顺序匹配规则
✓ RoleRouter 识别省市角色
✓ RoleRouter 识别县域角色
✓ RoleRouter 识别农户角色与默认值
✓ RoleRouter 返回正确的智能体组合

所有 BaseAgent、MockDataLoader、RoleRouter 测试通过！
```

退出码 0，10/10 通过。

### 回归测试 2：test_agent_manager.py

命令：`python tests/test_agent_manager.py`

```
✓ AgentManager 注册 6 个智能体
✓ 拓扑排序处理部分依赖（依赖不在集合内时安全跳过）
✓ 拓扑排序将依赖项放在被依赖项之后
✓ AgentManager.process 返回符合规范的结构化结果
✓ 未知问题默认路由到 farmer

所有 AgentManager 测试通过！
```

退出码 0，5/5 通过。

### 回归测试 3：test_agent_specialized.py

命令：`python tests/test_agent_specialized.py`

```
✓ StabilityRiskAgent.execute 返回县区稳定性数据
✓ StabilityRiskAgent.answer_question 返回稳定性总体评价
✓ StabilityRiskAgent.answer_question 识别退化风险区域
✓ PotentialAssessmentAgent.execute 返回 11 评价指标
✓ PotentialAssessmentAgent.answer_question 返回潜力评估
✓ PotentialAssessmentAgent 在 evidence 中暴露 target_ph
✓ ProblemIdentificationAgent.execute 返回障碍因素结构
✓ ProblemIdentificationAgent.answer_question 返回障碍识别
✓ ProblemIdentificationAgent 消费 model-2 的 target_ph
✓ AcidificationRemediationAgent.execute 返回酸化判定与石灰用量
✓ AcidificationRemediationAgent 返回酸化程度
✓ AcidificationRemediationAgent 返回石灰施用量建议
✓ OrganicMatterAgent.execute 返回有机质分级与施用量
✓ OrganicMatterAgent 返回有机质含量评估
✓ OrganicMatterAgent 返回有机肥施用量建议
✓ ComprehensiveImprovementAgent.execute 返回综合诊断结构
✓ ComprehensiveImprovementAgent 返回农户地块综合诊断
✓ ComprehensiveImprovementAgent 消费 model-4 和 model-5 结果

所有专业智能体测试通过！
```

退出码 0，18/18 通过。

### 回归测试 4：test_multi_agent.py

命令：`python tests/test_multi_agent.py`

```
Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given
Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given
Failed to send telemetry event CollectionQueryEvent: capture() takes 1 positional argument but 3 were given
✓ 状态初始化成功
  通用问题: type=3, relevance=0.67
  酸化评估: type=1, relevance=0.98
  治理方案: type=2, relevance=0.97
✓ 问题类型识别成功
✓ 路由函数正确
LLM调用失败，使用降级模式: Request timed out.
✓ RAG 节点执行成功
✓ RAG 结果聚合成功
✓ 专业模型结果聚合成功

所有多智能体并发工作流测试通过！
```

退出码 0，7/7 通过。注意：`LLM调用失败，使用降级模式` 是既有降级路径的预期行为（网络超时），非本次变更引入的回归。

## 测试摘要

- 集成测试：3/3 PASS
- 回归测试（4 个套件）：40/40 PASS
- 总计：43/43 PASS

## 关键实现要点

1. **`framework/agents/__init__.py`** 导出 `BaseAgent`、`RoleRouter`、`AgentManager`、`agent_manager`，便于外部使用 `from framework.agents import agent_manager`。
2. **`execute_models`** 优先调用 `agent_manager.process(question, context)`：
   - 成功（`status == "ok"`）时返回 `{"status": "model_completed", "model_results": result, "error": None}` 并保留原 state 其他字段
   - 任何异常或非 `ok` 状态均回退到 `_execute_models_fallback(state)`
3. **`_execute_models_fallback`** 完整保留，未被改动。
4. **context 字段透传**：`area_code`、`data` 必传；`longitude`、`latitude`、`target_ph`、`context` 在 request 中存在时透传给 `agent_manager`。

## 顾虑

无。
- RED 阶段失败原因明确（`status != "model_completed"`）。
- GREEN 阶段一次通过，无返工。
- 4 个回归测试套件全部通过，无回归。
- 日志中出现的 `Failed to send telemetry event` 与 `LLM调用失败，使用降级模式` 均为既有环境问题（VSCode Python 扩展遥测、网络超时），与本任务变更无关。
- Git 提示 `LF will be replaced by CRLF` 为 Windows 平台正常换行符处理，不影响功能。
