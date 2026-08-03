## MODIFIED Requirements

### Requirement: Question Type Identification

系统 SHALL 将 SOC、有机碳、Dose、施肥量预测、氮肥施用量、预测置信度等问题识别为 type 4；将有机肥施用、秸秆还田、培肥方案和提升有机质措施等问题识别为 type 7。具体诊断问题仍优先于知识性问题处理。

#### Scenario: SOC 预测问题
- **WHEN** 用户询问地块 SOC 预测值或预测置信度
- **THEN** 系统 SHALL 识别为 type 4 并仅调用 `model-6`

#### Scenario: 氮肥施用量问题
- **WHEN** 用户询问地块应施多少氮肥
- **THEN** 系统 SHALL 识别为 type 4 并仅调用 `model-6`

#### Scenario: 有机肥施用方案问题
- **WHEN** 用户询问有机肥每亩施用量或秸秆还田方案
- **THEN** 系统 SHALL 识别为 type 7 并仅调用 `model-5`
