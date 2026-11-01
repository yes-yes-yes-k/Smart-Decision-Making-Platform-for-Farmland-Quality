# professional-model-agents Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.

## Requirements

### Requirement: 专业智能体目录与正式能力一一对应

系统 SHALL 以 6 个已注册专业智能体作为正式专业能力的唯一来源。每个 Agent SHALL 有一个稳定内部 `agent_id`、一个规范公开 `model_id`、明确中文名称、业务边界、最小输入、数据前提、可靠性状态和降级方式。正式能力为：`model-1/stability-risk-evaluation`（稳定性风险）、`model-2/quality-grade-evaluation`（质量等级）、`model-3/obstacle-diagnosis`（障碍诊断）、`model-4/acidification-remediation`（酸化改良）、`model-5/organic-matter-improvement`（有机质提升）、`model-6/comprehensive-fertility-improvement`（耕地综合地力改良提升模型，仍标记为占位状态）。

#### Scenario: 读取正式专业能力目录
- **WHEN** 系统初始化专业能力目录
- **THEN** 目录 SHALL 包含且仅包含 6 项正式专业能力
- **AND** 每一项 SHALL 同时给出 Agent ID、公开模型 ID、名称和运行前提

#### Scenario: Agent 注册引用正式能力定义
- **WHEN** `AgentManager` 注册专业智能体
- **THEN** 每个已注册 Agent SHALL 引用统一能力定义
- **AND** SHALL NOT 在 Manager 内重复维护与能力目录冲突的名称或模型标识

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

### Requirement: 专业 Agent 提供可复用的结构化分析

系统 SHALL 为每个正式专业 Agent 提供 `analyze(payload)` 结构化分析入口。该入口必须返回统一模型结果信封，包含 `model_id`、`status`、`subject`、`result`、`meta` 和 `issues`，并遵循 `thematic-model-output-contract` 对状态、问题、模型业务 Schema 和严格 JSON 的要求。`analyze(payload)` 返回的规范结果必须是单模型 API、聊天链路、LLM 上下文和审计投影的唯一业务事实来源。

#### Scenario: Agent 为单模型接口执行分析
- **WHEN** 单模型接口按公开模型 ID 调用正式能力
- **THEN** 对应 Agent 必须使用 `analyze(payload)` 返回规范模型结果
- **AND** 单模型接口必须从该结果生成 `public_full` 投影
- **AND** Agent 禁止额外构造与规范 `result` 冲突的业务结论

#### Scenario: Agent 为聊天链路复用分析
- **WHEN** 聊天链路路由到某个正式 Agent
- **THEN** Agent 的专业答复和模型精简结果必须基于同一次 `analyze(payload)` 结果生成
- **AND** 系统禁止从自然语言答复反向解析结构化结果
- **AND** 系统禁止在聊天详情中嵌入完整分析包的重复副本

#### Scenario: 不同运行路径规范化
- **WHEN** 同一专业 Agent 可从数据库、CSV、SQLite、预计算、ML 或规则路径获得结果
- **THEN** Agent 必须在 `analyze(payload)` 边界将所有路径适配到同一模型业务 Schema
- **AND** 数据来源和模拟状态必须记录在 `meta` 中

#### Scenario: 专业能力目录独立查询
- **WHEN** 调用方需要模型名称、用途、能力边界或运行前提
- **THEN** 系统必须通过专业能力目录提供这些描述
- **AND** 每次模型执行结果禁止重复返回内容相同的 `model` 和 `capability`

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ObstacleDiagnosisAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。`execute()` 方法 SHALL 在 `FARMland_DIAGNOSIS_AVAILABLE=True` 且提供 `parcel_id` 时调用 `_get_real_diagnosis()` 复用已有方法获取真实诊断结果；模型不可用或缺少 `parcel_id` 时 SHALL 返回统一降级响应（`status: "degraded"`, `degraded: True`, `reason`, `message`），不得返回硬编码 mock 数据。

