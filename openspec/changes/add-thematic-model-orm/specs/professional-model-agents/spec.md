## MODIFIED Requirements

### Requirement: 专业智能体目录与正式能力一一对应

系统 SHALL 以 6 个已注册专业智能体作为正式专业能力的唯一来源。每个 Agent SHALL 有一个稳定内部 `agent_id`、一个规范公开 `model_id`、明确中文名称、业务边界、最小输入、数据前提、可靠性状态和降级方式。正式能力为：`model-1/stability-risk-evaluation`（稳定性风险）、`model-2/quality-grade-evaluation`（质量等级）、`model-3/obstacle-diagnosis`（障碍诊断）、`model-4/acidification-remediation`（酸化改良）、`model-5/organic-matter-improvement`（有机质提升）、`model-6/comprehensive-fertility-improvement`（耕地综合地力改良提升模型，仍标记为占位状态）。

#### Scenario: 读取正式专业能力目录
- **WHEN** 系统初始化专业能力目录
- **THEN** 目录 SHALL 包含且仅包含 6 项正式专业能力
- **AND** 每一项 SHALL 同时给出 Agent ID、公开模型 ID、名称和运行前提

#### Scenario: Model-6 元数据升级为综合地力改良提升模型
- **WHEN** `framework/agents/capabilities.py` 中 Model-6 的 `ProfessionalCapability` 被读取
- **THEN** Model-6 SHALL 将 `model_id` 从 `placeholder` 升级为 `comprehensive-fertility-improvement`
- **AND** Model-6 SHALL 将 `name` 从"占位模型"升级为"耕地综合地力改良提升模型"
- **AND** Model-6 SHALL 将 `domain` 从 `placeholder` 更新为 `fertility`
- **AND** Model-6 的 `runtime_requirement` SHALL 标注为占位状态（业务逻辑尚未实现）
- **AND** Model-6 SHALL 保持 `question_type` 为 6 不变

#### Scenario: Model-6 保持占位状态
- **WHEN** Model-6 能力被调用
- **THEN** 系统 SHALL 标注该模型为占位状态，业务逻辑尚未实现
- **AND** SHALL NOT 执行实际的综合地力改良提升计算
