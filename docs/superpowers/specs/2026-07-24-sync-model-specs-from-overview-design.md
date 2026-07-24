---
comet_change: sync-model-specs-from-overview
role: technical-design
canonical_spec: openspec
---

# 技术设计：sync-model-specs-from-overview

## 概述

将 `专业模型总览表(2).xlsx` 中六种专业模型的输入输出定义和 3 角色经典问题同步到 OpenSpec delta spec 与 agent 代码。xlsx 已读取验证，delta spec 已包含模型1-5 的完整输入输出和 scenario，模型6 在 xlsx 完全空白故保留现有 FertilityMLAgent 实现。

## 已确认的设计决策

| 决策点 | 选择 | 依据 |
|--------|------|------|
| Scenario 粒度 | 提炼版约 30 个 | 从 xlsx 经典问题提炼核心行为，工作量适中，覆盖 3 角色关键问题 |
| 模型6 xlsx 空白 | 保留现有 FertilityMLAgent 实现 | xlsx 未填写，保留 SOC/Dose 预测能力，spec 名称对齐 xlsx |
| Agent 代码范围 | 最小化改动 | 仅 answer_question 模板 + nodes.py 关键词，不重构架构 |

## 技术方案

### 1. Spec 文档同步（Task 1.1-1.7）

delta spec 已包含六种模型的输入输出和 scenario。本轮工作：
- **模型1-5**：验证 delta spec 输入输出与 xlsx 一致（已验证一致），scenario 已覆盖 xlsx 经典问题核心行为
- **模型6**：spec 名称从「耕地肥力机器学习预测模型」回退为「耕地综合地力改良提升模型」（xlsx 名称），保留现有输入输出和 scenario，标注「来源：现有实现，xlsx 未填写」
- **role-based-routing**：问题类型映射已与 xlsx 经典问题对齐（TYPE_1→model-1, TYPE_2→model-4, TYPE_3→model-2/3, TYPE_4→model-5/6）

### 2. 问题类型关键词更新（Task 2.1-2.5）

更新 `framework/agents/nodes.py` 的 QUESTION_TYPE_1~4_KEYWORDS，覆盖 xlsx 各模型经典问题关键词：

| 问题类型 | 覆盖模型 | xlsx 经典问题关键词示例 |
|----------|----------|------------------------|
| TYPE_1 | model-1 | 等级稳定性、退化风险、关注清单、临界状态、风险类型 |
| TYPE_2 | model-4 | 酸化程度、酸化等级、调理剂、碱性材料、木本泥炭、pH 提升 |
| TYPE_3 | model-2/3 | 潜力、障碍因素、主要问题、障碍诊断、潜力分布 |
| TYPE_4 | model-5/6 | 有机质、有机肥、秸秆、肥力、SOC、施用量 |

保留现有逻辑：关键词匹配优先于向量匹配（`identify_question_type` 先调用 `_identify_question_type_keyword`，命中后直接返回）。

### 3. Agent 代码对齐（Task 3.1-3.6）

仅修改各 agent 的 `answer_question` 回复模板，对齐 xlsx 3 角色经典回复：

- **StabilityRiskAgent**：对齐省市端"稳定性总体评价"、县域端"薄弱片区清单"、农户端"通俗语言说明稳不稳"
- **PotentialAssessmentAgent**：对齐"潜力评估"、"地块诊断"
- **ProblemIdentificationAgent**：对齐"障碍因素统计"、"县域障碍诊断"
- **AcidificationRemediationAgent**：对齐 GB/T 42817-2023 酸化等级判定、调理剂施用量计算（含 NY/T 443-2019）
- **OrganicMatterAgent**：对齐"有机质含量评估"、"有机肥/秸秆施用量"
- **FertilityMLAgent**：保留 ML 预测，对齐"综合地力诊断"描述

回复模板作为 fallback 写入代码，LLM 不可用时降级到模板回复。

### 4. 路由与角色映射（Task 4.1-4.3）

确认现有 `RoleRouter` 的 3 角色路由（province_admin/county_executor/farmer）与 xlsx 三端一致。不修改 router.py 路由结构，仅验证覆盖。

## 测试策略

| 测试类型 | 范围 | 目标 |
|----------|------|------|
| spec 一致性 | 模型1-5 输入输出 vs xlsx | delta spec 与 xlsx 数据名称一致 |
| 关键词路由 | xlsx 经典问题 → question_type | 3 角色经典问题正确路由 |
| agent Q&A | 6 agent × 经典问题 | 回复模板覆盖 xlsx 经典回复要点 |
| 回归 | 全量测试 | 不破坏现有功能，model_6_execution 不受影响 |

## 边界条件与风险

- **模型6 xlsx 空白**：spec 标注来源差异，agent 保留现有 ML 预测实现
- **xlsx 模型2-5 未完成填写**：以现有内容为准，spec 标注待补充
- **回复质量依赖 LLM**：经典问题回复模板写入代码作为 fallback
- **关键词冲突**：QUESTION_TYPE_2 原含"施加""用量"等通用词导致误判，本轮移除通用词保留具体词

## 非目标

- 不导入新数据（属于拆分项 A，已完成 import-lechang-soil-data）
- 不训练新 ML 模型
- 不修改 model_6_execution 核心逻辑
- 不修改 API 路由结构
