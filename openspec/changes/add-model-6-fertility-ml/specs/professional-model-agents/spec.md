## MODIFIED Requirements

### Requirement: FertilityMLAgent 智能体
系统 SHALL 实现 `FertilityMLAgent` 智能体，对应模型6「耕地肥力机器学习预测模型」，负责调用预训练的 ExtraTreesRegressor 模型对 SOC（土壤有机碳）和 Dose（施用量）进行预测，并通过 `framework/agents/manager.py` 注册为 `model-6`。该智能体不再依赖其他模型结果，作为独立的计算单元接入 farmer 角色路由。

#### Scenario: 农户 SOC 预测查询
- **WHEN** 农户询问"我的田土壤有机碳含量大概多少？"，且 `framework/agents/manager.py` 已将 `FertilityMLAgent` 注册为 `model-6`
- **THEN** 智能体 SHALL 调用 `framework/domain/other_models/model_6.py` 中的 `model_6_execution`，传入从问题中提取或默认填充的土壤特征字典，返回包含 `soc_prediction`（g/kg）、`soc_confidence`（0.91）、`model_version` 的结构化结果，并由 `answer_question` 方法包装为包含 `answer`、`evidence`、`confidence` 字段的自然语言响应

#### Scenario: 农户 Dose 施用量预测查询
- **WHEN** 农户询问"我这块地大概需要施多少有机肥？"
- **THEN** 智能体 SHALL 调用 `model_6_execution` 返回 `dose_prediction`（kg/亩）、`dose_confidence`（0.47）、`dose_warning` 字段，并在自然语言回答中明确标注"预测结果仅供参考"

#### Scenario: 综合肥力诊断查询
- **WHEN** 农户询问"我的田肥力怎么样？"
- **THEN** 智能体 SHALL 同时返回 SOC 和 Dose 两个预测值，并提供综合诊断说明（如"SOC 预测 X g/kg，建议施肥量约 Y kg/亩"），`evidence` 字段包含两个预测值的指标列表

#### Scenario: 模型降级时的回退响应
- **WHEN** `model_6_execution` 返回 `status: "fallback"`（模型文件缺失或 sklearn 未安装）
- **THEN** 智能体 SHALL 在 `answer` 中标注"基于训练集均值的估算"而非"基于 ML 模型预测"，`confidence` 字段值降低到 0.3，并在 `evidence` 中包含 `fallback_reason` 字段

#### Scenario: Agent 独立执行无依赖
- **WHEN** `AgentManager.process` 调用 farmer 角色对应的智能体集合 `["model-4", "model-5", "model-6"]`
- **THEN** `model-6`（FertilityMLAgent）的 `dependencies` SHALL 为空列表 `[]`，可在拓扑排序中与 `model-4`、`model-5` 并行执行，不等待上游 agent 结果

#### Scenario: 非肥力相关问题跳过 model-6
- **WHEN** 农户角色提出的问题不包含肥力相关关键词（如"我的田 pH 如何"），且 `AgentManager` 路由到 model-6
- **THEN** `AgentManager._should_execute_agent` SHALL 返回 False，model-6 不被执行（不触发模型加载），`details["model-6"]` 字段值为 `{status: "skipped", reason: "question_not_related"}`。肥力关键词列表包括：有机碳、SOC、施用量、施肥量、施肥、Dose、剂量、施多少肥、肥力、综合肥力、秸秆、有机肥、培肥

#### Scenario: 输入越界时返回拒绝响应
- **WHEN** `FertilityMLAgent.execute` 收到包含越界特征值的输入，`model_6_execution` 返回 `status: "rejected"`
- **THEN** Agent SHALL 在 `answer` 中明文标注越界特征和合法范围（如"输入值异常，无法预测。越界特征：pH=99.0（合法范围 3.0-11.0）"），不返回预测值，`evidence` 为空列表

## REMOVED Requirements

### Requirement: ComprehensiveImprovementAgent 智能体
**Reason**: 原 `ComprehensiveImprovementAgent`（model-6）是占位用的综合编排器，仅基于规则拼接 model-4/model-5 的结论生成"分区分类提升建议"，并非用户原始设想中的"计算模型"。本次变更将其替换为 `FertilityMLAgent`，让 model-6 真正具备基于真实训练数据的 ML 预测能力。

**Migration**:
- `framework/agents/specialized/comprehensive_agent.py` 文件将被删除
- `framework/agents/specialized/__init__.py` 移除 `ComprehensiveImprovementAgent` 导出，新增 `FertilityMLAgent` 导出
- `framework/agents/manager.py` 的 `_load_real_agents` 中 model-6 加载逻辑由 `ComprehensiveImprovementAgent()` 改为 `FertilityMLAgent()`
- `framework/agents/manager.py` 中 `self.agents["model-6"].dependencies` 由 `["model-4", "model-5"]` 改为 `[]`
- `tests/test_agent_specialized.py` 与 `tests/test_agent_manager.py` 中 model-6 相关测试用例同步更新为 `FertilityMLAgent` 的 ML 预测断言
- 原由 `ComprehensiveImprovementAgent.answer_question` 处理的"综合诊断"类问题，由 `FertilityMLAgent.answer_question` 接管，回答内容从"综合分区建议"变为"SOC + Dose 预测值"
