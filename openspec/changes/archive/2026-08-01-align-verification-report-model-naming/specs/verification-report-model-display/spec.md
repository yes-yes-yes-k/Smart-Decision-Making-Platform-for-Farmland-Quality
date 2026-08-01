## ADDED Requirements

### Requirement: 验证报告按 Excel 标准模型顺序展示
验证报告 SHALL 按 Excel 标准表格（数据字段标准化）定义的 6 个模型顺序展示，使用标准模型命名。

#### Scenario: 标准模型顺序展示
- **WHEN** 生成验证报告时
- **THEN** "Agent 加载状态盘点"表格 SHALL 按 模型1→模型2→模型3→模型4→模型5→模型6 的顺序展示

#### Scenario: 标准模型命名
- **WHEN** 展示模型信息时
- **THEN** 每个模型行 SHALL 显示 Excel 标准名称（如"耕地质量等级稳定性与退化风险识别模型"），同时标注对应的项目 model_id

### Requirement: 模型6 占位符展示
验证报告 SHALL 为未实现的模型6（耕地综合地力改良提升模型）显示占位符行。

#### Scenario: 模型6 占位
- **WHEN** 展示模型6 时
- **THEN** 报告 SHALL 显示"占位符（未实现）"，model_id 为 None，状态为"未实现"

### Requirement: 未对应 Excel 标准的占位桩标注
验证报告 SHALL 在标准模型表格后，标注当前项目中未对应 Excel 标准模型的占位桩 agent。

#### Scenario: 占位桩标注
- **WHEN** 项目中存在 model-2 (PotentialAssessmentAgent) 和 model-5 (OrganicMatterAgent) 等未对应 Excel 标准的 agent 时
- **THEN** 报告 SHALL 在表格末尾附加说明"未对应 Excel 标准的占位桩"
