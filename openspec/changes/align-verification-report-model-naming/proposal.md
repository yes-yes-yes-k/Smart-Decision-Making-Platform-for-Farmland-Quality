## Why

验证报告中的模型命名和顺序与 Excel 标准表格（`数据字段标准化 (1).xlsx`）不一致。当前报告使用项目内部的 model-1 到 model-7 编号，而标准表格定义了 6 个模型的标准命名和顺序。需要调整验证报告使模型展示与标准表格一致，并为尚未实现的模型6（耕地综合地力改良提升模型）提供占位符。

## What Changes

- 建立 Excel 标准模型与项目 model 的映射关系，按标准顺序展示
- 使用 Excel 标准模型命名（如"耕地质量等级稳定性与退化风险识别模型"替代简写）
- 为模型6"耕地综合地力改良提升模型"添加占位符（未实现，显示为 placeholder）
- 调整 `verify_agent_capabilities.py` 中的模型命名以匹配标准表格
- 当前的 model-2 (PotentialAssessmentAgent) 和 model-5 (OrganicMatterAgent) 标注为"未对应 Excel 标准的占位桩"

### Excel 标准模型 ↔ 项目 model 对应关系

| Excel 标准模型 | 项目 model | Agent 类 | 状态 |
|---|---|---|---|
| 模型1：耕地质量等级稳定性与退化风险识别模型 | model-1 | StabilityRiskAgent | 真实计算 |
| 模型2：耕地质量提升潜力评估模型 | model-7 | FarmlandGradeAgent | 真实计算 |
| 模型3：耕地质量主要问题精准识别模型 | model-3 | ProblemIdentificationAgent | 真实计算 |
| 模型4：耕地土壤酸化改良模型 | model-4 | AcidificationRemediationAgent | 真实计算 |
| 模型5：耕地土壤有机质培肥提升模型 | model-6 | FertilityMLAgent | 真实计算 |
| 模型6：耕地综合地力改良提升模型 | —（占位符） | — | 未实现 |

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无 — 本变更仅修改验证脚本的展示层，不涉及 spec 级别的行为变更）

## Impact

- `scripts/gen_full_verification_report.py` — 修改模型展示逻辑，建立标准模型映射，添加模型6 占位符
- `scripts/verify_agent_capabilities.py` — 修改模型命名以匹配标准表格
- 不影响实际的路由逻辑、agent 注册或 API 契约
