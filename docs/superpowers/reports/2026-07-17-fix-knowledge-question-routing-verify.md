# 验证报告：fix-knowledge-question-routing

**日期**：2026-07-17
**Change**：fix-knowledge-question-routing
**工作流**：hotfix
**验证模式**：light

## 改动概述

修改 `framework/agents/nodes.py` 中两处问题分类逻辑，使知识性问题正确路由到 RAG 路径：
1. `_identify_question_type_keyword` L132：默认返回值从 type 1（酸化评估）改为 type 0（RAG）
2. `_identify_question_type_vector` L117：向量相似度阈值从 0.5 提高到 0.75

## 轻量验证结果（6 项）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务已完成 | PASS | 无 `- [ ]` 未勾选项 |
| 2 | 改动文件与 tasks.md 一致 | PASS | git diff 显示仅 framework/agents/nodes.py（2 insertions, 2 deletions） |
| 3 | 编译通过 | PASS | `from framework.agents.nodes import identify_question_type, route_models` 成功 |
| 4 | 相关测试通过 | PASS | "耕地质量评价的标准是什么" → type=0, route=rag_chat（断言通过，exit code 0） |
| 5 | 无明显安全问题 | PASS | 仅修改返回值和阈值，无硬编码密钥或 unsafe 操作 |
| 6 | 代码审查 | SKIP | review_mode: off（hotfix 预设跳过自动审查） |

## 测试详情

```
=== Keyword-based routing ===
  [PASS] knowledge question -> RAG: '耕地质量评价的标准是什么' -> type=0, relevance=0.33
  [PASS] knowledge question -> RAG: '耕地质量评价包括哪些指标' -> type=0, relevance=0.33
  [PASS] treatment question -> type 2: '如何治理强酸性耕地' -> type=2, relevance=1.00
  [PASS] acidification assessment -> type 1: '全省耕地酸化程度如何' -> type=1, relevance=0.67
  [PASS] nitrogen impact -> type 3: '施氮肥会导致土壤pH下降多少' -> type=3, relevance=1.00

=== Full routing (with embeddings) ===
  [PASS] knowledge question -> RAG: '耕地质量评价的标准是什么' -> type=0, relevance=0.64
  [PASS] knowledge question -> RAG: '耕地质量评价包括哪些指标' -> type=0, relevance=0.71
  [PASS] treatment question -> type 2: '如何治理强酸性耕地' -> type=2, relevance=1.00
  [PASS] acidification assessment -> type 1: '全省耕地酸化程度如何' -> type=1, relevance=1.00
  [PASS] nitrogen impact -> type 3: '施氮肥会导致土壤pH下降多少' -> type=3, relevance=1.00
```

## 结论

验证通过。知识性问题正确路由到 RAG 路径，计算性问题不受影响。
