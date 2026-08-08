# agent-base-framework Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
### Requirement: BaseAgent 抽象基类

系统 SHALL 提供 `BaseAgent.analyze(payload)`、`execute(task)` 和 `answer_question(question, context)` 接口。`analyze(payload)` SHALL 是专业计算的结构化入口；`answer_question()` SHALL 复用分析结果生成面向用户的答复，而不是维护独立计算路径。

#### Scenario: 执行结构化专业分析
- **WHEN** 调用方传入满足能力要求的结构化 payload
- **THEN** `analyze(payload)` SHALL 返回包含能力标识、发现、建议、证据、可靠性和降级状态的结构化结果

#### Scenario: 从问答复用专业分析
- **WHEN** Agent 响应用户专业问题
- **THEN** Agent SHALL 基于 `analyze(payload)` 的结果生成答复
- **AND** 其证据和可靠性说明 SHALL 与结构化结果一致

### Requirement: AgentManager 中心化编排器

系统 SHALL 由统一专业能力目录注册 6 个正式 Agent，而不是在 `AgentManager` 内重复定义名称、模型标识和路由相关元数据。`model-2` 同时承接 type 5 和 type 6。

#### Scenario: 初始化 AgentManager
- **WHEN** 系统初始化 `AgentManager`
- **THEN** 系统 SHALL 注册统一目录中定义的 6 个正式 Agent
- **AND** 每个 Agent SHALL 保持与公开专业模型相同的能力标识

### Requirement: 模拟数据层
系统 SHALL 为尚未接入真实算法的智能体提供模拟数据层，包括模拟输入数据、模拟计算逻辑和模拟输出结果；已接入真实算法的智能体不得用模拟成功结果替代真实计算。

#### Scenario: 模拟数据加载
- **WHEN** 智能体初始化时
- **THEN** 智能体 SHALL 加载内置的模拟数据集，包含领域相关的输入参数和参考阈值

#### Scenario: 模拟计算执行
- **WHEN** 智能体执行计算任务
- **THEN** 智能体 SHALL 基于阈值规则对模拟数据进行计算，并返回带有 `simulated` 标记的结果
