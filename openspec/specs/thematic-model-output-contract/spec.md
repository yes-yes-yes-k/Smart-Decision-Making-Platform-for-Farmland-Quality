# thematic-model-output-contract Specification

## Purpose
TBD - created by archiving change optimize-thematic-model-output-contract. Update Purpose after archive.
## Requirements
### Requirement: 统一专题模型结果信封

系统必须为六个正式专题模型返回统一结果信封，且必须包含 `model_id`、`status`、`subject`、`result`、`meta` 和 `issues`。系统禁止在规范结果中返回与业务结果重复的 `model`、`capability`、`analysis`、通用 `evidence`、字符串化 `findings`、`reliability`、`fallback` 或 `degraded` 字段。

#### Scenario: 返回完整模型结果
- **WHEN** 任一正式专题模型完成规范化分析
- **THEN** 结果必须包含规范公开 `model_id` 和评价对象 `subject`
- **AND** 业务数据必须只出现在 `result` 中
- **AND** 运行元数据必须只出现在 `meta` 中
- **AND** 结果不得包含旧展示型重复字段

#### Scenario: 无法确定评价对象 ID
- **WHEN** 模型因输入不足无法确定地块或区域 ID
- **THEN** `subject` 必须仍然存在
- **AND** `subject.type` 必须为已知对象类型或 `unknown`
- **AND** `subject.id` 必须为 `null`

### Requirement: 统一模型状态和问题表达

模型 `status` 必须且只能为 `ok`、`degraded`、`rejected`、`unavailable` 或 `error`。`issues` 必须为数组，每项必须包含稳定的 `code`、`severity` 和 `message`，并可以包含 `field` 和不含敏感信息的 `details`。

#### Scenario: 完整成功
- **WHEN** 模型使用预期数据和运行依赖生成完整结果
- **THEN** `status` 必须为 `ok`
- **AND** `result` 必须为对象
- **AND** `issues` 必须为空数组或只包含不影响结果可用性的提示

#### Scenario: 部分结果或替代路径
- **WHEN** 模型使用默认值、替代数据源或只生成部分可用结果
- **THEN** `status` 必须为 `degraded`
- **AND** `result` 可以包含部分业务结果
- **AND** `issues` 必须至少包含一项解释降级原因的 warning

#### Scenario: 输入被拒绝
- **WHEN** 输入存在冲突、越界或不满足业务约束
- **THEN** `status` 必须为 `rejected`
- **AND** `result` 必须为 `null`
- **AND** `issues` 必须至少包含一项机器可读的输入问题

#### Scenario: 能力不可用
- **WHEN** 模型尚未实现、必要数据未就绪或运行依赖不可用且没有可靠降级结果
- **THEN** `status` 必须为 `unavailable`
- **AND** `result` 必须为 `null`
- **AND** `issues` 必须说明不可用原因

#### Scenario: 非预期执行失败
- **WHEN** 模型已尝试执行但发生非预期异常
- **THEN** `status` 必须为 `error`
- **AND** `result` 必须为 `null`
- **AND** 公共 `issues` 禁止包含堆栈、数据库凭证或内部路径等敏感信息

### Requirement: 统一运行元数据

`meta` 必须包含 `data_source`、`simulated` 和 `model_version`。数据来源差异必须通过 `meta.data_source` 表达，禁止通过改变同一模型 `result` 的结构表达 DB、CSV、SQLite、预计算、ML 或规则降级路径。

#### Scenario: 不同数据源返回同一业务结构
- **WHEN** 同一模型分别从数据库和文件路径获得等价业务结果
- **THEN** 两个响应的 `result` 字段集合必须遵守同一模型 Schema
- **AND** 两个响应必须通过不同的 `meta.data_source` 标识来源

#### Scenario: 模型版本未知
- **WHEN** 当前运行路径没有可识别的模型版本
- **THEN** `meta.model_version` 必须为 `null`
- **AND** 系统禁止伪造版本字符串

### Requirement: Model-1 稳定性风险结果 Schema

`stability-risk-evaluation` 的 `result` 必须使用 `region`、`score`、`grade` 和 `modules` 表达稳定性结果；`modules` 必须是九个模块结果的唯一容器，禁止同时返回与其内容相同的 `all_results`。

#### Scenario: 返回九模块稳定性结果
- **WHEN** Model-1 成功读取某地块的预计算稳定性结果
- **THEN** `result.modules` 必须包含可用的模块结果
- **AND** `result` 禁止包含 `module_1` 至 `module_9` 与 `all_results` 的重复副本

#### Scenario: 部分模块数据不足
- **WHEN** 九模块中部分模块因历史或邻域数据不足无法计算
- **THEN** `status` 必须为 `degraded`
- **AND** 对应模块值必须为 `null` 或包含明确的模块问题标识
- **AND** 其他可用模块必须继续返回

### Requirement: Model-2 质量等级结果 Schema

`quality-grade-evaluation` 的 `result` 必须使用 `quality_grade`、`composite_index`、`indicators` 和 `obstacle_degree` 表达质量等级评价，数据库与 CSV 路径必须返回相同字段语义。

#### Scenario: 数据库路径评价成功
- **WHEN** Model-2 从数据库完成质量等级评价
- **THEN** `result` 必须符合 Model-2 Schema
- **AND** `meta.data_source` 必须标识数据库来源

#### Scenario: CSV 路径评价成功
- **WHEN** Model-2 从 CSV 完成质量等级评价
- **THEN** `result` 必须与数据库路径使用相同字段语义
- **AND** `meta.data_source` 必须标识 CSV 来源