**模型输入**（来源：xlsx 总览表）：
- 一级农业区、二级农业区、土壤pH、有机质、pH、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、地块唯一编码、地块经纬度、地块边界、行政区划边界、农田类型（水田/旱地）

**模型输出**（来源：xlsx 总览表）：
- 主要障碍因素、次要障碍因素、pH障碍等级、有机质障碍等级、有效磷障碍等级、速效钾障碍等级、容重障碍等级、耕层质地障碍等级、灌溉能力障碍等级、排水能力障碍等级、地形部位障碍等级、质地构型障碍等级、障碍因素组合

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

#### Scenario: 真实诊断执行
- **WHEN** `execute()` 被调用且 `FARMland_DIAGNOSIS_AVAILABLE=True` 且 `parcel_id` 已提供
- **THEN** 智能体 SHALL 调用 `_get_real_diagnosis()` 复用已有方法获取真实诊断结果
- **AND** 返回结果中 `simulated` SHALL 为 `False` 或不设置

#### Scenario: 统一降级响应
- **WHEN** `execute()` 被调用但 `FARMland_DIAGNOSIS_AVAILABLE=False` 或未提供 `parcel_id`
- **THEN** 智能体 SHALL 返回统一降级响应：`status: "degraded"`, `degraded: True`, `reason: "model_unavailable" | "missing_input"`, `message: <说明>`
- **AND** SHALL NOT 返回硬编码 mock 数据

### Requirement: AcidificationRemediationAgent 智能体
系统 SHALL 实现 `AcidificationRemediationAgent` 智能体，对应模型4「耕地土壤酸化改良模型」，负责判定酸化程度并计算调理剂施用量。`execute()` 方法 SHALL 调用 `model_4_execution()` 进行真实计算，且 SHALL NOT 在顶层添加误导性的 `simulated: True` 标记。

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

#### Scenario: 真实计算标记
- **WHEN** `execute()` 调用 `model_4_execution()` 成功返回
- **THEN** 返回结果中 `simulated` SHALL 为 `False`
- **AND** SHALL NOT 使用 `MockDataLoader.mark_simulated()` 包装真实计算结果

### Requirement: OrganicMatterAgent 智能体
系统 SHALL 实现 `OrganicMatterAgent` 智能体，对应模型5「耕地土壤有机质培肥提升模型」，通过 `model_5_execution` 提供 SOC 与 Dose 机器学习预测；韶关区域按旱地/水田选择 RF，非韶关使用全局 ETR 或明确降级。

**模型输入**（来源：xlsx 总览表）：
- 土壤pH、有机质、有效磷、速效钾、总氮、阳离子交换量、土壤黏粒、交换性氢离子、交换性铝离子、游离铁、总铁、全氮、全磷、全钾、游离氧化铁、土壤容重、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标土壤有机质

**模型输出**：
- `model_id=model-5`、SOC 预测、Dose 预测、置信度、实际 `model_version`、`simulated`、`fallback` 和输入处理状态

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

#### Scenario: 韶关 RF 预测
- **WHEN** Agent 收到 `area_code=lechang`、`land_type` 和规范或外部土壤字段
- **THEN** SHALL 调用 `model_5_execution` 对应的韶关 RF，返回 `model_id=model-5`、`model_version=SG_RF_v2_20260804` 和 `simulated=false`

#### Scenario: 输入不足或模型不可用
- **WHEN** 关键特征缺失、字段冲突、输入越界或 joblib/依赖不可用
- **THEN** SHALL 返回机器可读的 `need_input`、`input_conflict`、`input_out_of_range` 或 `fallback_reason`，不得把规则结果标记为真实 RF

### Requirement: FarmlandGradeObstacleAgent 智能体
系统 SHALL 实现 `FarmlandGradeObstacleAgent` 智能体，对应模型2「耕地质量等级评价模型」（纯 Python 实现），通过调用 `run_grade_evaluation` 获取地块评价结果，返回基于 GB/T 33469-2016 标准的真实质量等级和障碍度诊断。模型不可用或缺少 `parcel_code` 时 SHALL 返回统一降级响应（`status: "degraded"`, `degraded: True`, `reason`, `message`），不得返回硬编码 mock 数据。

