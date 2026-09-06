# county-smart-diagnosis Specification

## Purpose
TBD - created by archiving change bootstrap-lechang-county-demo. Update Purpose after archive.
## Requirements
### Requirement: 县域诊断结构化接口
系统 MUST 支持围绕乐昌市县域问题发起结构化诊断请求，并输出结构化诊断结果，至少包括诊断主题、问题摘要、判定依据、可验证的重点区域提示、治理方向和推荐图层。系统只有在具备字段级依据时才 MUST 返回定量结论；模板化内容 MUST 标记为定性建议而非预测结果。

#### Scenario: 按主题发起县域酸化诊断
- **WHEN** 调用方以结构化参数请求县域酸化诊断，但没有可验证的县域治理效果预测
- **THEN** 系统 MUST 返回酸化主题、定性问题说明、推荐图层和治理方向
- **AND** MUST 将结果标记为 `advisory_only`
- **AND** MUST NOT 返回无依据的见效时间、提升率、成本或治理效果

#### Scenario: 按区域发起县域综合诊断
- **WHEN** 调用方请求县域耕地质量提升或限制因子识别诊断
- **THEN** 系统 MUST 返回与该主题对应的诊断摘要、建议查看的图层和治理方向
- **AND** 重点区域、占比或排序只有在真实统计结果可用时才 MUST 返回

### Requirement: 诊断与地图联动
系统 MUST 将诊断结果与地图展示联动，确保每次诊断结果都能指向一个或多个建议展示的专题图层或区域范围。

#### Scenario: 根据诊断推荐图层
- **WHEN** 系统完成一次县域诊断
- **THEN** 系统 MUST 返回与该诊断相关的推荐图层或推荐查看区域，供前端直接切换展示

### Requirement: 缺失输入时允许模板回退
系统 MUST 在模型所需输入字段不完整时提供可解释的回退策略。最近邻数据只有在匹配范围、距离、来源和时间可追溯时才可用于计算；模板回退 MUST 仅提供定性建议，不得使用模板数字补齐治理周期、提升率、效果、成本或占比。

#### Scenario: 位置诊断缺少完整字段
- **WHEN** 调用方发起基于位置的诊断请求，且部分模型输入字段缺失
- **THEN** 系统 MUST 返回缺失字段、实际采用的回退来源和受影响结果
- **AND** 如果没有满足溯源要求的最近邻数据，系统 MUST 将相关定量字段标记为不可用
- **AND** MUST NOT 使用固定模板数字完成计算

#### Scenario: 仅能提供模板建议
- **WHEN** 系统只能根据主题提供通用治理方向
- **THEN** 每条建议 MUST 标记 `advisory_only=true` 和 `basis=template_guidance`
- **AND** 建议 MUST NOT 使用预测性定量措辞

### Requirement: 诊断接口支持机器可读状态
系统 MUST 为诊断接口返回稳定的状态字段、错误信息字段、结果性质和数据来源字段。模板化定性结果 MUST 使用 HTTP 200、`status=degraded` 和 `result_kind=advisory_only`，并明确 `predictive=false` 与 `quantitative_available=false`，不得伪装为普通成功的真实诊断。

#### Scenario: 真实诊断成功返回结构化状态
- **WHEN** 调用方成功完成一次具备可验证数据和结果的县域诊断
- **THEN** 系统 MUST 返回 `status=ok`、诊断主题、结果主体和来源说明
- **AND** 所有非空定量字段 MUST 具备完整依据

#### Scenario: 模板建议返回降级状态
- **WHEN** 请求合法但系统只能返回通用定性建议
- **THEN** 系统 MUST 返回 HTTP 200、`status=degraded` 和 `result_kind=advisory_only`
- **AND** 顶层可靠性 MUST 表明证据不足且不可进行定量预测

#### Scenario: 诊断失败返回结构化错误
- **WHEN** 调用方提交了无效参数或触发了诊断失败
- **THEN** 系统 MUST 返回可机读的失败状态、错误码或错误原因
- **AND** MUST 避免只返回笼统文本

### Requirement: 县域诊断禁止无依据定量占位值

系统 MUST NOT 在县域诊断活动响应中把固定模板值作为治理周期、提升率、治理效果、成本或问题占比返回。缺少经过验证的数据或模型依据时，既有定量字段 MUST 保留为 `null` 或从响应中省略；为兼容保留字段时 MUST 同时提供机器可读的不可用原因。

#### Scenario: 模板诊断不返回固定预测数字

- **WHEN** 调用方请求县域酸化、质量或治理提升诊断，且系统没有可验证的治理效果或统计结果
- **THEN** `period`、`improve`、`effect`、`cost` 和问题 `percent` 等定量字段 MUST NOT 包含固定联调值
- **AND** 为兼容保留的字段 MUST 为 `null`
- **AND** 响应 MUST NOT 包含 `1-2年`、`2-3年` 或其他被描述为预计见效时间的模板周期

#### Scenario: 兼容别名不复制占位值

- **WHEN** 响应同时包含 `measures`、`treatments`、`regions` 或 `base_data` 等兼容结构
- **THEN** 所有结构 MUST 遵守相同的定量安全规则
- **AND** 系统 MUST NOT 在任一兼容结构中恢复或复制无依据数字

### Requirement: 县域定量结果必须具备字段级依据

系统只有在非空定量值同时具备数据来源、计算或统计方法、计算时间、适用范围以及适用时的模型版本后，才 MUST 将该字段标记为可用。潜在定量字段附近 MUST 提供 `metric_meta` 或等价的机器可读元数据。

#### Scenario: 缺少依据的数值被拒绝

- **WHEN** 县域诊断构造出非空定量值，但没有完整的 `source`、`method`、`calculated_at` 或 `scope`
- **THEN** 系统 MUST 拒绝把该值作为正常诊断结果返回
- **AND** MUST 记录可定位的契约错误

#### Scenario: 有依据的真实数值可以返回

- **WHEN** 定量值来自已验证数据或专业模型，且字段元数据完整
- **THEN** 系统 MUST 返回该值、单位和字段级依据
- **AND** 顶层可靠性状态 MUST 与字段可用性一致

