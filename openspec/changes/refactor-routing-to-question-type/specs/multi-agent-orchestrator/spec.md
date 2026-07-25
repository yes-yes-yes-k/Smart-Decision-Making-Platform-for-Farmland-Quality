## REMOVED Requirements

### Requirement: model-7 问题感知过滤
**Reason**: 本次重构将路由改为 question_type-based 1:1 映射后，model-7 仅在 question_type=5 时被 `TYPE_AGENTS` 路由调用，路由本身已保证 model-7 不会在非质量等级问题上执行。`AgentManager._should_execute_agent` 二次关键词过滤逻辑完全移除，无需单独为 model-7 维护过滤要求。
**Migration**: 不再需要 `GRADE_KEYWORDS` 常量镜像 `QUESTION_TYPE_5_KEYWORDS`。type 5 问题的路由由 `identify_question_type` 关键词识别 + `TYPE_AGENTS[5] = ["model-7"]` 映射共同保证。非 type 5 问题不会进入 model-7 的执行路径。

## MODIFIED Requirements

### Requirement: Type 5 质量等级评价问题库
系统 SHALL 在 `REFERENCE_QUESTIONS` 字典中维护 key `5`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」），使验证脚本能覆盖 model-7。

`_identify_question_type_keyword` 函数 SHALL 维护 type 5 分支，当问题命中 `QUESTION_TYPE_5_KEYWORDS`（"质量等级"、"等级评价"、"综合指数"、"指标隶属度"、"障碍度排序"、"耕地质量等级"、"质量评价"、"等级评定"、"指标权重"）时返回 `(5, relevance)`。

`TYPE_AGENTS` 映射表 SHALL 将 question_type=5 严格映射到 `["model-7"]`（1:1 映射），SHALL NOT 包含 model-4/5/6。type 5 问题的路由 SHALL NOT 依赖用户角色识别（role-based 路由已移除）。

#### Scenario: 识别质量等级问题为 type 5
- **WHEN** 用户询问「我的田耕地质量等级是多少」
- **THEN** `identify_question_type` SHALL 返回 `question_type=5`

#### Scenario: type 5 问题仅路由到 model-7
- **WHEN** 问题被识别为 type 5
- **THEN** `QuestionTypeRouter.get_agents_for_type(5)` SHALL 返回 `["model-7"]`
- **AND** `AgentManager.process` SHALL 仅调用 model-7（FarmlandGradeAgent）
- **AND** SHALL NOT 调用 model-4/5/6
- **AND** model-7 SHALL 被执行（status ≠ `skipped`），无需 `_should_execute_agent` 二次过滤

#### Scenario: 非 type 5 问题不调用 model-7
- **WHEN** 问题被识别为 type 1/2/3/4（如「我的田肥力怎么样」识别为 type 4）
- **THEN** `AgentManager.process` SHALL NOT 调用 model-7
- **AND** SHALL NOT 在 `details` 中出现 model-7 的 `skipped` 条目（因路由未包含 model-7）