#### Scenario: 质量等级查询
- **WHEN** 用户询问某地块的耕地质量等级，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 调用 `run_grade_evaluation`（Python 实现），返回质量等级（1-10等）、综合指数和 12 项指标的原始值

#### Scenario: 障碍度诊断
- **WHEN** 用户询问某地块的主要障碍因素，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 调用 `run_grade_evaluation`（Python 实现），返回障碍度因子排序表（从大到小），识别主要限制因子

#### Scenario: 评价调用失败
- **WHEN** Python 评价调用失败（CSV 数据缺失、地块代码无效、编码字段越界）
- **THEN** 智能体 SHALL 返回明确的错误信息（如"CSV 数据文件缺失"、"未找到地块代码"），`confidence` 字段降低，不返回模拟数据

#### Scenario: 统一降级响应
- **WHEN** `execute()` 被调用但 `GRADE_EVAL_AVAILABLE=False` 或未提供 `parcel_code`
- **THEN** 智能体 SHALL 返回统一降级响应：`status: "degraded"`, `degraded: True`, `reason: "model_unavailable" | "missing_input"`, `message: <说明>`
- **AND** SHALL NOT 返回硬编码 mock 数据

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
系统 SHALL 实现 `AcidificationImprovementAgent` 智能体，对应模型4「耕地土壤酸化改良模型」，通过调用模型4 的在线查询接口获取酸化程度分区和改良方案，返回真实的酸化程度、调理剂施用量建议和改良措施。

#### Scenario: 酸化程度查询
- **WHEN** 用户询问某地块的酸化程度，且模型4 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 返回酸化程度（无明显酸化/轻度/中度/重度）、酸化方向（酸化/碱化）和 pH 值

#### Scenario: 改良方案查询
- **WHEN** 用户询问某地块的酸化改良方案，且该地块被判定为中度或重度酸化
- **THEN** 智能体 SHALL 返回调理剂施用量建议（如石灰施用量 kg/亩）和改良措施（如施肥方式、轮作制度调整）

#### Scenario: 轻度或无酸化
- **WHEN** 用户询问某地块的酸化改良方案，但该地块为轻度酸化或无明显酸化
- **THEN** 智能体 SHALL 返回"无需特殊改良"的提示，建议常规监测和维护

### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量稳定性与退化风险评价模型」，基于预计算结果识别稳定性、历史变化和退化风险。当 `STABILITY_MODEL_AVAILABLE=True` 且提供 `parcel_id` 时 SHALL 调用 `StabilityStorage` 获取真实结果；不可用时 SHALL 返回统一降级响应（`status: "degraded"`, `degraded: True`, `reason`, `message`），不得返回硬编码 mock 数据。

#### Scenario: 稳定性评价查询
- **WHEN** 用户询问某地块的稳定性评价结果，且预计算数据已就绪
- **THEN** 智能体 SHALL 返回九模块综合评价结果，包括等级边界安全度、指标支撑均衡度等

#### Scenario: 退化风险评估
- **WHEN** 用户询问某地块的退化风险
- **THEN** 智能体 SHALL 返回掉级风险、关键因子退化风险等评估结果

#### Scenario: 预计算数据未就绪
- **WHEN** 用户询问稳定性相关问题，但预计算数据未就绪
- **THEN** 智能体 SHALL 返回"数据未就绪"提示，不返回模拟数据

#### Scenario: 统一降级响应
- **WHEN** `execute()` 被调用但 `STABILITY_MODEL_AVAILABLE=False` 或未提供 `parcel_id`
- **THEN** 智能体 SHALL 返回统一降级响应：`status: "degraded"`, `degraded: True`, `reason: "model_unavailable" | "missing_input"`, `message: <说明>`
- **AND** SHALL NOT 返回硬编码 mock 数据

### Requirement: 专题模型优先从数据库 parcel_info 表读取地块指标

