## Context

当前系统注册了 7 个专业模型（model-1~7），其 agent_id 编号与实际专题模型编号不一致。实际专题模型仅有 5 个（障碍诊断、酸化改良、有机质提升、稳定性风险、质量等级），其中 model-2（提升潜力评估）和 model-6（肥力 SOC/Dose 预测）为占位符模型。

现有 question_type 到 model 的映射为非一一对应（1→model-1、2→model-4、3→model-3、4→model-6、5→model-7、6→model-2、7→model-5），增加了路由逻辑的复杂性。

## Goals / Non-Goals

**Goals:**
- 将 agent_id 重新编号，使其与专题模型编号一一对应：model-1=障碍诊断、model-2=酸化改良、model-3=有机质提升、model-4=稳定性风险、model-5=质量等级
- 移除占位符模型 model-2（improvement-potential-assessment）和 model-6（fertility-soc-dose-prediction）
- question_type 从 1-7 重新编号为 1-5，与新 model 编号一一对应
- 更新排他规则、路由关键词、API 响应和测试套件

**Non-Goals:**
- 不改变 model_id 字符串标识符（如 obstacle-diagnosis 保持不变）
- 不改变 Agent 内部实现逻辑
- 不改变非专业能力（spatial-structure-analysis, soil-indicator-analysis, multi-factor-collaborative-improvement）
- 不实现新的路由策略或排他规则逻辑

## Decisions

### 决策 1：agent_id 一一对应专题模型编号

新映射关系：
| agent_id | 专题模型 | model_id（不变） | 原 agent_id |
|---|---|---|---|
| model-1 | 障碍诊断 | obstacle-diagnosis | model-3 |
| model-2 | 酸化改良 | acidification-remediation | model-4 |
| model-3 | 有机质提升 | organic-matter-improvement | model-5 |
| model-4 | 稳定性风险 | stability-risk-evaluation | model-1 |
| model-5 | 质量等级 | quality-grade-evaluation | model-7 |

**理由**：agent_id 与专题模型编号一一对应，消除编号混乱，便于沟通和维护。

### 决策 2：question_type 重新编号为 1-5

新映射：1→model-1（障碍诊断）、2→model-2（酸化改良）、3→model-3（有机质提升）、4→model-4（稳定性风险）、5→model-5（质量等级）。type 0 仍为 RAG。

**理由**：question_type 与 agent_id 一一对应简化路由逻辑，不再需要非一一对应的映射表。

### 决策 3：移除占位符模型

移除 model-2（PotentialAssessmentAgent）和 model-6（FertilityMLAgent）及其所有相关代码：capabilities 注册、routing 关键词、exclusive_rules 条目、orchestrator 注册、manager 注册、测试用例。

**理由**：这两个模型为占位符，没有对应的实际专题模型，移除后系统更清晰。

### 决策 4：排他规则更新

排他规则中原引用 model-2（潜力）和 model-6（有机质投入量）的条目移除。剩余排他规则的 model 编号更新为新编号。易混淆对从 model-3/7、model-2/7、model-4/6 调整为 model-1/5（障碍诊断 vs 质量等级）、model-2/3（酸化 vs 有机质，如有重叠）。

**理由**：移除模型后排他规则需同步清理，避免引用不存在的模型。

### 决策 5：model_id 字符串保持不变

`model_id`（如 obstacle-diagnosis、acidification-remediation）保持不变，仅 `agent_id`（model-N）重新编号。LEGACY_MODEL_ALIASES 保持不变。

**理由**：model_id 是对外公开的稳定标识，改变会破坏 API 消费者。agent_id 是内部标识，可安全重新编号。

## Risks / Trade-offs

- [question_type 编号变化可能影响已存储的对话历史] → question_type 为运行时路由值，不持久化存储，无影响
- [排他规则测试需全面更新] → 测试中硬编码的 model-N 引用全部同步更新，确保覆盖率不降
- [API 响应中 agent_id 变化] → agent_id 为内部标识，API 响应主要返回 model_id，影响可控
- [移除模型可能导致导入错误] → 全面清理 import 和注册引用，确保无悬空引用
