## 新增需求

### 需求: model-5 Agent 返回真实 ML 来源

`OrganicMatterAgent` 必须在提供可用结构化输入时调用 `model_5_execution`，返回实际模型版本、区域、土地类型、置信度和可靠性状态。完整真实预测必须标记 `simulated=false`；使用均值填充、通用模型或规则降级时必须显式标记降级原因。

#### 场景: 韶关旱地 Agent 执行
- **当** Agent 收到 `area_code=lechang`、`land_type=upland` 及规范或外部土壤字段
- **那么** Agent 调用韶关旱地 RF，返回 `model_id=model-5`、`model_version=SG_RF_v2_20260804`、`simulated=false`

#### 场景: Agent 与单模型接口共用结果
- **当** 单模型 API 或聊天链路调用 model-5
- **那么** 两者都通过同一个 `analyze(payload)` 结果生成响应，不得各自重新计算

#### 场景: 输入不足
- **当** 请求缺少模型无法推断的关键输入
- **那么** Agent 返回机器可读的 `need_input` 或 `fallback` 状态，并明确缺少字段，不得把模拟规则值标记为真实结果

## 修改需求

### Requirement: 专业智能体目录与正式能力一一对应

系统 SHALL 以 6 个已注册专业智能体作为正式专业能力的唯一来源。`model-5/organic-matter-improvement` SHALL 对应可调用真实肥力 ML 的有机质培肥 Agent；`model-6/placeholder` SHALL 继续保留为独立占位能力，且不得注册或调用韶关 RF 引擎。每个 Agent SHALL 有稳定 `agent_id`、规范公开 `model_id`、业务边界、最小输入、可靠性状态和降级方式。

#### Scenario: 读取正式能力目录
- **WHEN** 系统初始化专业能力目录
- **THEN** 目录 SHALL 包含且仅包含 6 项正式能力，其中 model-5 为有机质培肥、model-6 为占位符

#### Scenario: model-6 保持占位
- **WHEN** AgentManager 注册 model-6
- **THEN** model-6 SHALL 仍由占位 Agent 提供，且不得加载 `model_5_execution` 或任何 RF 模型

### Requirement: OrganicMatterAgent 智能体

系统 SHALL 实现 `OrganicMatterAgent`，对应模型5「耕地土壤有机质培肥提升模型」，并通过 `model_5_execution` 计算 SOC 与 Dose。韶关区域按旱地/水田使用 SG RF；非韶关区域使用全局模型或明确降级。Agent 输出 SHALL 包含有机质培肥预测、施用量、模型版本、置信度、输入处理状态和实际/降级来源。

#### Scenario: 韶关 RF 施用量计算
- **WHEN** 用户提供韶关区域和土地类型，以及合法特征
- **THEN** Agent SHALL 返回对应 RF 的 Dose、SOC、置信度和模型版本，并标记 `simulated=false`

#### Scenario: 外部字段输入
- **WHEN** 用户提供 `SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX`
- **THEN** Agent SHALL 先适配为规范字段后执行，不得因字段名不同而把值当作缺失

#### Scenario: 模型不可用
- **WHEN** joblib 缺失、依赖缺失或输入越界
- **THEN** Agent SHALL 返回明确失败/降级状态、原因和下一步所需输入，不得伪造 RF 成功结果
