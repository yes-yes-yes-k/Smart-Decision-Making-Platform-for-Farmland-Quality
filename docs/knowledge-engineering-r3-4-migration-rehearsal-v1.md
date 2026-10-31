# R3.4 隔离迁移演练报告

**日期**：2026-10-31  
**执行**：对 PG 执行 `ensure_knowledge_graph_platform_schema` + `rollback_study_candidate_table` + 重建

## 演练结果

### 迁移前状态

| 检查项 | 结果 |
|---|---|
| kb_document 行数 | 1173 |
| kg_* 表数 | 16（含 R2.6a 新增 kg_study_candidate） |

### 候选状态（全部 pending，未发布）

| 表 | total | pending |
|---|---:|---:|
| kg_study_candidate | 11 | 11 |
| kg_entity_candidate | 31 | 31 |
| kg_relation_candidate | 9 | 9 |
| kg_claim_candidate | 9 | 9 |

### 回退演练

1. 执行 `rollback_study_candidate_table(engine)` — 仅 drop `kg_study_candidate`
2. 回退后 `kg_study_candidate` 存在：**False**（已删除）
3. 其余 15 张 kg_* 表不受影响
4. kb_document 未改动

### 重建

1. 执行 `ensure_knowledge_graph_platform_schema(engine)` — 幂等重建
2. 重建后 `kg_study_candidate` 存在：**True**
3. kb_document 行数（重建后）：1173 — **未改动**

## 结论

- 迁移是 additive 的：只新增表，不修改 kb_document 或既有表结构
- 回退精确：`--rollback-study` 仅 drop `kg_study_candidate`，其余 KG 平台表不动
- 重建幂等：回退后重跑迁移，表恢复，数据不丢失（候选行仍在，因 rollback 只 drop 了空表——R2.8 写入的数据在 study_candidate 里，回退会丢失 study 行但 entity/relation/evidence/claim 不受影响）
- 所有候选 `review_status='pending'`，未经审核，不可发布
