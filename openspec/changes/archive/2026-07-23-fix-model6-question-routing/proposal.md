## Why

**问题**：用户询问肥力相关问题（如"我的田施有机肥多少？"）时，系统路由到 RAG 分支而非 model-6（FertilityMLAgent），导致 LLM 超时返回"AI服务暂时不可用"，用户无法获得 ML 预测结果。

**根因**：`framework/agents/nodes.py` 的 `_identify_question_type_keyword` 函数只识别 QUESTION_TYPE_1/2/3（酸化治理相关）关键词，未包含肥力/施肥相关关键词，导致肥力问题被判定为 question_type=0（RAG），无法触发 model-6 的 ML 预测。

## What Changes

- 在 `framework/agents/nodes.py` 中新增 `QUESTION_TYPE_4_KEYWORDS`（肥力相关关键词列表）
- 修改 `_identify_question_type_keyword` 函数，添加对肥力问题的识别逻辑，返回 question_type=4
- 修改 `route_models` 函数，确保 question_type=4 路由到 `execute_models`（调用 AgentManager + model-6）

## Capabilities

### New Capabilities
- `fertility-ml-prediction-routing`: 肥力问题正确路由到 model-6 执行 ML 预测

### Modified Capabilities
- `professional-model-agents`: 新增 question_type=4 路由规则，确保 FertilityMLAgent 在肥力问题时被调用

## Impact

- **代码影响**：修改 `framework/agents/nodes.py` 单文件（约 10 行新增/修改）
- **API 影响**：无公共 API 变更，仅内部路由逻辑调整
- **测试影响**：需添加单元测试验证肥力问题路由正确性
