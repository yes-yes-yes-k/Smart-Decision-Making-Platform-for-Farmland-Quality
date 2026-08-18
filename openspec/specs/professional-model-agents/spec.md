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

系统 SHALL 为每个正式专业 Agent 提供 `analyze(payload)` 结构化分析入口。该入口 SHALL 返回 `status`、`capability`、`summary`、`findings`、`recommendations`、`evidence`、`lineage`、`reliability` 和 `fallback`，并包含成功、数据未就绪、输入不足、拒绝或降级时的机器可读状态。

#### Scenario: Agent 为单模型接口执行分析
- **WHEN** 单模型接口按公开模型 ID 调用正式能力
- **THEN** 对应 Agent SHALL 使用 `analyze(payload)` 返回结构化结果
- **AND** 结果 SHALL 标示实际数据来源、可靠性和降级状态

#### Scenario: Agent 为聊天链路复用分析
- **WHEN** 聊天链路路由到某个正式 Agent
- **THEN** Agent 的专业答复 SHALL 基于同一次 `analyze(payload)` 结果生成
- **AND** SHALL NOT 另行产生与单模型接口冲突的专业计算结论

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
