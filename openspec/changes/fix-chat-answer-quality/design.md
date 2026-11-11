## Context

### 系统链路
`/api/v1/chat/stream` → `MultiAgentOrchestrator.run_stream` → 路由识别（`routing.py`，`ROUTING_MODE=llm` 默认）→ [`execute_models`](nodes.py)（Function Calling 优先，回退 `AgentManager`）→ 专业模型（model-1 稳定性 / model-2 质量等级 / model-3 障碍 / model-4 酸化 / model-5 有机质，均为 `output_contract.py` 规范化 envelope）→ RAG 取证（可选）→ 最终 LLM 总结（`build_professional_answer_prompt` + `llm_context` 投影）→ 前端展示（字段直查前缀 + 结论正文 + sources）。

### 已验证事实（本次收集的运行时证据）
| 编号 | 结论 | 证据来源 |
|---|---|---|
| F1 | 地块 3597 的 `parcel_info.soil_indicators` **确有实测 `soil_ph=5.1736`**，来源 `model1_shapefile`、`is_imputed=false`、年份 2024；`exchangeable_hydrogen=0.2949`、`exchangeable_aluminum=4.0262` 也在 | psycopg2 直连生产 DB |
| F2 | 3597 有 **3 期历史等级快照**（2018: 9等/0.7053，2021: 6等/0.7447，2024: 4等/0.7876），**稳定性完全可判定** | `parcel_history_snapshot` |
| F3 | model-2 正式评算结果为 5等/0.8425（`versioned_model_result` 2026-10-13），与快照 4等/0.7876 **不一致**（两套等级口径并存） | `versioned_model_result` vs `parcel_info.quality_grade` |
| F4 | 会话实际回答：Q"酸化严重吗"回复「现有结果中没有该地块的实测土壤酸碱度及酸化分级，无法判断」，**与 F1 矛盾**；同会话后续一次回答却展示出 model-4 的酸负荷数值（背景酸108058.79等）且仍称「酸碱度值为空」——**model-4 实际执行成功，但 `soil_ph/acidification_level` 未出现在 LLM 上下文** | `kb_message` 会话记录 |
| F5 | Q"质量等级稳不稳，退化风险高吗"只回答「耕地质量等级为 5等」，**未回答稳定性与退化风险**，尽管 F2 数据充足 | `kb_message` 会话记录 |
| F6 | 障碍度字段直查把 **Python dict 字面量** 原样带给用户；LLM 正文把「耕层质地」**幻觉为「耕作制度」** 且排序与权威 dict 不一致 | 会话记录 + [`parcel_field_query._format_value`](framework/agents/parcel_field_query.py) 不处理 Mapping |
| F7 | 酸化解释优化（提交 e36e14a9）在 2026-11-11 被 **Revert（206501de）**，连带删除专项 prompt 规则、`public_numbers.py`、延迟观测；工作区随后手工恢复部分修复但 **未提交**（`git status`：7 个 M 文件 + 1 个未跟踪文件）——修复处于随时可再次丢失状态 | `git log` / `git status` |
| F8 | `ROUTING_MODE=llm` 时 LLM 初判**覆盖**关键词判定（`routing.py` `identify_question_type`），排他规则「{model-1,model-2}→model-1」在纯关键词路径下生效，但对 LLM 复合意图初判无保底 | 代码路径 |

### 约束
- 不改专业模型计算内核（model-1~5 算法与 DB 表结构）。
- 改动聚焦聊天回答的**呈现与路由决策**；回答必须诚实、只答所问、不编造。
- 保持 `chat_compact`/`model_results` 协议稳定，不破坏既有 API 契约。

## Goals / Non-Goals

**Goals:**
- G1 酸化回答必须反映实测：DB 有 `soil_ph` 时回答 SHALL 报告 pH 值与酸化分级（含"强酸性/酸性"判定与"严重吗"的明确结论）；无实测时给出**缺失原因 + 分级阈值 + 补测引导**，禁止笼统"无法判断"。
- G2 稳定性复合意图保底路由：含稳定性关键词（稳不稳/退化风险/等级稳定/掉级）的问题 SHALL 无论 LLM 初判结果如何都执行 model-1；历史充足时输出稳定性+退化风险结论，历史不足时输出契约化解释。
- G3 回答正文完整性：最终正文 SHALL NOT 为空（禁止只剩"分析对象：地块xxx"前缀），LLM 总结为空/失败时 SHALL 用确定性模型结果兜底。
- G4 字段幻觉治理：LLM 结论字段 SHALL 来自模型结果字段白名单；障碍度排序 SHALL 有序逐项渲染，禁止 dict 字面量与"耕作制度"类幻觉字段。
- G5 回归防护：将未提交修复纳入 git 提交，并为 4 个问题增加会话级回归断言（测试锚点），防止再次被整体 Revert。