所有专题模型 Agent（Model-1 到 Model-5）的 `_collect_inputs` SHALL 优先按 `parcel_id` 从 PostgreSQL `parcel_info` 表查询 `soil_indicators` JSON 字段获取地块指标数据。当 `parcel_info` 表中存在该 `parcel_id` 记录时，Agent SHALL 使用 DB 中的指标数据作为模型输入。当 DB 查询失败或 `parcel_id` 不存在时，Agent SHALL 降级到现有数据源（Model-1 的 MOCK_COUNTIES、Model-2 的 CSV、Model-3/4 的 SQLite、Model-5 的用户传入参数），并记录 WARNING 级别日志标明降级原因。降级响应 SHALL 包含 `data_source: "fallback"` 标识，DB 命中时 SHALL 包含 `data_source: "db"` 标识。

#### Scenario: DB 命中时使用 DB 地块指标
- **WHEN** Agent 的 `_collect_inputs` 被调用且 `parcel_id` 在 `parcel_info` 表中存在
- **THEN** Agent SHALL 从 `soil_indicators` JSON 字段解析土壤指标（soil_ph、organic_matter、available_potassium 等）作为模型输入
- **AND** 返回结果 SHALL 包含 `data_source: "db"` 标识

#### Scenario: DB 未命中时降级到现有数据源
- **WHEN** Agent 的 `_collect_inputs` 被调用且 `parcel_id` 在 `parcel_info` 表中不存在，或 DB 连接失败
- **THEN** Agent SHALL 降级到现有数据源（SQLite/CSV/MOCK_COUNTIES/用户传入参数）
- **AND** SHALL 记录 WARNING 日志标明降级原因（parcel_id_not_found 或 db_unavailable）
- **AND** 返回结果 SHALL 包含 `data_source: "fallback"` 标识

#### Scenario: Model-1 移除硬编码 MOCK_COUNTIES 优先路径
- **WHEN** StabilityRiskAgent 的 `_collect_inputs` 被调用且提供了 `parcel_id`
- **THEN** Agent SHALL 优先查询 `parcel_info` 表获取稳定性相关指标
- **AND** 仅在 DB 未命中时才使用 `MOCK_COUNTIES` 硬编码数据作为 fallback

#### Scenario: SoilDataLoader 接入生产代码
- **WHEN** 任意专题模型 Agent 需要从 DB 读取地块指标
- **THEN** SHALL 通过 `SoilDataLoader` 或等价的数据访问层统一查询 `parcel_info` 表
- **AND** SHALL NOT 在 Agent 中直接编写裸 SQL 查询

### Requirement: 专题模型结果同步持久化到 V3.0 结果表

每个专题模型 Agent 在计算成功后 SHALL 同步将结果写入对应的 V3.0 结果表和 `model_execution_log` 表。`model_execution_log` SHALL 记录 `agent_id`、`parcel_id`（县级分析除外）、`status`、`input_snapshot`（JSON 快照）、`output_snapshot`（JSON 快照）、`started_at` 和 `completed_at`。结果表 SHALL 通过 `execution_id` 外键关联 `model_execution_log.id`。DB 写入失败时 Agent SHALL 记录 ERROR 日志，但 SHALL NOT 阻断返回给用户的计算结果。`model_execution_log.status` SHALL 在计算成功时为 `ok`，计算失败时为 `error`，降级时为 `degraded`。

结果表映射：
- Model-1 → `stability_risk_result`
- Model-2 → `quality_grade_result`
- Model-3 → `obstacle_diagnosis_result`
- Model-4 → `acidification_remediation_result`
- Model-5 → `organic_matter_result`（县级分析，无 `parcel_id`）

#### Scenario: 计算成功后同步写入结果表和执行日志
- **WHEN** 专题模型 Agent 计算成功返回结果
- **THEN** Agent SHALL 先写入 `model_execution_log` 记录（`status: "ok"`，含输入/输出快照和时间戳）
- **AND** SHALL 通过 `execution_id` 外键写入对应结果表
- **AND** SHALL 在持久化完成后才返回结果给调用方

