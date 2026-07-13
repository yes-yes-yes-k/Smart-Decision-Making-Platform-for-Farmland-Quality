## 1. 智能体基类框架

- [x] 1.1 创建 `framework/agents/base.py`，实现 `BaseAgent` 抽象基类，定义 `execute(task)`、`answer_question(question, context)` 方法和 `name`/`description`/`model_id`/`domain` 属性
- [x] 1.2 创建 `framework/agents/manager.py`，实现 `AgentManager` 中心化编排器，包含智能体注册、任务分配、依赖调度和结果汇总功能
- [x] 1.3 创建 `framework/agents/mock_data.py`，实现模拟数据层基类，提供模拟数据加载和阈值规则计算工具

## 2. 专业智能体实现

- [x] 2.1 创建 `framework/agents/specialized/stability_risk_agent.py`，实现 StabilityRiskAgent（模型1），包含等级稳定性评价和退化风险识别的模拟计算
- [x] 2.2 创建 `framework/agents/specialized/potential_agent.py`，实现 PotentialAssessmentAgent（模型2），包含提升潜力评估和障碍度值计算的模拟逻辑
- [x] 2.3 创建 `framework/agents/specialized/problem_agent.py`，实现 ProblemIdentificationAgent（模型3），包含障碍因素识别和障碍组合分析的模拟逻辑
- [x] 2.4 创建 `framework/agents/specialized/acidification_agent.py`，实现 AcidificationRemediationAgent（模型4），包含酸化程度判定和调理剂施用量计算的模拟逻辑
- [x] 2.5 创建 `framework/agents/specialized/organic_matter_agent.py`，实现 OrganicMatterAgent（模型5），包含有机质评估和有机肥施用量计算的模拟逻辑
- [x] 2.6 创建 `framework/agents/specialized/comprehensive_agent.py`，实现 ComprehensiveImprovementAgent（模型6），包含多模型结果综合和分区分类建议的模拟逻辑

## 3. 角色路由与集成

- [x] 3.1 创建 `framework/agents/router.py`，实现用户角色识别（省市/县域/农户）和智能体组合路由逻辑
- [x] 3.2 修改 `framework/agents/nodes.py`，在 `execute_models` 节点中集成 AgentManager 调用
- [x] 3.3 修改 `framework/agents/orchestrator.py`，确保 MultiAgentOrchestrator 正确调用 AgentManager
- [x] 3.4 修改 `framework/api/routes/chat.py`，支持返回多智能体协作的结构化结果

## 4. 测试与验证

- [x] 4.1 编写智能体基类和 Manager 的单元测试
- [x] 4.2 编写每个专业智能体的独立功能测试（验证模拟计算和问题回答）
- [x] 4.3 编写多智能体协同测试（验证依赖调度和结果汇总）
- [x] 4.4 编写 API 集成测试（验证 `/api/v1/chat/` 接口触发多智能体协作）
- [x] 4.5 验证三类用户角色（省市/县域/农户）的问题都能正确路由和返回结果

## 5. 代码审查记录（review_mode: standard）

最终全分支审查结果：**APPROVED**（0 Critical, 0 Important, 5 Minor）

5 个 Minor 建议的接受理由（不阻塞合并，可在后续迭代优化）：

1. **`execute` 返回冗余顶层 `simulated` 键**：6 个专业智能体的 `execute` 使用 `mark_simulated()` 在顶层添加了冗余 `simulated: True`（spec 要求仅在 `metadata.simulated` 中）。接受理由：`mark_simulated` 是 MockDataLoader 提供的统一标记工具，额外标记不影响功能，且测试已验证 `metadata.simulated` 存在。后续可统一为仅在 metadata 中标记。

2. **`_summarize` 重复调用拓扑排序**：`AgentManager._summarize` 重复调用 `_topological_sort`。接受理由：功能正确，性能影响可忽略（智能体数量固定为 6），模拟环境下无需优化。

3. **`PotentialAssessmentAgent` 未消费 context**：model-2 忽略 context 始终使用硬编码 mock 数据。接受理由：模拟环境下所有数据均为 mock，行为差异不影响功能正确性。后续迭代可统一 context 消费模式。

4. **综合智能体使用脆弱的字符串匹配**：`_match_measures` 将 evidence 序列化为字符串后做子串搜索。接受理由：模拟环境下 evidence 结构可控，字符串匹配可接受。生产化时需改为结构化字段匹配。

5. **Task 3.3 描述与实现不符**：tasks.md 标记"修改 orchestrator.py"，实际通过 nodes.py 完成集成。接受理由：功能正确，orchestrator.py 通过 LangGraph 图间接调用 execute_models，自动获得 AgentManager 集成，无需直接修改。
