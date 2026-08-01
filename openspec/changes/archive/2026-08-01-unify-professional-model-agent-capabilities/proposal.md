# 提案：统一专业模型与专业智能体能力目录

## Why

当前系统同时维护专题模型目录、`AgentManager` 注册目录和聊天 `question_type` 路由。三者的数量、名称、模型标识和覆盖范围不同：专题模型有 8 项，Agent 有 7 个，正常聊天只路由其中 5 个专业 Agent。这会使同一业务能力在单模型 API 与聊天链路中出现不同口径，也使调用方无法判断结果是否来自真实计算、规则结果或 Demo 占位结果。

本变更以现有 7 个专业 Agent 为正式能力边界，统一专业模型目录、单模型 API、聊天路由和文档的能力定义。空间结构解析、关键指标解析和多项协同提升不与现有 Agent 强行映射，改为独立的辅助或实验性能力。

## What Changes

- 建立以 7 个专业 Agent 为唯一来源的正式专业能力目录。
- 让正式专业模型 API 与聊天 Agent 共享同一能力标识、输入条件、结构化分析结果、可靠性和降级状态。
- 将 7 个专业 Agent 全部纳入明确的 `question_type` 一对一路由。
- 使辅助/实验性专题能力不再混入正式专业模型和聊天路由目录。
- 更新 OpenAPI、接口文档与测试，确保公开契约可复现。

## 非目标

- 不新增第 8 个综合协同 Agent。
- 不改变既有专业计算算法、训练模型、离线预计算或外部 exe 的业务规则。
- 不将空间结构或关键指标能力强行改造成专业 Agent。
- 不改变知识性问题走 RAG、专业问题末尾最多一次 LLM 汇总的机制。

## 正式能力目录

| Agent ID | 正式公开模型 ID | 能力名称 | 聊天问题类型 |
|---|---|---|---:|
| `model-1` | `stability-risk-evaluation` | 稳定性与退化风险识别 | 1 |
| `model-2` | `improvement-potential-assessment` | 耕地质量提升潜力评估 | 6 |
| `model-3` | `obstacle-diagnosis` | 主要问题与障碍诊断 | 3 |
| `model-4` | `acidification-remediation` | 土壤酸化改良 | 2 |
| `model-5` | `organic-matter-improvement` | 有机质培肥提升 | 7 |
| `model-6` | `fertility-soc-dose-prediction` | 肥力 SOC/Dose 预测 | 4 |
| `model-7` | `quality-grade-evaluation` | 耕地质量等级评价 | 5 |

## 影响范围

- 修改 `professional-model-agents`、`agent-base-framework`、`callable-thematic-model-stubs`、`role-based-routing`、`api-documentation-examples` 规格。
- 预计实现阶段会涉及能力注册表、`AgentManager`、问题分类/路由、专题模型入口、专业 Agent、模型 API、OpenAPI、文档和相关测试。
- 现有语义化专题模型 ID 的兼容策略将在实现中显式处理：可无歧义映射的旧 ID 返回弃用提示并映射到正式能力；无 Agent 对应的 ID 改为辅助/实验性分类，不再作为正式专业模型列出。

## 风险与缓解

- `model-5` 培肥建议与 `model-6` SOC/Dose 预测存在关键词重叠：通过问题类型、输入输出边界和测试样例明确区分“治理方案”与“预测值”。
- 不同 Agent 当前结构化结果不一致：增加统一 `analyze(payload)` 契约，再由聊天回答复用其结果，避免从自然语言反解析。
- 旧异常回退会回到多模型组合：移除该组合式回退，失败时返回同一能力的结构化失败/降级信息。
- 变更会影响既有调用方：在 API 文档中列出正式 ID、辅助能力状态和兼容/弃用行为，并用回归测试保护。
