## Context

当前系统使用 `framework/agents/nodes.py` 中的 `_identify_question_type_keyword` 函数进行问题类型识别，只支持 QUESTION_TYPE_1/2/3（酸化治理相关），不支持肥力问题（model-6）。当用户询问肥力相关问题时，系统返回 question_type=0，路由到 RAG 分支，无法触发 AgentManager 和 model-6 的 ML 预测。

## Goals / Non-Goals

**Goals:**
- 在 `nodes.py` 中新增肥力关键词识别，使肥力问题返回 question_type=4
- question_type=4 路由到 `execute_models`，触发 AgentManager 和 model-6

**Non-Goals:**
- 不修改 AgentManager 或 FertilityMLAgent 的现有逻辑
- 不修改 RAG 或 LLM 服务
- 不新增 API 端点

## Decisions

**Decision 1: 新增 QUESTION_TYPE_4_KEYWORDS**

关键词列表从 `FertilityMLAgent` 和 `AgentManager` 的 `FERTILITY_KEYWORDS` 中提取核心词：
- "有机肥"、"施肥"、"施用量"、"肥力"、"有机碳"、"SOC"、"Dose"

**Decision 2: 修改 _identify_question_type_keyword 返回 question_type=4**

在现有 TYPE_1/2/3 判断之后添加 TYPE_4 判断，保持原有优先级不变。

**Decision 3: route_models 无需修改**

现有逻辑：`if question_type == 0: return "rag_chat"; return "execute_models"`，question_type=4 会自动路由到 `execute_models`。

## Risks / Trade-offs

- **风险**：关键词冲突（同一问题同时匹配多个类型）→ 缓解：保持现有优先级（酸化 > 治理 > 氮肥 > 肥力），肥力匹配放在最后
- **风险**：误匹配非肥力问题 → 缓解：使用精确关键词（如"有机肥"而非"有机"），避免过度匹配