**Non-Goals:**
- 不改专业模型计算内核、不改 DB 表结构。
- 不处理 model-2 快照(4等/0.79)与正式评算(5等/0.84)的口径不一致——单独立项，本轮只记录差异。
- 不做前端 UI 重构；不重构 RAG 检索链路；不改知识库/文档内容。

## Decisions

### D1 稳定性复合意图保底路由（关键词优先于 LLM 初判）
在 `identify_question_type` 中，LLM 初判结果落定前，若问题命中 type-1 稳定性关键词（"稳不稳""退化风险""等级稳定""掉级"）则 SHALL 强制回落到 type-1（联动 model-2 字段直查），不等待 LLM 判断。排他规则 `{model-1, model-2} → model-1` 已存在于 `exclusive_rules.PRIORITY_RESOLUTION`，需将其作为**任何路由模式下**的最终兜底（当前纯关键词路径生效，LLM 路径可能跳过）。
- 备选：仅依赖排他规则。缺点：排他规则只在问题类型判定后叠加，无法防止 LLM 把复合问题判成单一 type-2。
- 理由：关键词是领域内的强先验（契约已维护），LLM 初判用于模糊问题；两者冲突时应以强先验为准，符合"专业模型不因路由误判被跳过"的既有设计方向（见 `routing.py` 对 type-0 的同样处理）。

### D2 Model-4 酸化结果必带 `soil_ph`/`acidification_level`
`output_contract` 的 model-4 规范结果 SHALL 在存在实测输入时携带 `soil_ph` 与 `acidification_level`；回填/降级仅清空定量用量字段（`background_acid`/`soil_conditioner_dosage`/`woody_peat_dosage`），**不得清空 `soil_ph`**（当前 `normalize_execution` 已是此行为，但回答链路显示该值未到达 LLM）。同时把 model-4 的土壤状态输出改为**确定性句式基础 + LLM 解释扩展**：
- 有实测：前缀由系统确定性生成「土壤酸碱度(pH)=X；分级=Y（<5.5 强酸性，5.5~6.5 酸性）。是否严重：Y>=强酸性 时『强酸性，属严重』」。
- 无实测：前缀确定性生成「该地块缺少实测 pH 记录；分级阈值：<5.5 强酸性 / 5.5~6.5 酸性；建议补测」。
- LLM 只负责解释、扩展与结合障碍度，禁止否定前缀已展示的实测数据（契约规则）。
- 备选：继续依赖 LLM 从 `llm_context` 自行携带。缺点：F4 实证 LLM 会丢弃/改写 `soil_ph`；决定改为"确定性前缀为主，LLM 为辅"。

### D3 空正文兜底（确定性 body guard）
`run_stream` 与 `aggregate_results` 的模型路径在「正文为空」场景下 SHALL 以 `deterministic_answer` 拼接模型结果作为正文；并新增场景级断言（LLM 返回空流时回答不得为空）。同会话后续回答亦需通过 `field_query` 前缀拼接正确的确定性正文（当前会话存在"只有前缀、正文缺失"的实例）。
- 备选：重试 LLM。缺点：增加时延与成本，revert 历史已表明整体回退风险；确定性兜底零成本且完全可测试。

### D4 字段白名单 + 障碍度有序渲染
- `parcel_field_query._format_value` SHALL 支持 `Mapping`：对障碍度 dict 按权威键顺序逐项渲染为「标签 数值」（禁止 `str(dict)`）。
- `build_professional_answer_prompt` 增加**字段白名单**约束：LLM 只能使用上下文中 `result` 实际存在的标准字段名；补充 `public_field_labels` 别名表（含「耕作制度」→ 非合法字段，正确名「耕层质地」/按结果键）。
- 对幻觉字段实现双层拦截：prompt 约束 + 输出后校验（正文若出现白名单外字段名则丢弃该句/回退确定性模板）。
- 备选：只改 prompt。缺点：F6 证明 prompt 约束不足以阻止幻觉；加入输出后校验形成闭环。

