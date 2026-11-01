# R2.3 位置先定的选择协议与验证

日期：2026-10-31。完成"实体原文片段/位置先确定，再判关系"的协议层与验证；未运行新模型批次、未写入候选库、未发布断言。语义支持仍为未评估，本批不宣称抽取质量提升。

## 实现

新增 `framework/knowledge_graph/selection_protocol_v2.py`（`selection-protocol-v2`），在冻结的 v2 契约（`research_contract_v2`）之前增加一层"先把引用落到确切位置"的判定：

- **先定位置，再判关系**：`resolve_enumeration` 先把研究上下文与实体提及全部解析成 `(chunk_index, start, end, quote)`，产出不可变 `ledger`；`resolve_decision` 只接受 ledger 中已存在的实体 ID 作为关系端点，端点缺失或跨研究一律拒收。关系判定阶段无法再引入新实体。
- **重复片段必须显式位置**：研究上下文和实体提及只有在块内**唯一出现**时才允许自动定位；出现两次及以上直接 `ambiguous_quote_requires_position`。关系结果与限定词属于科学结论的证据，**无论是否唯一都要求显式 offset**，避免"取第一个匹配"。
- **严格字面匹配**：只用 `str.find` 精确子串，不做大小写折叠、空白归一、Unicode 规范化或相似度打分，从机制上排除"放宽匹配提高通过数"。
- **拒收码化**：`SelectionError` 携带稳定原因码——`unknown_source_chunk`（错块）、`invalid_offsets`（越界）、`span_quote_mismatch`（引用与坐标不一致）、`quote_not_found`（错源或原文不存在）、`ambiguous_quote_requires_position`（歧义）、`unknown_relation_endpoint`、`cross_study_relation_forbidden`、`duplicate_entity_mention`、`duplicate_relation_fact`。
- **无支持关系不静默通过**：`adjudicate_resolution` 把关系分为 accepted / pending / rejected 三档；`direction` 为 `uncertain`/`not_reported` 的进入 pending，最终仍由契约标记 `review_status: pending`、`semantic_support: unreviewed`。
- **与冻结契约组合**：`compile_selection` 先解析再调用 `compile_bundle`，沿用既有的文档哈希、解析版本、块集版本绑定与身份去重，不修改 v2 契约本身。

## 验证

```powershell
py -3.12 -m pytest tests/test_selection_protocol_v2.py -q
```

结果：**15 项通过**。覆盖：

| 组 | 用例 |
| --- | --- |
| 精确定位 | 唯一引用可自动定位；重复引用必须给坐标；给了坐标能选中指定那一次；大小写/空白不同视为不存在；出现位置按序返回 |
| 拒收 | 错块、越界、起止颠倒、引用与坐标不一致、关系证据缺坐标、重复实体提及 |
| 关系顺序 | 未知端点拒收；跨研究端点拒收；adjudication 正确分出 1 accepted / 1 pending / 1 rejected |
| 契约组合 | 解析后的结果通过 v2 契约（`rule_validation: passed`、`published_claims_added: 0`）；实体歧义会阻断关系阶段；文档版本绑定不完整被契约拒收 |

## 限制

1. **只做规则层**：通过只代表坐标与结构合法，不代表原文支持该科学结论；所有关系仍为 pending。
2. **未接真实模型输出**：本批没有运行新的抽取批次，协议尚未在真实模型返回上做批量验证（属 R2.5）。
3. **未接入候选写入**：`compile_selection` 只产出通过校验的记录，不写库；持久化属 R2.6。
4. **待审队列语义**：`pending` 目前以方向字段判定，未做独立的证据强度分级。

## 下一步

R2.4 准备原十篇任务相关全文的实际请求与预算方案；获批后 R2.5 用本协议跑有限批次，逐篇记录拒收原因分布，再进入 R2.6 持久化。
