## MODIFIED Requirements

### Requirement: 智能体组合执行

系统 SHALL 根据统一能力目录的 `question_type` 对 1 至 7 进行一对一专业路由；`question_type=0` SHALL 继续走 RAG，不调用 AgentManager。映射为：1→`model-1`、2→`model-4`、3→`model-3`、4→`model-6`、5→`model-7`、6→`model-2`、7→`model-5`。路由即执行，系统 SHALL NOT 进行二次关键词过滤。

在五维路由生效时，系统 SHALL 在 `question_type` 判定基础之上叠加排他规则：当排他规则命中且能明确判别时，SHALL 路由到排他规则指定的目标 Agent；当排他规则无法消解重叠时，SHALL 返回「模型边界待确认」降级状态，而非自行选择。

#### Scenario: 提升潜力问题调用 model-2
- **WHEN** 用户问题被识别为 type 6 且排他规则判定潜力任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-2/PotentialAssessmentAgent`

#### Scenario: 有机质培肥问题调用 model-5
- **WHEN** 用户问题被识别为 type 7 且排他规则判定培肥任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-5/OrganicMatterAgent`

#### Scenario: 质量等级评价调用 model-7
- **WHEN** 用户问题为质量等级评价且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-7`
- **AND** SHALL NOT 路由到 `model-3`

#### Scenario: 现状障碍识别调用 model-3
- **WHEN** 用户问题为现状/障碍识别且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-7`

#### Scenario: 知识性问题走 RAG
- **WHEN** 用户问题被识别为 type 0
- **THEN** 系统 SHALL 路由到 RAG
- **AND** SHALL NOT 调用任何专业 Agent

#### Scenario: 重叠问题模型边界待确认
- **WHEN** 排他规则无法消解 model-3 与 model-7 等重叠关系
- **THEN** 系统 SHALL 返回「模型边界待确认」降级提示
- **AND** SHALL NOT 自行选择任一 Agent