### D5 历史快照驱动的稳定性结论
`model-1` 在历史快照充足时（F2：3 期）SHALL 输出等级序列趋势、掉级风险等级与稳定性结论；LLM 上下文必须包含 `modules`（历史相关模块有值时），并禁止把已可判定的稳定性说成"缺少历史"。历史不足时保持现有 `insufficient_history` 契约文案。
- 备选：无（契约已要求，属执行回归）。

### D6 会话上下文沉淀（已知前提注入）
当同一会话、同一地块的**上一轮**已发布任一模特结果（如 Q3 障碍度含「土壤酸碱度 0.14」）对应本问题相关字段时，SHALL 将其作为「已知前提」注入本轮 prompt，使 Q4 类回答能引用上一轮的障碍度结论并解释「障碍度≠实测 pH」的语义差异，消除跨轮矛盾观感。
- 备选：仅靠 `conversation_history` 让 LLM 自行记忆。缺点：前置前缀（确定性字段答案）已证明无法被 LLM 反向利用；显式注入更可控。

## Risks / Trade-offs

- [D1 关键词保底可能误伤「这块地怎么样/肥力如何」类复合问题] → 保底仅限定于明确的稳定性关键词集，不加宽；「这块地怎么样」继续走 type-2 向量/LLM 判定。
- [D2 确定性前缀与 LLM 正文并存可能重复] → 前缀只输出「pH+分级+是否严重」，LLM 禁止重复该信息，仅做扩展（契约明确）。
- [D4 白名单太严可能误杀合法字段（如模型结果确含未知新字段）] → 白名单以「模型 result 实际键 ∪ 标准标签表」动态生成，数据驱动，而非静态常量。
- [D6 注入上下文可能串地块/泄漏] → 仅当新对象 id 与上一轮对象 id 相同且属同一 `conversation_id` 时注入。
- [F7 历史回归风险（未提交 + revert 历史）] → 本轮含两个动作：先提交工作区现有修复；新增 4 个会话级回归断言（Q1 稳定性、Q2 等级、Q3 排序渲染、Q4 酸化实测），CI 阻止再次 Revert。

## Migration Plan

1. `git add` 并提交当前未提交改动（nodes/orchestrator/output_contract/parcel_field_query/routing/manager/versioned_results + public_numbers.py），保住现有修复成果。
2. 按依赖顺序实施：D4（字段渲染）→ D2（model-4 前缀）→ D5（稳定结论）→ D3（空正文兜底）→ D1（路由保底）→ D6（会话上下文）。
3. 每步补充/更新 `tests/` 断言（含 `test_parcel_field_query.py`、`test_agent_integration.py`、会话级集成断言），运行 `pytest` 相应用例。
4. 验收：用四个基准问题（稳不稳/等级/障碍度排序/酸化严重吗）重放，断言四项契约：
   - Q4 回复包含实测 pH≈5.17 与「强酸性」判定；
   - Q1 回复包含稳定性结论（历史充足）或契约降级文案；
   - Q3 回复无 dict 字面量、无「耕作制度」、障碍度有序；
   - 所有回复正文非空。
5. 回滚策略：每步独立小提交；若回退需要，仅回退该步提交；D1/D2 为行为变更如引发布线上问题，可先回退 `routing.py` 保底（保守），其余保留。

## Open Questions

- OQ1: `ROUTING_MODE=llm` 下「我的田酸化严重吗」的 LLM 初判 result/reason 是什么？（`routing_decision_log` 无今日记录——需在实施时补一条今日实测，确认 Q4 并非被路由到 RAG。）
- OQ2: model-2 快照 4等/0.7876 与正式评算 5等/0.8425 的口径差异，是否由产品确认以正式评算为准？（影响 Q1/Q2 是否需提示"档案快照与最新评算不一致"。）
- OQ3: 会话级断言应挂在 SSE 端到端（需真实 LLM）还是单元层（mock LLM）？倾向：单元层为主，端到端手工验收，避免 CI 依赖外部 LLM。
