## Context

当前多智能体框架采用 **role-based 路由**：`RoleRouter` 通过关键词识别用户角色（province/county/farmer），每个角色固定映射到一组 agents。`AgentManager.process` 调用 `identify_role` → `get_agents_for_role` → `_execute_with_dependencies`，其中 `_should_execute_agent` 对 model-6/model-7 做二次关键词过滤。

与此同时，`nodes.py` 中已存在稳定的 `identify_question_type` 函数，基于关键词+向量相似度识别 5 种问题类型（type 1-5）。`QUESTION_TYPE_TO_MODEL_ID` 字典已建立 type→model 映射（但缺少 type 5）。两套路由机制并存导致：

1. 冗余调用：farmer 问「我的田质量等级」会路由到 model-4/5/6/7 全部，再靠 `_should_execute_agent` 跳过 model-4/5/6
2. 语义重复：role 识别和 question_type 识别都在做问题分类
3. 心智负担：开发者需同时理解 role 路由 + question_type 路由 + 二次过滤三层逻辑

本次重构将路由统一为 question_type-based，消除冗余层次。

## Goals / Non-Goals

**Goals:**
- 将 `AgentManager.process` 的路由依据从 `role` 改为 `question_type`
- 实现 question_type → model 的 1:1 映射（type 1→model-1、type 2→model-4、type 3→model-3、type 4→model-6、type 5→model-7）
- 移除 `_should_execute_agent` 二次过滤逻辑（路由本身已保证精准性）
- 移除 API 响应中的 `role` 字段
- 保持 `identify_question_type`、`parcel_id`/`parcel_code` 透传、RAG 链路（type=0）不变

**Non-Goals:**
- 不修改 `identify_question_type` 的现有关键词列表和向量识别逻辑（但新增知识性问题预检分支）
- 不修改各专业模型（model-1/3/4/6/7）的内部实现
- 不重构 LangGraph 工作流节点拓扑（`initialize_state` → `identify_question_node` → `route_models` → `execute_models`/`rag_chat_node` → `llm_generate` → `aggregate_results`）
- 不移除 model-2/model-5 的注册（保留向后兼容，仅不被路由调用）
- 不重命名 `role-based-routing` spec 目录（仅修改内容）

## Decisions

### Decision 1: 1:1 映射而非 1:N

**选择**：每个 question_type 严格映射到单一 model（type 3→model-3 而非 model-2+model-3，type 4→model-6 而非 model-5+model-6）。

**理由**：
- 用户示例明确暗示 1:1（「障碍诊断问题调用诊断模型」「耕地质量评价调用 model7」均用单数）
- 1:1 消除拓扑排序复杂性，无需处理 model-3 依赖 model-2 的依赖链
- model-2（PotentialAssessmentAgent）和 model-5（OrganicMatterAgent）当前为桩/未完整实现，调用它们无实际价值
- 路由精准性由 `identify_question_type` 保证，无需多模型协同

**备选方案考虑**：
- 1:N（保留依赖链）：会保留冗余调用和拓扑排序复杂性，与重构目标相悖
- 混合（type 3 用 1:N，type 4 用 1:1）：增加心智负担，无充分理由

### Decision 2: 移除 `_should_execute_agent` 而非保留

**选择**：完全删除 `_should_execute_agent` 方法及 `FERTILITY_KEYWORDS`、`GRADE_KEYWORDS` 常量。

**理由**：
- 1:1 路由后，question_type 已精确决定调用哪个模型，二次过滤是冗余
- model-6 仅在 type 4 时调用（type 4 关键词已含肥力语义），无需再检查肥力关键词
- model-7 仅在 type 5 时调用（type 5 关键词已含等级语义），无需再检查等级关键词
- 移除后 `_execute_with_dependencies` 逻辑简化，每个 agent 直接执行

**备选方案考虑**：
- 保留作为「双保险」：增加维护成本，且关键词列表重复（GRADE_KEYWORDS 镜像 QUESTION_TYPE_5_KEYWORDS）

### Decision 3: `AgentManager.process` 通过 context 接收 question_type

**选择**：`process(question, context)` 从 `context.get("question_type")` 读取 question_type，不改变方法签名。

**理由**：
- 保持向后兼容（现有调用方无需改签名）
- `execute_models` 已构建 context dict，新增 `context["question_type"] = state.get("question_type")` 即可
- question_type=0（识别失败）时，`TYPE_AGENTS` 查不到对应 key，回退到调用所有真实模型——但这不会发生，因为 type=0 在 `route_models` 阶段已路由到 `rag_chat_node`，不会进入 `execute_models`

**备选方案考虑**：
- 改签名为 `process(question, context, question_type)`：更显式但破坏所有调用方
- 新增 `process_by_type(question_type, question, context)`：增加 API 表面积

### Decision 4: type=0 仍走 RAG，不在 AgentManager 处理

**选择**：保持现有 `route_models` 逻辑——type=0 → `rag_chat_node`，type≠0 → `execute_models`。

**理由**：
- type=0 是「识别失败/通用问题」，走 RAG 知识库是合理兜底
- 调用所有真实模型会产生大量无关回答，UX 不佳
- 用户明确选择保留现有行为

### Decision 5: `TYPE_AGENTS` 定义在 `router.py`，`RoleRouter` 类重命名为 `QuestionTypeRouter`

**选择**：在 `router.py` 中将 `RoleRouter` 类重命名为 `QuestionTypeRouter`，定义 `TYPE_AGENTS` 字典。

