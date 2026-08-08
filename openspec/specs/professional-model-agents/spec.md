# professional-model-agents Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
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

### Requirement: 专业 Agent 提供可复用的结构化分析

系统 SHALL 为每个正式专业 Agent 提供 `analyze(payload)` 结构化分析入口。该入口 SHALL 返回 `status`、`capability`、`summary`、`findings`、`recommendations`、`evidence`、`lineage`、`reliability` 和 `fallback`，并包含成功、数据未就绪、输入不足、拒绝或降级时的机器可读状态。

#### Scenario: Agent 为单模型接口执行分析
- **WHEN** 单模型接口按公开模型 ID 调用正式能力
- **THEN** 对应 Agent SHALL 使用 `analyze(payload)` 返回结构化结果
- **AND** 结果 SHALL 标示实际数据来源、可靠性和降级状态

#### Scenario: Agent 为聊天链路复用分析
- **WHEN** 聊天链路路由到某个正式 Agent
- **THEN** Agent 的专业答复 SHALL 基于同一次 `analyze(payload)` 结果生成
- **AND** SHALL NOT 另行产生与单模型接口冲突的专业计算结论

### Requirement: 肥力预测与有机质培肥边界明确

系统 SHALL 将 `model-6` 限定为 SOC/Dose 等肥力预测能力，将 `model-5` 限定为有机肥、秸秆还田和培肥措施等治理建议能力。两项能力 SHALL 在名称、输入、输出、路由关键词和可靠性说明上可区分。

#### Scenario: 查询 SOC 或 Dose 预测
- **WHEN** 用户请求 SOC、有机碳、Dose、施肥量预测或预测置信度
- **THEN** 系统 SHALL 使用 `model-6/fertility-soc-dose-prediction`
- **AND** 返回预测值、模型可用性和置信度/降级说明

#### Scenario: 农户地块诊断
- **WHEN** 农户询问"我这块地到底有啥毛病？"
- **THEN** 智能体 SHALL 给出地块耕地质量等级和诊断结论，重点标出地块的主要障碍因子，同时配上示意图

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ProblemIdentificationAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。

**模型输入**（来源：xlsx 总览表）：
- 一级农业区、二级农业区、土壤pH、有机质、pH、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、地块唯一编码、地块经纬度、地块边界、行政区划边界、农田类型（水田/旱地）

**模型输出**（来源：xlsx 总览表）：
- 主要障碍因素、次要障碍因素、pH障碍等级、有机质障碍等级、有效磷障碍等级、速效钾障碍等级、容重障碍等级、耕层质地障碍等级、灌溉能力障碍等级、排水能力障碍等级、地形部位障碍等级、质地构型障碍等级、有效土层障碍等级、障碍因素组合

#### Scenario: 障碍因素识别
- **WHEN** 用户询问"全省耕地质量存在哪些问题？"
- **THEN** 智能体 SHALL 返回全省/市范围内的主要障碍因素、次要障碍因素和障碍组合统计

#### Scenario: 指标障碍等级统计
- **WHEN** 智能体接收到地块指标数据
- **THEN** 智能体 SHALL 输出每个指标的障碍等级（1~10级频数统计），最后一列为该指标是否主要、次要障碍因素

#### Scenario: 县域障碍诊断
- **WHEN** 县域执行端用户询问"县/乡镇里的耕地在哪些方面有问题"
- **THEN** 智能体 SHALL 统计全区域内的信息，每个指标为一行，列为每个指标1~10等级的频数统计，最后一列为是否主要、次要障碍因素

#### Scenario: 农户地块问题
- **WHEN** 农户询问"我这块地有没有问题？"
- **THEN** 智能体 SHALL 用简单语言说明耕地质量等级、列举低等级的指标

### Requirement: AcidificationRemediationAgent 智能体
系统 SHALL 实现 `AcidificationRemediationAgent` 智能体，对应模型4「耕地土壤酸化改良模型」，负责判定酸化程度并计算调理剂施用量。

**模型输入**（来源：xlsx 总览表）：
- 土壤pH、有机质、阳离子交换量、土壤黏粒、总氮、游离铁、总铁、交换性氢离子、交换性铝离子、全氮、全磷、全钾、游离氧化铁、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标pH（或pH增加值）

**模型输出**（来源：xlsx 总览表）：
- 土壤酸化程度级别、土壤本底酸量、农业活动产酸量、碱性调理剂施用量、木本泥炭施用量

#### Scenario: 酸化程度判定
- **WHEN** 用户询问"查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？"
- **THEN** 智能体 SHALL 按 GB/T 42817-2023 标准（酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5）输出酸化等级和比例

