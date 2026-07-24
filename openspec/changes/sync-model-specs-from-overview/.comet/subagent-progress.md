# Subagent Progress Checkpoint — sync-model-specs-from-overview

- Change: sync-model-specs-from-overview
- Date: 2026-07-24
- Phase: build (build 阶段任务全部完成，待 verify)
- Build mode: subagent-driven-development
- TDD mode: tdd
- Review mode: standard
- Isolation: branch (feature/20260724/sync-model-specs-from-overview)

## Current Task

- Plan Task: 全部 build 阶段任务（Task 1-14）已完成 + 最终轻量审查 concerns 已修复；下一步进入 verify 阶段
- OpenSpec Task mapping: 5.4 / 6.1-6.4
- Stage: build-complete → 待 verify
- Risk signals: 无（D5 keyword-priority 已实现并验证；最终审查 2 个 Important 已修复）

## Completed Tasks

- Task 1-9: 已完成（详见此前 commit 历史）
- Task 10: 创建 spec 一致性测试 → commit 4ae6e95；12 passed；无风险信号
- Task 11: 完善关键词路由测试全量覆盖 → commit 9b22245；24 passed；DONE_WITH_CONCERNS（vector 路径正常，keyword fallback 对 2 条问题有缺口）
- Task 11 reviewer: **Approved** — concern 属 pre-existing（Task 4 设计取舍），vector 路径在生产环境正确路由（相似度 0.985/0.992），Plan 明确排除源码修改于 Task 11 范围外；建议作为独立 hardening 任务跟踪，不阻塞
- Task 12: 完善 agent 经典 Q&A 测试全量覆盖 → commit 4cc0b54；28 passed；无风险信号
- Task 13: 全量回归测试 → 179 passed / 0 failed（排除 3 个既有 collection-error 模块：test_function_calling/test_interfaces/test_thematic_models）；model_6.py 无 diff；无需修复
- Task 14: 集成验证 → 6.1 OK / 6.2-6.4 全量回归覆盖 / 62 passed 汇总 / 变更范围符合非目标约束（无 model_6.py、无 api、无数据库脚本改动）
- 最终轻量审查: Approved with concerns → 2 个 Important 已修复（commit 63bc635）：
  - Issue #1 spec/impl 语义不一致：将 identify_question_type 改为关键词优先（D5 第三子句「关键词优先于向量匹配」此前未实现，现已落地，spec 与实现一致）
  - Issue #2 flaky 测试 test_unrelated_question_returns_zero：改为 mock embedding off 确定化（连跑 5 次稳定通过）
  - 附带修复 Task 11 concern：补「哪些问题」「有问题」到 QUESTION_TYPE_3_KEYWORDS，2 条问题现经关键词路径正确路由 TYPE_3（不再依赖 vector）
  - test_keyword_match_priority_over_vector 改为真正验证优先级（monkeypatch 向量冲突，断言关键词胜出）

## 已知环境问题（非本 change 引入，不阻塞）

- test_rag.py::test_vector_store_operations 失败：chroma_db 本地存储 metadata segment compaction 损坏（Rust u64 / SQL BLOB 类型不匹配）。隔离运行也复现，属磁盘上 chroma_db 既有损坏状态，与 nodes.py 路由改动无关。重置 chroma_db 可恢复但会丢失已索引文档，建议作为独立运维任务处理。

## Task 11 Concern 跟踪（已在最终审查修复阶段解决）

- Concern 性质: 潜在脆弱点（keyword fallback 路径对 "全省耕地质量存在哪些问题？" 等返回 TYPE_0），但生产路径（vector 优先）正常
- 影响范围: 仅在 embedding service 不可用时（如离线部署、API Key 失效）暴露
- 修复方案候选: 补 "哪些问题" / "有问题" 关键词到 QUESTION_TYPE_3_KEYWORDS，但需重新验证 test_type_order_no_cross_collision 不被破坏
- 决策: 用户选择「完整实现 D5 keyword-priority」，已在 commit 63bc635 中一并修复——补「哪些问题」「有问题」到 TYPE_3_KEYWORDS，2 条问题现经关键词路径正确路由；test_type_order_no_cross_collision 仍通过。本 concern 关闭。

## Notes

- Task 1-5 已合并到 master（快进合并，master @ 88a313a）
- 已对账 tasks.md：1.1-2.5、3.1-3.6、4.1-4.3、5.1-5.4、6.1-6.4 已全部勾选
- 测试现状：全量 179 passed（test_model_specs_sync 12 / test_question_type_keywords 24 / test_agent_classic_qa 28 / 其他回归 115）
- 既有 collection-error（非本 change 引入）：test_function_calling（langchain 版本）、test_interfaces/test_thematic_models（ai_culti_demo 模块）
- 待办：进入 verify 阶段（comet-verify）或归档