#### Scenario: DB 持久化失败不影响用户结果
- **WHEN** 专题模型 Agent 计算成功但 DB 写入结果表或 `model_execution_log` 失败
- **THEN** Agent SHALL 记录 ERROR 日志标明持久化失败原因
- **AND** SHALL NOT 抛出异常或阻断返回给用户的计算结果
- **AND** 返回结果 SHALL 包含 `persisted: false` 标识

#### Scenario: 降级计算时的执行日志记录
- **WHEN** 专题模型 Agent 因 DB 未命中而降级到 fallback 数据源完成计算
- **THEN** `model_execution_log.status` SHALL 为 `degraded`
- **AND** `input_snapshot` SHALL 记录实际使用的数据源标识（`data_source: "fallback"`）

#### Scenario: 计算失败时的执行日志记录
- **WHEN** 专题模型 Agent 计算失败
- **THEN** Agent SHALL 写入 `model_execution_log` 记录（`status: "error"`，含错误信息）
- **AND** SHALL NOT 写入结果表

### Requirement: 统一 soil_indicators 键名映射

系统 SHALL 在 ParcelDataAccessor 中实现 V3.0 英文 snake_case 字段名到各模型计算所需输入参数的统一映射。映射表覆盖全部 5 个模型的输入字段。

#### Scenario: Model-2/3 映射
- **WHEN** Agent 为 model-2 或 model-3
- **THEN** soil_ph→SJD, organic_matter→YJZ, available_phosphorus→YXL, available_potassium→SXJ, bulk_density→TRRZ, topsoil_thickness→YXTCHD, plow_layer_thickness→GCHD 等映射生效

#### Scenario: Model-4 映射
- **WHEN** Agent 为 model-4
- **THEN** soil_ph→SJD, exchangeable_hydrogen→Hex, exchangeable_aluminum→Alex 映射生效

#### Scenario: Model-5 映射
- **WHEN** Agent 为 model-5
- **THEN** soil_ph→pH, organic_matter→SOMbe, available_potassium→AK, available_phosphorus→AP, total_nitrogen→TN 映射生效

### Requirement: 离散指标英文/中文值转代码

系统 SHALL 将 soil_indicators 中的离散指标值转换为模型计算所需的代码。DB 实际存储英文值（如 "loam"、"dry"、"lower"），也可能存储中文值（如「壤土」、「充分满足」）。系统先查 `DISCRETE_EN_MAP`（英文→代码），未命中再查 `DISCRETE_CN_MAP`（中文→代码）。

#### Scenario: 英文质地映射
- **WHEN** soil_texture 值为 "loam"
- **THEN** 转换为代码 RT，用于隶属度查找

#### Scenario: 英文灌溉映射
- **WHEN** irrigation_condition 值为 "dry"
- **THEN** 转换为代码 US（GGNL）/ BM（PSNL）

#### Scenario: 中文值回退
- **WHEN** soil_texture 值为「壤土」（英文映射未命中）
- **THEN** 通过 DISCRETE_CN_MAP 转换为代码 RT

#### Scenario: 未知值降级
- **WHEN** 离散值既不在英文映射也不在中文映射中
- **THEN** 返回 None，该指标隶属度降级为默认值 0.5

### Requirement: OrganicMatterAgent 规则路径只返回安全降级结果

`OrganicMatterAgent` 的 `execute`、`analyze` 和自然语言答复 MUST 对相同输入使用一致的安全降级语义。缺少真实模型结果时，Agent 禁止暴露固定规则施用量、提升量、默认县域均值或其他无依据定量结论。

#### Scenario: 直接调用 Agent 且缺少模型特征

- **WHEN** 内部调用方直接执行 `OrganicMatterAgent`，且数据库未命中、模型特征不足或模型不可用
- **THEN** Agent SHALL 返回统一 `degraded` 或 `unavailable` 结果
- **AND** `manure_dosage`、`potential_increase`、`dose` 和 `dose_prediction` MUST 为 `null` 或在规范响应中省略
- **AND** `issues` SHALL 包含稳定代码 `MODEL5_QUANTITATIVE_UNAVAILABLE`

#### Scenario: 自然语言答复使用规则降级