#### Scenario: 调理剂施用量计算
- **WHEN** 农户询问"我的田酸化了，pH是XX，我要施加多少碱性调理剂可以治理好？"
- **THEN** 智能体 SHALL 输出使土壤pH从当前值提升到6.5目标值的碱性调理剂建议施用量，结合 GB/T 42817-2023 和 NY/T 443-2019 标准

#### Scenario: 不同土地利用类型酸化
- **WHEN** 用户询问"查询区域内不同土地利用类型的酸化程度"
- **THEN** 智能体 SHALL 输出旱地、水田、园地、林地等不同土地利用类型土壤的酸化等级及比例

#### Scenario: 农户酸化判断
- **WHEN** 农户询问"我的这块田酸化严重吗？"
- **THEN** 智能体 SHALL 输出该地块土壤酸化等级

### Requirement: OrganicMatterAgent 智能体
系统 SHALL 实现 `OrganicMatterAgent` 智能体，对应模型5「耕地土壤有机质培肥提升模型」，负责有机质提升评估和有机肥施用量计算。

**模型输入**（来源：xlsx 总览表）：
- 土壤pH、有机质、有效磷、速效钾、总氮、阳离子交换量、土壤黏粒、交换性氢离子、交换性铝离子、游离铁、总铁、全氮、全磷、全钾、游离氧化铁、土壤容重、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标土壤有机质

**模型输出**（来源：xlsx 总览表）：
- 有机肥/秸秆、有机肥施用量、秸秆施用量

#### Scenario: 有机质含量评估
- **WHEN** 用户询问"全省耕地土壤有机质含量如何，空间分布情况？"
- **THEN** 智能体 SHALL 返回总体水平（平均含量及高、中、低等级占比）和空间分布（哪些区域较高、较低，是否呈现地形梯度）

#### Scenario: 有机肥施用量计算
- **WHEN** 农户询问"为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？"
- **THEN** 智能体 SHALL 分别输出有机肥和秸秆还田的每亩施用量

#### Scenario: 有机质低值区域识别
- **WHEN** 县域执行端用户询问"本县耕地土壤有机质平均含量是多少？"
- **THEN** 智能体 SHALL 说明本县耕地土壤有机质平均含量及高、中、低等级占比，识别出土壤有机质低的区域并给出明确数值

#### Scenario: 有机质低值原因
- **WHEN** 用户询问"耕地有机质含量低的原因是什么？"
- **THEN** 智能体 SHALL 从土壤类型、气候、地形、耕作制度、秸秆还田和施肥管理等方面解释差异，指出低有机质区域及后续培肥重点

### Requirement: FertilityMLAgent 智能体
系统 SHALL 实现 `FertilityMLAgent` 智能体，对应模型6「耕地综合地力改良提升模型」，负责综合多个模型结果形成分区分类的综合提升建议。该智能体内部使用预训练的 ExtraTreesRegressor 模型对 SOC 和 Dose 进行 ML 预测作为综合地力评估的计算单元，并通过 `framework/agents/manager.py` 注册为 `model-6`。

**模型输入**（来源：xlsx 总览表，xlsx 未填写，保留现有实现）：
- 综合上述模型1-5的输入指标，包括土壤理化指标、农田类型、目标有机质等

**模型输出**（来源：xlsx 总览表，xlsx 未填写，保留现有实现）：
- 综合提升建议（基于 SOC 预测和 Dose 预测的综合地力评估）

#### Scenario: 农户综合诊断
- **WHEN** 农户询问"我的田肥力怎么样？"
- **THEN** 智能体 SHALL 同时返回 SOC 和 Dose 两个预测值，并提供综合诊断说明（如"SOC 预测 X g/kg，建议施肥量约 Y kg/亩"）

#### Scenario: 农户 SOC 预测查询
- **WHEN** 农户询问"我的田土壤有机碳含量大概多少？"
- **THEN** 智能体 SHALL 调用 `model_6_execution` 返回 `soc_prediction`（g/kg）、`soc_confidence`（0.91）等结构化结果

#### Scenario: 农户 Dose 施用量预测查询
- **WHEN** 农户询问"我这块地大概需要施多少有机肥？"
- **THEN** 智能体 SHALL 调用 `model_6_execution` 返回 `dose_prediction`（kg/亩）、`dose_confidence`（0.47）、`dose_warning` 字段，并在回答中标注"预测结果仅供参考"

#### Scenario: 模型降级时的回退响应
- **WHEN** `model_6_execution` 返回 `status: "fallback"`（模型文件缺失或 sklearn 未安装）
- **THEN** 智能体 SHALL 在回答中标注"基于训练集均值的估算"而非"基于 ML 模型预测"，confidence 降为 0.3

#### Scenario: Agent 独立执行无依赖
- **WHEN** `AgentManager.process` 调用 farmer 角色对应的智能体集合
- **THEN** `model-6`（FertilityMLAgent）的 `dependencies` SHALL 为空列表 `[]`，可与其他模型并行执行