**理由**：
- 类名应反映职责，`RoleRouter` 名不副实
- `TYPE_AGENTS` 集中管理映射，便于维护和测试
- 重命名是 BREAKING change，但 `router.py` 仅被 `manager.py` 引用，影响可控

```python
class QuestionTypeRouter:
    TYPE_AGENTS: Dict[int, List[str]] = {
        1: ["model-1"],
        2: ["model-4"],
        3: ["model-3"],
        4: ["model-6"],
        5: ["model-7"],
    }

    def get_agents_for_type(self, question_type: int) -> List[str]:
        return list(self.TYPE_AGENTS.get(question_type, []))
```

**备选方案考虑**：
- 保留 `RoleRouter` 类名：误导性，违反最小惊讶原则
- 将 `TYPE_AGENTS` 放在 `manager.py`：职责分散，`router.py` 失去存在意义

### Decision 6: API 响应保留 `agents_invoked`/`summary`/`recommendations`，仅移除 `role`

**选择**：`chat.py` 移除 `role = agent_data.get("role")` 和 `response_data["role"] = role`，保留其他字段。

**理由**：
- `agents_invoked` 对客户端调试可见性有价值
- `summary` 是 AgentManager 聚合的答案文本，作为 `answer` 的补充
- `recommendations` 提供行动建议，有业务价值
- 仅 `role` 字段因本次重构失效，需移除

### Decision 7: 新增知识性问题预检（Spec Patch）

**选择**：在 `identify_question_type` 函数最前端插入 `_is_knowledge_question` 预检，命中知识性问题模式时直接返回 `(0, 1.0)` 走 RAG，先于 relevance 检查和领域关键词匹配。

**模式列表**（保守、高精度）：
- 开头匹配（强信号）：`"什么是"`、`"何为"`、`"解释"`
- 包含匹配（含义类）：`"是什么意思"`、`"什么意思"`、`"定义"`、`"概念"`、`"含义"`

**理由**：
- 当前关键词匹配过于激进——「什么是土壤酸化」因含「酸化」被路由到 model-4，但实际是概念解释应走 RAG
- 知识性问题与具体诊断问题的区别：前者问普遍概念，后者问具体地块/数据
- 保守模式避免误报：「我的田耕地质量等级是多少」不匹配任何知识模式，仍走 type 5 → model-7

**备选方案考虑**：
- 扩展模式（加「为什么」「区别」「差异」）：召回率高但「为什么我的田酸化」会误判为知识问题
- 仅最小集（「什么是」「何为」）：漏报「X是什么意思」类
- 当前选择平衡精度和召回

```python
KNOWLEDGE_QUESTION_PATTERNS_START = ["什么是", "何为", "解释"]
KNOWLEDGE_QUESTION_PATTERNS_CONTAIN = ["是什么意思", "什么意思", "定义", "概念", "含义"]

def _is_knowledge_question(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    if any(q.startswith(p) for p in KNOWLEDGE_QUESTION_PATTERNS_START):
        return True
    if any(p in q for p in KNOWLEDGE_QUESTION_PATTERNS_CONTAIN):
        return True
    return False
```

## Risks / Trade-offs

**[Risk] model-2/model-5 永远不被调用，可能隐藏未发现的 bug** → 保留注册和单元测试，确保它们仍可独立执行；未来如需启用，只需在 `TYPE_AGENTS` 添加映射。

**[Risk] `identify_question_type` 误判导致问题路由到错误模型** → 现有 `identify_question_type` 已经过验证（23/23 测试通过），误判风险与重构前相同；重构后影响范围更小（只调一个模型而非一组）。

**[Risk] 知识性问题预检误报导致具体问题被误路由到 RAG** → 采用保守模式列表（仅高精度模式），「为什么」「区别」等歧义模式不纳入；测试覆盖边界场景。

**[Risk] 客户端依赖 `role` 字段导致 BREAKING** → 在 proposal 中明确标注 BREAKING；可通过 changelog 通知客户端；`question_type` 字段已存在，客户端可改用该字段。

**[Trade-off] 1:1 映射失去多模型协同能力** → 当前 model-2/model-5 为桩实现，协同价值有限；未来如需真实多模型协同，可扩展 `TYPE_AGENTS` 为 1:N。

**[Trade-off] spec 目录名 `role-based-routing` 与新内容不符** → 避免目录重命名的 git 复杂度；在 spec 内容中明确说明这是 question_type-based routing。

## Migration Plan

1. **代码改动顺序**（TDD）：
   - 先改 `router.py`（新增 `QuestionTypeRouter` + `TYPE_AGENTS`）
   - 再改 `manager.py`（`process` 用 question_type，删 `_should_execute_agent`）
   - 再改 `nodes.py`（`execute_models` 透传 question_type，`QUESTION_TYPE_TO_MODEL_ID` 加 type 5）
   - 再改 `chat.py`（移除 role 字段）
   - 同步更新所有测试

2. **回滚策略**：
   - 本次变更为纯代码重构，无数据库迁移
   - 如需回滚，`git revert` 即可恢复 role-based 路由

3. **验证**：
   - 单元测试覆盖所有 5 种 question_type 的路由
   - 运行 `gen_full_verification_report.py` 确认 23 个问题回答不变
   - 验证 API 响应不含 `role` 字段，含 `question_type`

## Open Questions

无。所有关键决策已在需求澄清阶段确认。