### Requirement: Model-3 障碍诊断结果 Schema

`obstacle-diagnosis` 的 `result` 必须使用 `obstacle_type`、`primary_factors`、`secondary_factors`、`obstacle_degrees`、`obstacle_levels` 和 `obstacle_combination` 表达诊断结果，禁止把 SQLite 路径的 `evaluation/diagnosis` 原始层级直接暴露为公共结构。

#### Scenario: 不同诊断路径返回一致结构
- **WHEN** Model-3 从数据库或旧 SQLite 路径完成诊断
- **THEN** 两条路径必须返回相同的 Model-3 业务字段
- **AND** 原始存储结构差异只能记录在内部审计数据中

### Requirement: Model-4 酸化改良结果 Schema

`acidification-remediation` 的 `result` 必须使用有明确业务含义的 snake_case 字段表达酸化水平、酸量和用量，禁止在公共结果中直接暴露 `Adep`、`Acrop`、`ANcy`、`Aagri`、`Aback`、`YTK` 或 `MBNT` 等来源相关缩写。

#### Scenario: 酸化计算成功
- **WHEN** Model-4 完成真实酸化改良计算
- **THEN** `result` 必须包含可用的 `acidification_level`、酸量字段、`soil_conditioner_dosage`、`woody_peat_dosage` 和 `sub_model`
- **AND** `meta.simulated` 必须为 `false`

#### Scenario: 旧路径返回缩写字段
- **WHEN** Model-4 底层实现返回来源相关缩写
- **THEN** Agent 适配器必须将其转换为规范字段
- **AND** 公共结果禁止同时保留缩写字段副本

### Requirement: Model-5 有机质提升结果 Schema

`organic-matter-improvement` 的 `result` 必须使用 `soc_prediction`、`dose_prediction`、`soc_confidence`、`dose_confidence`、`region`、`land_type` 和 `imputed_features` 表达预测结果。系统禁止返回与真实模型置信度无关的通用硬编码 `confidence`。

#### Scenario: ML 路径预测成功
- **WHEN** Model-5 使用已部署 ML 模型完成预测
- **THEN** `result` 必须返回 SOC 和 Dose 预测及各自置信度
- **AND** `meta.model_version` 必须返回实际模型版本
- **AND** `meta.simulated` 必须为 `false`

#### Scenario: 数据库快速路径只有 Dose
- **WHEN** 数据库路径只能提供 Dose 结果
- **THEN** 系统必须按完整 Model-5 Schema 返回
- **AND** 不可获得的 SOC 和置信度字段必须为 `null`
- **AND** `status` 必须为 `degraded`，`issues` 必须说明缺失内容

### Requirement: Model-6 未实现状态

`comprehensive-fertility-improvement` 在业务逻辑未实现期间必须返回 `status=unavailable` 和 `result=null`，禁止将桩结果包装为 `ok`。

#### Scenario: 调用未实现的 Model-6
- **WHEN** 调用方执行 Model-6
- **THEN** `status` 必须为 `unavailable`
- **AND** `meta.data_source` 必须标识占位实现
- **AND** `meta.simulated` 必须为 `true`
- **AND** `issues` 必须包含 `MODEL_NOT_IMPLEMENTED`

### Requirement: 严格 JSON 合规

所有公共模型响应必须是标准 JSON，禁止输出 `NaN`、`Infinity` 或 `-Infinity`。非有限数值必须转换为 `null`，且在影响结果解释时必须添加 `NON_FINITE_VALUE` 问题。

#### Scenario: 底层模型返回 NaN
- **WHEN** 任一底层模型结果包含非有限浮点值
- **THEN** 公共响应中的对应值必须为 `null`
- **AND** 响应必须能被严格 JSON 解析器成功解析
- **AND** `issues` 必须在该值影响业务解释时包含 `NON_FINITE_VALUE`

### Requirement: 分层结果投影

系统必须从同一规范模型结果生成 `public_full`、`chat_compact`、`llm_context` 和 `audit` 投影。投影过程禁止重新执行模型，禁止把完整规范结果复制到多个同级字段。

#### Scenario: 生成专题模型完整响应
- **WHEN** 专题模型 API 返回成功处理的模型调用
- **THEN** `data` 必须使用 `public_full` 投影
- **AND** 必须包含完整规范模型结果

#### Scenario: 生成聊天精简投影
- **WHEN** 聊天接口显式请求返回模型结果
- **THEN** `models` 中每个值必须使用 `chat_compact` 投影
- **AND** 必须省略大体积模块、中间计算、能力目录描述和内部执行错误

#### Scenario: 保存审计数据
- **WHEN** 系统保存模型执行日志或 trace
- **THEN** 完整输入、规范输出和内部诊断必须只进入 `audit` 投影
- **AND** 审计专用字段禁止出现在普通公共响应中

### Requirement: 输出协议版本与兼容投影

专题模型和聊天公共响应必须包含 `schema_version`。Schema 2.0 必须作为新默认结构；兼容期内请求 `response_schema="1.0"` 时，系统必须从规范模型结果生成旧结构，并提供弃用信息。

#### Scenario: 默认请求使用新结构
- **WHEN** 调用方未指定 `response_schema`
- **THEN** 响应 `schema_version` 必须为 `2.0`
- **AND** 响应必须符合新输出契约

#### Scenario: 兼容调用旧结构
- **WHEN** 调用方在兼容期请求 `response_schema="1.0"`
- **THEN** 系统必须从规范模型结果单向生成旧结构
- **AND** 响应必须包含弃用提示
- **AND** 系统禁止让旧对象成为内部模型结果的事实来源