#### Scenario: 非肥力相关问题跳过 model-6
- **WHEN** 农户角色提出的问题不包含肥力相关关键词（如"我的田 pH 如何"），且 `AgentManager` 路由到 model-6
- **THEN** `AgentManager._should_execute_agent` SHALL 返回 False，model-6 不被执行

#### Scenario: 输入越界时返回拒绝响应
- **WHEN** `FertilityMLAgent.execute` 收到包含越界特征值的输入，`model_6_execution` 返回 `status: "rejected"`
- **THEN** Agent SHALL 在回答中明文标注越界特征和合法范围，不返回预测值

### Requirement: PotentialAssessmentAgent 真实质量与潜力评估
系统 SHALL 由 `model-2/PotentialAssessmentAgent` 调用 `farmland_grade_eval` 的纯 Python 引擎，统一提供质量等级、综合指数、障碍度、单地块提升潜力和县域潜力情景。该 Agent 不得使用固定模拟指标作为成功结果。

#### Scenario: 质量等级查询
- **WHEN** 用户以 type 5 询问某地块的耕地质量等级，且提供了合法的 `parcel_code`
- **THEN** `PotentialAssessmentAgent` SHALL 调用 `run_grade_evaluation`，返回质量等级、综合指数和 12 项指标的原始值

#### Scenario: 单地块与县域潜力评估
- **WHEN** 用户以 type 6 提供 `parcel_code`，或提供 `xqmc_code` 与 `scenario`
- **THEN** `PotentialAssessmentAgent` SHALL 分别调用 `run_potential_analysis` 或 `run_county_potential`，返回真实潜力结果

#### Scenario: 评价调用失败
- **WHEN** 缺少 `parcel_code`，或 Python 评价调用失败（CSV 数据缺失、地块代码无效、编码字段越界）
- **THEN** Agent SHALL 返回明确的机器可读错误（包括 `MISSING_PARCEL_CODE`、`DEPLOYMENT_ERROR` 或底层错误），且 `metadata.simulated` SHALL 为 `false`

### Requirement: ObstacleDiagnosisAgent 智能体
系统 SHALL 实现 `ObstacleDiagnosisAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，通过调用模型3 的在线查询接口获取障碍诊断结果，返回真实的障碍类型、主要/次要障碍因素和障碍组合类型。

#### Scenario: 障碍诊断查询
- **WHEN** 用户询问某地块的障碍诊断结果，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 调用模型3 在线查询接口，返回障碍类型（单一障碍/多障碍）、主要障碍因素、次要障碍因素和障碍度排序

#### Scenario: 障碍组合类型识别
- **WHEN** 用户询问某地块的障碍组合类型，且该地块存在多个中度以上障碍因素
- **THEN** 智能体 SHALL 返回障碍组合类型描述（如"酸化+有机质不足"、"养分失衡+耕层条件偏弱"）

#### Scenario: 诊断数据未就绪
- **WHEN** 用户询问障碍诊断相关问题，但模型3 批量评价和诊断结果未就绪
- **THEN** 智能体 SHALL 返回"模型3 数据未就绪，请先执行批量评价"的提示，不返回模拟数据

### Requirement: AcidificationImprovementAgent 智能体
系统 SHALL 实现 `AcidificationImprovementAgent` 智能体，对应模型3「耕地土壤酸化改良模型」，通过调用模型3 的在线查询接口获取酸化程度分区和改良方案，返回真实的酸化程度、调理剂施用量建议和改良措施。

#### Scenario: 酸化程度查询
- **WHEN** 用户询问某地块的酸化程度，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 返回酸化程度（无明显酸化/轻度/中度/重度）、酸化方向（酸化/碱化）和 pH 值

#### Scenario: 改良方案查询
- **WHEN** 用户询问某地块的酸化改良方案，且该地块被判定为中度或重度酸化
- **THEN** 智能体 SHALL 返回调理剂施用量建议（如石灰施用量 kg/亩）和改良措施（如施肥方式、轮作制度调整）

#### Scenario: 轻度或无酸化
- **WHEN** 用户询问某地块的酸化改良方案，但该地块为轻度酸化或无明显酸化
- **THEN** 智能体 SHALL 返回"无需特殊改良"的提示，建议常规监测和维护

### Requirement: 模型3 与模型1 整合诊断
系统 SHALL 在 agent 层实现模型3（障碍诊断）与模型1（退化风险）的整合，当用户请求综合诊断时，同时调用两个模型并整合结果。

#### Scenario: 综合诊断查询
- **WHEN** 用户询问某地块的综合诊断结果（同时涉及稳定性和障碍诊断），且两个模型的数据均已就绪
- **THEN** 系统 SHALL 同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，整合退化风险和障碍诊断结果，返回综合诊断报告

