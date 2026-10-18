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

系统 MUST 确保生成的汇报内容引用报告输入中的主题、范围、状态和已有结论，不得生成与当前上下文无关或输入中不存在的定量内容。报告生成后 MUST 执行数字审计：从输入上下文与数据章节构建数值白名单，抽取语言模型章节中的敏感定量表述，无法在白名单中追溯的数值 MUST 按“暂无可靠估计”处理，并在报告结果中记录问题清单。

#### Scenario: 基于当前诊断导出材料

- **WHEN** 调用方基于某次县域诊断结果执行导出
- **THEN** 系统 MUST 生成与该次诊断主题、区域和可靠性状态一致的汇报内容
- **AND** 所有定量内容 MUST 可追溯到原诊断中的非空可用字段

#### Scenario: 原诊断没有定量结果

- **WHEN** 原诊断的定量字段为空或标记为不可用
- **THEN** 导出内容 MUST 明确说明暂无可靠定量估计或省略该结论
- **AND** MUST NOT 根据模板、常识或语言模型自行推断数值

#### Scenario: 语言模型章节出现输入中没有的数值

- **WHEN** 某章节正文包含输入上下文中不存在的百分比、施用量、提升幅度或经济效益数值
- **THEN** 系统 MUST 将该数值替换为“暂无可靠估计”
- **AND** 报告 `status` MUST 为 `degraded`
- **AND** 报告结果 MUST 在审计信息中记录该章节、原始数值和稳定问题码

### Requirement: 结果整理接口优先返回结构化字段
系统 MUST 优先返回机器可读的摘要字段，而不是只返回一段不可拆解的长文本，以便未来 Agent 继续拼装输出。

#### Scenario: 解析结果整理接口返回值
- **WHEN** 未来 Agent 或前端消费结果整理接口
- **THEN** 系统 MUST 能以稳定字段读取摘要、发现、建议和行动项，而不依赖自然语言切分

### Requirement: 回填输入下报告不展示用量数值

当报告中的治理用量行来自含回填或默认输入的计算结果时，报告 MUST NOT 展示用量数值：相关列 SHALL 渲染“暂无可靠估计”，并在表格后说明原因（列出被回填或默认的输入字段）。该要求同时约束数据渲染章节与语言模型提示词摘要。

#### Scenario: 酸化治理用量表

- **WHEN** 某地块的 Model-4 输入包含回填或默认字段
- **THEN** 表格用量列 SHALL 为“暂无可靠估计”，MUST NOT 出现具体数值
- **AND** 表格后 SHALL 给出原因说明与字段清单

#### Scenario: 语言模型提示词摘要

- **WHEN** 提示词摘要包含该地块
- **THEN** 摘要 MUST 用“暂无可靠估计”并注明原因，MUST NOT 注入具体用量数值

### Requirement: 报告生成后的数字审计结果

系统 SHALL 在报告生成完成后返回固定结构的审计信息，至少包含已检查的定量表述数量、通过白名单校验的数量和问题清单；问题项 SHALL 包含稳定代码、章节标题、原始数值和说明。审计 MUST 基于机器可验证的白名单比对，MUST NOT 依赖另一次语言模型判断。

#### Scenario: 报告全部数值可追溯

- **WHEN** 语言模型章节只引用输入中已有的数值
- **THEN** 审计问题清单 MUST 为空
- **AND** 报告 `status` MUST 保持 `ok`

#### Scenario: 报告存在不可追溯数值

- **WHEN** 审计发现不可追溯数值
- **THEN** 审计信息 MUST 记录 `UNGROUNDED_QUANTITATIVE_CLAIM` 问题项
- **AND** 调用方 MUST 能在不解析正文 HTML 的情况下判断报告是否只引用输入事实

#### Scenario: 数据章节不受审计替换影响

- **WHEN** 章节由数据渲染器直接生成
- **THEN** 审计 MUST NOT 修改该章节内容
- **AND** 审计 SHALL 把该章节的数值视为白名单来源

