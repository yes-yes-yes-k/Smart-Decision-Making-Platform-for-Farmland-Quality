# demo-report-export Specification

## Purpose
TBD - created by archiving change bootstrap-lechang-county-demo. Update Purpose after archive.
## Requirements
### Requirement: 诊断结果整理接口
系统 MUST 支持将一次结构完整的 `ok` 或 `degraded` 县域诊断结果整理为适合汇报和后续 Agent 二次加工的结构化内容，至少包含结论摘要、关键发现、治理建议、后续行动项、原诊断结果性质和可靠性状态。整理过程 MUST NOT 将定量不可用的诊断升级为真实或普通成功结论。

#### Scenario: 基于安全降级诊断生成摘要
- **WHEN** 调用方基于 `status=degraded`、`result_kind=advisory_only` 的县域诊断请求生成摘要
- **THEN** 系统 MUST 保留原诊断的结果性质和可靠性状态
- **AND** MUST 只整理已有定性内容和推荐图层
- **AND** MUST NOT 因原字段为 `null` 而补造周期、提升率、效果、成本或占比

#### Scenario: 基于真实诊断生成摘要
- **WHEN** 调用方基于具备完整定量依据的 `status=ok` 诊断请求生成摘要
- **THEN** 系统 MUST 输出包含结论摘要、关键发现、治理建议和后续行动项的结构化内容
- **AND** 引用的定量值 MUST 与原诊断及其字段级依据一致

### Requirement: 汇报内容与诊断结果一致
系统 MUST 确保导出的汇报内容引用当前诊断结果中的主题、区域、状态和已有关键结论，不得生成与当前诊断上下文无关或输入中不存在的定量内容。

#### Scenario: 基于当前诊断导出材料
- **WHEN** 调用方基于某次县域诊断结果执行导出
- **THEN** 系统 MUST 生成与该次诊断主题、区域和可靠性状态一致的汇报内容
- **AND** 所有定量内容 MUST 可追溯到原诊断中的非空可用字段

#### Scenario: 原诊断没有定量结果
- **WHEN** 原诊断的定量字段为空或标记为不可用
- **THEN** 导出内容 MUST 明确说明暂无可靠定量估计或省略该结论
- **AND** MUST NOT 根据模板、常识或语言模型自行推断数值

### Requirement: 结果整理接口优先返回结构化字段
系统 MUST 优先返回机器可读的摘要字段，而不是只返回一段不可拆解的长文本，以便未来 Agent 继续拼装输出。

#### Scenario: 解析结果整理接口返回值
- **WHEN** 未来 Agent 或前端消费结果整理接口
- **THEN** 系统 MUST 能以稳定字段读取摘要、发现、建议和行动项，而不依赖自然语言切分

