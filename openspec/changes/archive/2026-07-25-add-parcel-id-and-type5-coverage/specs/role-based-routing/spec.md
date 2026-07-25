## MODIFIED Requirements

### Requirement: 用户角色识别
系统 SHALL 基于关键词匹配识别用户角色（省市管理端、县域执行端、农户种植端），并将问题路由到对应的智能体组合。

农户种植端（farmer）角色 SHALL 包含 model-7（FarmlandGradeAgent），使 farmer 问「我的田质量等级」时能触发耕地质量等级评价。model-7 的实际执行受 `AgentManager._should_execute_agent` 关键词过滤约束——仅当问题含 `QUESTION_TYPE_5_KEYWORDS` 时执行，否则跳过。

#### Scenario: 省市管理端路由
- **WHEN** 用户问题包含"全省"、"全市"、"全局"、"政策"等关键词
- **THEN** 系统 SHALL 识别角色为"省市管理端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent

#### Scenario: 县域执行端路由
- **WHEN** 用户问题包含"本县"、"乡镇"、"片区"、"任务"等关键词
- **THEN** 系统 SHALL 识别角色为"县域执行端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent + PotentialAssessmentAgent

#### Scenario: 农户种植端路由
- **WHEN** 用户问题包含"我的田"、"这块地"、"施氮肥"、"施多少"等关键词
- **THEN** 系统 SHALL 识别角色为"农户种植端"，路由到 AcidificationRemediationAgent (model-4) + OrganicMatterAgent (model-5) + FertilityMLAgent (model-6) + FarmlandGradeAgent (model-7)

#### Scenario: farmer 质量等级问题触发 model-7
- **WHEN** farmer 角色问题包含"质量等级"、"等级评价"、"综合指数"等 `QUESTION_TYPE_5_KEYWORDS` 关键词
- **THEN** 系统 SHALL 执行 model-7（FarmlandGradeAgent），调用 fortran exe 获取真实质量等级评价（如 `parcel_code` 可用）

#### Scenario: farmer 非质量等级问题跳过 model-7
- **WHEN** farmer 角色问题不含 `QUESTION_TYPE_5_KEYWORDS` 关键词（如「我的田肥力怎么样」）
- **THEN** 系统 SHALL 跳过 model-7（status=`skipped`, reason=`question_not_related`）
- **AND** SHALL 只执行 model-4/5/6
