## MODIFIED Requirements

### Requirement: 秸秆移除计算

系统 SHALL 计算秸秆移除通量：`straw = [exp(ln)/(exp(ln)×0.76−0.0034)] × f11 × 0.5 × 15 / 1000`（g/ha/a）。分母 `exp(ln)×0.76−0.0034` 非正时系统 MUST **按原系统静默跳过**该样点（仅写日志），MUST NOT 因此中断计算。响应 MAY 返回 `skipped_invalid_denominator` 计数用于可观测性，该字段 MUST NOT 改变计算数值或筛选范围。移除计算 MUST 按全量执行，区域参数 MUST 仅记录（`area_filter: not_applied`），与原系统 `calculate_*_removal_by_area` 的 `area` 仅用于出图边界一致。

#### Scenario: 分母非正

- **WHEN** 某样点的 `exp(ln)×0.76−0.0034 ≤ 0`
- **THEN** 系统 MUST 跳过该样点且继续计算其余样点
- **AND** 跳过 MUST 只写日志，不得中断整批计算

#### Scenario: 正常计算

- **WHEN** 分母为正
- **THEN** 系统 MUST 按公式输出秸秆移除通量
- **AND** 单位 MUST 为 g/ha/a
