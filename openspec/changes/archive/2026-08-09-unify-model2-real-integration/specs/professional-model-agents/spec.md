## MODIFIED Requirements

### Requirement: 专业智能体目录与正式能力一一对应

系统 SHALL 以 6 个已注册专业智能体作为正式专业能力的唯一来源。每个 Agent SHALL 有一个稳定内部 `agent_id`、一个规范公开 `model_id`、明确中文名称、业务边界、最小输入、数据前提、可靠性状态和降级方式。正式能力为：`model-1/stability-risk-evaluation`、`model-2/improvement-potential-assessment`、`model-3/obstacle-diagnosis`、`model-4/acidification-remediation`、`model-5/organic-matter-improvement`、`model-6/fertility-soc-dose-prediction`。`model-2` SHALL 提供耕地质量综合指数、质量等级、障碍度、单地块提升潜力和县域潜力情景的真实计算能力；`model-7/quality-grade-evaluation` SHALL NOT 再作为独立正式能力出现。

#### Scenario: 读取正式专业能力目录
- **WHEN** 系统初始化专业能力目录
- **THEN** 目录 SHALL 包含且仅包含 6 项正式专业能力
- **AND** 每一项 SHALL 同时给出 Agent ID、公开模型 ID、名称和运行前提
- **AND** 目录 SHALL NOT 包含独立的 `model-7` 或 `quality-grade-evaluation` 项

#### Scenario: Agent 注册引用正式能力定义
- **WHEN** `AgentManager` 注册专业智能体
- **THEN** 每个已注册 Agent SHALL 引用统一能力定义
- **AND** SHALL NOT 在 Manager 内重复维护与能力目录冲突的名称或模型标识
- **AND** 注册表 SHALL 仅包含 6 个正式 Agent

#### Scenario: 模型2使用真实地块数据完成评价和潜力计算
- **WHEN** 调用 `model-2` 并提供已部署数据中的 `parcel_code`
- **THEN** 系统 SHALL 返回基于该地块实际指标计算的质量等级、综合指数和障碍度
- **AND** 当请求为潜力评估时 SHALL 返回逐项改良与全改良后的潜力结果
- **AND** 结果 SHALL 标记真实数据来源与 `simulated: false`

#### Scenario: 模型2缺少真实计算所需输入
- **WHEN** 调用 `model-2` 但未提供可识别的 `parcel_code` 或完整结构化指标
- **THEN** 系统 SHALL 返回 `status: "error"` 和 `error.code: "MISSING_PARCEL_CODE"`
- **AND** SHALL NOT 将固定演示指标作为真实地块计算结果返回

#### Scenario: 旧 model-7 标识被彻底移除
- **WHEN** 调用方使用历史 `model-7` 或 `quality-grade-evaluation` 标识请求能力目录或单模型接口
- **THEN** 系统 SHALL NOT 将其解析、映射或迁移到 `model-2`
- **AND** 系统 SHALL 返回未知模型或不支持模型的结构化结果
