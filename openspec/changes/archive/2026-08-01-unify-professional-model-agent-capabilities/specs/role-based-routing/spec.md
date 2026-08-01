## MODIFIED Requirements

### Requirement: 智能体组合执行

系统 SHALL 根据统一能力目录的 `question_type` 对 1 至 7 进行一对一专业路由；`question_type=0` SHALL 继续走 RAG，不调用 AgentManager。映射为：1→`model-1`、2→`model-4`、3→`model-3`、4→`model-6`、5→`model-7`、6→`model-2`、7→`model-5`。路由即执行，系统 SHALL NOT 进行二次关键词过滤。

#### Scenario: 提升潜力问题调用 model-2
- **WHEN** 用户问题被识别为 type 6
- **THEN** `AgentManager.process` SHALL 仅调用 `model-2/PotentialAssessmentAgent`

#### Scenario: 有机质培肥问题调用 model-5
- **WHEN** 用户问题被识别为 type 7
- **THEN** `AgentManager.process` SHALL 仅调用 `model-5/OrganicMatterAgent`

#### Scenario: 知识性问题走 RAG
- **WHEN** 用户问题被识别为 type 0
- **THEN** 系统 SHALL 路由到 RAG
- **AND** SHALL NOT 调用任何专业 Agent

### Requirement: Question Type Identification

系统 SHALL 将 SOC、有机碳、Dose、施肥量预测、预测置信度等问题识别为 type 4；将有机肥施用、秸秆还田、培肥方案和提升有机质措施等问题识别为 type 7。具体诊断问题仍优先于知识性问题处理。

#### Scenario: SOC 预测问题
- **WHEN** 用户询问地块 SOC 预测值或预测置信度
- **THEN** 系统 SHALL 识别为 type 4 并仅调用 `model-6`

#### Scenario: 有机肥施用方案问题
- **WHEN** 用户询问有机肥每亩施用量或秸秆还田方案
- **THEN** 系统 SHALL 识别为 type 7 并仅调用 `model-5`

## ADDED Requirements

### Requirement: 路由失败不回退到隐式多模型组合

系统 SHALL 在 AgentManager 或已路由 Agent 失败时保留当前能力的结构化状态。系统 SHALL NOT 使用旧的 `QUESTION_TYPE_TO_MODEL_ID` 多模型组合回退，也 SHALL NOT 在响应中执行未声明的其他专业 Agent。

#### Scenario: 已路由 Agent 执行失败
- **WHEN** 已路由的专业 Agent 抛出异常或返回未就绪状态
- **THEN** 系统 SHALL 返回当前 `question_type`、对应 Agent ID、错误/降级原因和可用专业结果
- **AND** SHALL NOT 调用额外的专业 Agent
