## MODIFIED Requirements

### Requirement: 智能体组合执行

系统 SHALL 根据统一能力目录的 `question_type` 对专业问题进行确定性路由；`question_type=0` SHALL 继续走 RAG，不调用 AgentManager。质量等级评价（type 5）和提升潜力评估（type 6）SHALL 均路由到同一个真实 `model-2`，其他专题问题继续路由到各自的正式模型。路由结果 SHALL 不包含独立 `model-7`。

#### Scenario: 提升潜力问题调用 model-2
- **WHEN** 用户问题被识别为 `question_type=6`
- **THEN** `AgentManager.process` SHALL 仅调用 `model-2/improvement-potential-assessment`
- **AND** 提供地块编码时 SHALL 返回真实单地块或县域潜力计算结果

#### Scenario: 质量等级问题调用 model-2
- **WHEN** 用户问题被识别为 `question_type=5`
- **THEN** `AgentManager.process` SHALL 仅调用 `model-2/improvement-potential-assessment`
- **AND** 提供地块编码时 SHALL 返回真实质量等级、综合指数和障碍度结果

#### Scenario: 不再路由到独立 model-7
- **WHEN** 系统对任意 `question_type` 执行专业路由
- **THEN** `agents_invoked` SHALL NOT 包含 `model-7`

#### Scenario: 有机质培肥问题调用 model-5
- **WHEN** 用户问题被识别为 `question_type=7`
- **THEN** `AgentManager.process` SHALL 仅调用 `model-5/organic-matter-improvement`

#### Scenario: 知识性问题走 RAG
- **WHEN** 用户问题被识别为 `question_type=0`
- **THEN** 系统 SHALL 走 RAG 链路
- **AND** SHALL NOT 调用任一专业 Agent