- **WHEN** `answer_question` 无法获得真实模型结果
- **THEN** 答复 MAY 说明需要补充的输入和可执行的核验步骤
- **AND** 答复 MUST NOT 声称县域平均有机质、推荐每亩施用量或预期提升量
- **AND** 证据列表 MUST NOT 包含由默认值或固定规则生成的数值

#### Scenario: 聊天入口地块未命中权威数据

- **WHEN** 聊天链路已经选择地块但该地块未命中权威 Model-5 输入数据
- **THEN** Agent SHALL 保持现有专业输入守卫并拒绝执行规则处方
- **AND** 系统 MUST NOT 因兼容直接调用路径存在而绕过该守卫

#### Scenario: 真实模型结果不受影响

- **WHEN** Model-5 使用可验证输入和已部署模型成功执行
- **THEN** Agent SHALL 继续返回真实 SOC/Dose 预测、置信度、模型版本和数据来源
- **AND** 结果 SHALL 标记 `simulated=false`

### Requirement: 生产聊天禁止无合法对象的地块级具体数值

通过生产聊天链路调用 Model-1 至 Model-5 时，每个专业 Agent SHALL 只接受编排器传入的已验证分析上下文或已通过完整性校验的 scenario 输入。要求地块对象的能力在缺少合法 parcel 对象时 SHALL NOT 使用 MOCK、默认指标、任意县内地块或历史请求残留生成具体结果。

#### Scenario: 酸化问题缺少地块

- **WHEN** 生产聊天中的酸化问题要求地块级用量，但当前无合法 parcel 对象且未选择 scenario 模式
- **THEN** AcidificationRemediationAgent SHALL NOT 使用 `MOCK_INPUTS` 计算 YTK、MBNT、pH 或其他具体数值
- **AND** 请求 SHALL 在进入 Agent 前被守卫转换为 `needs_analysis_object`

#### Scenario: 地块查询失败

- **WHEN** 已提交 parcel 对象但 `parcel_info` 查询失败或验证依赖不可用
- **THEN** 专业 Agent SHALL NOT 将该状态降级为用户输入、CSV、SQLite 或 MOCK 地块结果
- **AND** 系统 SHALL 返回与失败原因对应的对象或服务错误

#### Scenario: 合法情景试算

- **WHEN** 能力支持 scenario 且用户提供全部必需输入
- **THEN** Agent SHALL 使用实际提供的输入执行
- **AND** 输出 SHALL 标记为情景试算而非地块真实结果

### Requirement: 专业能力声明空间对象要求

每个正式专业能力 SHALL 在统一能力目录中声明 `supported_object_types`、`requires_spatial_object`、`supports_scenario` 和 `required_scenario_inputs`。聊天守卫与单模型入口的输入校验 SHALL 复用这些声明。

#### Scenario: 地块模型能力元数据

- **WHEN** 系统读取一个仅支持地块计算的能力
- **THEN** 其 `supported_object_types` SHALL 包含 `parcel`
- **AND** `requires_spatial_object` SHALL 为 true

#### Scenario: 县域统计能力元数据

- **WHEN** 能力支持县域聚合统计
- **THEN** 其 `supported_object_types` SHALL 明确包含 `county`
- **AND** 守卫 SHALL NOT 错误要求 parcel

### Requirement: 专业结果提供实际数据与模型时间信息

专业 Agent 的结构化分析结果 SHALL 提供实际 `model_version`、`data_as_of` 或 `data_version` 以及本次实际关键输入，供统一溯源构建器使用。未知值 SHALL 明确为 null 或 unknown，不得编造时间和版本。

#### Scenario: 地块历史数据计算

- **WHEN** 模型使用某调查年度的地块历史快照
- **THEN** 结构化结果 SHALL 将该调查年度作为 `data_as_of`

#### Scenario: 模型版本不可获得

- **WHEN** Agent 无法确定实际模型版本
- **THEN** SHALL 返回 `model_version=unknown`
- **AND** SHALL NOT使用能力目录版本冒充实际运行版本
