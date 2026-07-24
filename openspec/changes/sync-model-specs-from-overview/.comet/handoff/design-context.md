# Comet Design Handoff

- Change: sync-model-specs-from-overview
- Phase: design
- Mode: compact
- Context hash: 4a19846cdf0ffa919bf79b581b21af75468b60276a4f2141b63ce30c5ac8471b

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/sync-model-specs-from-overview/proposal.md

- Source: openspec/changes/sync-model-specs-from-overview/proposal.md
- Lines: 1-28
- SHA256: 2ae0e325894e8e7599234ac126e61670b2bf08da0fc58df7e35a6db3237f7607

```md
## Why

`专业模型总览表(2).xlsx` 更新了六种专业模型的输入输出定义和领域涉及问题（省/县/农户三角色经典 Q&A），但当前系统的 spec 和 agent 代码与 xlsx 存在差异：模型 6 名称不一致（spec 为"耕地肥力机器学习预测模型"，xlsx 为"耕地综合地力改良提升模型"）、各模型输入输出未对齐 xlsx 详细定义、3 角色经典问题未覆盖。需要同步更新以确保 spec 和代码与权威文档一致。

## What Changes

- 更新 `professional-model-agents` spec 中六种模型的输入输出定义，对齐 xlsx 的数据名称、格式、来源
- 更新 model 6 规格名称为"耕地综合地力改良提升模型"（以 xlsx 为准），FertilityMLAgent 的 ML 预测作为内部实现保留
- 新增 3 角色经典问题场景（省市管理端、县域执行端、农户种植端）到各模型的 scenario 中
- 同步修改 agent 代码的 `answer_question` 逻辑和 `nodes.py` 的问题类型关键词/路由，确保能回答 xlsx 中定义的经典问题
- **BREAKING**: model 6 spec 名称从"耕地肥力机器学习预测模型"回退为"耕地综合地力改良提升模型"

## Capabilities

### New Capabilities

（无新增能力，均为现有能力的修改）

### Modified Capabilities
- `professional-model-agents`: 更新六种专业模型的输入输出定义（对齐 xlsx）、model 6 名称回退为"耕地综合地力改良提升模型"、新增 3 角色经典问题场景
- `role-based-routing`: 更新问题类型关键词和路由逻辑，覆盖 xlsx 中 3 角色的经典问题路由

## Impact

- **修改 spec**: `openspec/specs/professional-model-agents/spec.md`（6 个模型定义）、`openspec/specs/role-based-routing/spec.md`（路由规则）
- **修改代码**: `framework/agents/specialized/*.py`（各 agent 的 answer_question）、`framework/agents/nodes.py`（问题类型关键词）、`framework/agents/router.py`（角色路由）
- **无新增依赖**: 仅修改现有代码逻辑
- **运行时影响**: agent 回答内容将更贴近 xlsx 定义的领域问题；model 6 的 spec 名称变更不影响 API 接口

```

## openspec/changes/sync-model-specs-from-overview/design.md

- Source: openspec/changes/sync-model-specs-from-overview/design.md
- Lines: 1-55
- SHA256: 4722c54c72336b298c071dfdb52c2fe44c6c89857431048bde53cbb58b5a5fba

```md
## Context

`专业模型总览表(2).xlsx` 是六种专业模型的权威定义文档，包含：
- 每个模型的输入数据（数据名称、格式、来源）
- 每个模型的输出数据（数据名称、格式）
- 3 角色经典问题与回复（省市管理端、县域执行端、农户种植端）

当前系统刚完成 `add-model-6-fertility-ml`（将 model 6 从 ComprehensiveImprovementAgent 改为 FertilityMLAgent ML 预测）。xlsx 中 model 6 仍为"耕地综合地力改良提升模型"，与当前 spec 不一致。用户确认以 xlsx 为准。

## Goals / Non-Goals

**Goals:**
- spec 中六种模型的输入输出定义与 xlsx 对齐
- model 6 spec 名称回退为"耕地综合地力改良提升模型"，FertilityMLAgent 作为内部实现保留
- 新增 3 角色经典问题作为 spec scenario
- agent 代码能回答 xlsx 中定义的经典问题

**Non-Goals:**
- 不导入新数据（属于拆分项 A）
- 不训练新的 ML 模型
- 不修改 model 6 的 ML 预测核心逻辑（model_6_execution）
- 不修改 API 路由结构

## Decisions

### D1: Model 6 名称处理 — 以 xlsx 为准
**选择**: spec 中 model 6 名称使用"耕地综合地力改良提升模型"（xlsx 版），FertilityMLAgent 的 ML 预测作为内部实现保留
**理由**: xlsx 是权威文档，用户确认以 xlsx 为准。FertilityMLAgent 的 SOC/Dose 预测能力不丢失，作为 model 6 综合地力评估的内部计算单元。
**备选**: 保留"耕地肥力机器学习预测模型"——与 xlsx 不一致，排除。

### D2: 输入输出定义粒度 — 写入 spec 而非代码
**选择**: 将 xlsx 的详细输入输出列表写入 spec 的 requirement 描述，agent 代码按需引用
**理由**: spec 是契约，定义模型应处理什么；代码实现具体如何处理。详细 I/O 列表放入 spec 可追溯。
**备选**: 写入代码注释——不可追溯，排除。

### D3: 3 角色经典问题 — 作为 scenario 写入 spec（提炼版）
**选择**: 从 xlsx 的 3 角色×5 问题经典问题提炼核心行为 scenario（每模型 4-7 个，共约 30 个），非逐个对应
**理由**: scenario 是可测试的行为契约。提炼版覆盖 3 角色关键问题但不重复变体，工作量适中。完整版 90 个（6 模型×3 角色×5 问题）含模型6 xlsx 空白无法生成，排除。
**备选**: 完整版 90 个逐个对应——模型6 无内容且含大量变体，排除。

### D4: agent 代码修改 — 最小化改动
**选择**: 仅修改 `answer_question` 中的关键词匹配和回复模板，对齐 xlsx 的经典问题；不重构 agent 架构
**理由**: xlsx 的问题是回答内容层面的，不是架构层面的。关键词和模板调整即可覆盖。
**备选**: 重构 agent——范围过大，排除。

### D5: 问题类型关键词更新 — 扩展覆盖
**选择**: 更新 `nodes.py` 的 QUESTION_TYPE_1~4_KEYWORDS，覆盖 xlsx 中各模型对应的经典问题关键词
**理由**: 确保 xlsx 中的经典问题能被正确路由到对应模型。

## Risks / Trade-offs

- [Model 6 名称回退与已归档 change 冲突] → spec 中标注"综合地力改良提升模型（内部使用 FertilityMLAgent ML 预测）"，保留双名映射
- [xlsx 部分 model 未完成填写] → xlsx 显示 model 2/3/4/5/6 的"是否完成填写"=否，但输入输出已有内容；以现有内容为准，标注待补充
- [agent 回复质量依赖 LLM] → 经典问题的回复模板写入代码作为 fallback，LLM 不可用时降级到模板回复
- [spec scenario 粒度] → 采用提炼版约 30 个 scenario（非 90 个完整版），覆盖 3 角色核心行为；模型6 xlsx 空白，scenario 来自现有实现并标注

```

## openspec/changes/sync-model-specs-from-overview/tasks.md

- Source: openspec/changes/sync-model-specs-from-overview/tasks.md
- Lines: 1-48
- SHA256: b006248c3f10234c17a5651ae9a613ab18e5a682b762ccf23e49b4ff46fc3989

```md
# Tasks: sync-model-specs-from-overview

## 1. Spec 文档同步

- [ ] 1.1 更新 `professional-model-agents` delta spec 中 model 1 (StabilityRiskAgent) 的输入输出定义和经典问题场景
- [ ] 1.2 更新 model 2 (PotentialAssessmentAgent) 的输入输出定义和经典问题场景
- [ ] 1.3 更新 model 3 (ProblemIdentificationAgent) 的输入输出定义和经典问题场景
- [ ] 1.4 更新 model 4 (AcidificationRemediationAgent) 的输入输出定义和经典问题场景
- [ ] 1.5 更新 model 5 (OrganicMatterAgent) 的输入输出定义和经典问题场景
- [ ] 1.6 更新 model 6 (FertilityMLAgent) 名称回退为"耕地综合地力改良提升模型"，保留 ML 预测为内部实现
- [ ] 1.7 更新 `role-based-routing` delta spec 的问题类型关键词和路由映射

## 2. 问题类型关键词更新

- [ ] 2.1 更新 `nodes.py` 的 QUESTION_TYPE_1_KEYWORDS 覆盖 xlsx model-1 经典问题关键词（等级稳定性、退化风险、关注清单等）
- [ ] 2.2 更新 QUESTION_TYPE_2_KEYWORDS 覆盖 model-4 经典问题关键词（酸化程度、调理剂、碱性材料等）
- [ ] 2.3 更新 QUESTION_TYPE_3_KEYWORDS 覆盖 model-2/3 经典问题关键词（潜力、障碍因素、主要问题等）
- [ ] 2.4 更新 QUESTION_TYPE_4_KEYWORDS 覆盖 model-5/6 经典问题关键词（有机质、有机肥、肥力、秸秆等）
- [ ] 2.5 验证关键词匹配优先于向量匹配的逻辑（已实现，确认覆盖 xlsx 经典问题）

## 3. Agent 代码对齐

- [ ] 3.1 更新 `StabilityRiskAgent.answer_question` 的回复模板，对齐 xlsx 省市/县域/农户三端经典回复
- [ ] 3.2 更新 `PotentialAssessmentAgent.answer_question` 的回复模板
- [ ] 3.3 更新 `ProblemIdentificationAgent.answer_question` 的回复模板
- [ ] 3.4 更新 `AcidificationRemediationAgent.answer_question` 的回复模板（含 GB/T 42817-2023 标准引用）
- [ ] 3.5 更新 `OrganicMatterAgent.answer_question` 的回复模板
- [ ] 3.6 更新 `FertilityMLAgent.answer_question` 的回复模板（保留 ML 预测，对齐综合地力描述）

## 4. 路由与角色映射

- [ ] 4.1 确认 `RoleRouter` 的 3 角色路由（province_admin/county_executor/farmer）与 xlsx 三端一致
- [ ] 4.2 更新 `router.py` 确保省市管理端和县域执行端角色能路由到对应模型集合
- [ ] 4.3 验证农户种植端角色路由到 model-4/5/6

## 5. 测试

- [ ] 5.1 创建 `tests/test_model_specs_sync.py` 测试各模型 spec 与 xlsx 的输入输出定义一致性
- [ ] 5.2 更新 `tests/test_question_type_keywords.py` 测试 xlsx 经典问题的路由正确性
- [ ] 5.3 创建 `tests/test_agent_classic_qa.py` 测试各 agent 能回答 xlsx 3 角色经典问题
- [ ] 5.4 运行全量测试确保不破坏现有功能

## 6. 集成验证

- [ ] 6.1 验证 model 6 spec 名称已回退为"耕地综合地力改良提升模型"
- [ ] 6.2 验证 FertilityMLAgent ML 预测功能正常（SOC/Dose 预测不受影响）
- [ ] 6.3 验证 6 个 agent 的 answer_question 能返回对齐 xlsx 的回复
- [ ] 6.4 验证问题类型关键词覆盖 xlsx 经典问题

```

## openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md

- Source: openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md
- Lines: 1-167
- SHA256: a39374ba9416a40b4c655042503b72da292dd8bb648657114b6b76427e1d7975

[TRUNCATED]

```md
## MODIFIED Requirements

### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量等级稳定性与退化风险识别模型」，负责评价耕地质量等级稳定性并识别退化风险。

**模型输入**（来源：xlsx 总览表）：
- 广东省-市-县行政边界（面 shp）、三普耕地评价单元（面 shp）、耕地质量等级及综合指数（shp 属性）、11 个评价指标及权重（pH、有机质、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层）、施肥措施单价、酸化治理措施单价

**模型输出**（来源：xlsx 总览表）：
- 等级边界安全度、指标支撑均衡度、关键指标临界度、空间邻域一致性、历史变化趋势、掉级风险、关键因子退化风险、退化空间集聚风险、持续低质风险

#### Scenario: 等级稳定性评价
- **WHEN** 用户询问"查询区域内耕地质量等级整体稳定吗？"
- **THEN** 智能体 SHALL 返回稳定性总体评价，包括稳定性较高、一般、较弱耕地面积及占比，并与上一级或同级区域进行对比

#### Scenario: 退化风险识别
- **WHEN** 用户询问"查询区域内哪些高等级耕地存在退化风险？"
- **THEN** 智能体 SHALL 返回一至三等高等级耕地中稳定性偏弱或退化风险较高的区域、面积、占比、排序和主要风险来源

#### Scenario: 县域稳定性薄弱片区
- **WHEN** 县域执行端用户询问"本县哪些乡镇或地块等级稳定性较弱，需要现场复核？"
- **THEN** 智能体 SHALL 输出稳定性较弱的乡镇、村或地块清单，说明当前等级、稳定性类型、面积规模和是否接近等级边界

#### Scenario: 农户地块稳定性判断
- **WHEN** 农户询问"我的这块田质量等级稳不稳？"
- **THEN** 智能体 SHALL 输出该地块当前耕地质量等级、等级稳定性类型，并用通俗语言说明是"比较稳""一般稳"还是"不太稳"

#### Scenario: 重点关注清单
- **WHEN** 用户询问"查询区域内哪些对象需要纳入重点关注清单？"
- **THEN** 智能体 SHALL 输出需要持续关注的县区、乡镇、村或地块清单，说明其等级稳定性、退化风险等级、风险类型、主要风险来源和后续模型调用建议

### Requirement: PotentialAssessmentAgent 智能体
系统 SHALL 实现 `PotentialAssessmentAgent` 智能体，对应模型2「耕地质量提升潜力评估模型」，负责评估耕地质量提升潜力和计算障碍度值。

**模型输入**（来源：xlsx 总览表）：
- 地块唯一编码、地块经纬度、pH值、有机质、有效磷、速效钾、土壤容重、有效土层厚度、耕层质地、质地构型、灌溉能力、排水能力、地形部位、耕地质量等级、pH增加值（模型4传参）、有机质增加值（模型5传参）

**模型输出**（来源：xlsx 总览表）：
- 潜在pH值、潜在有机质、潜在有效磷、潜在速效钾、潜在土壤容重、潜在有效土层厚度、潜在耕层质地、潜在灌溉能力、潜在地形部位、潜在排水能力、潜在耕地质量等级、11 个评价指标的潜在障碍度值

#### Scenario: 提升潜力评估
- **WHEN** 用户询问"辖区耕地质量提升的总体潜力有多大？可增产多少粮食？"
- **THEN** 智能体 SHALL 回答耕地质量平均可从 xx 等提升至 xx 等，可改善面积 xx 万亩，粮食增产潜力约 xx 万吨

#### Scenario: 目标 pH 计算
- **WHEN** 智能体接收到当前 pH 值和质量目标
- **THEN** 智能体 SHALL 计算目标 pH 或 pH 增加值，供模型1和模型3使用

#### Scenario: 县域潜力分布
- **WHEN** 县域执行端用户询问"我们县划定的优先改良片区具体在哪几个村？每块潜力多大？"
- **THEN** 智能体 SHALL 输出一幅大比例尺地图，以地块为单元用颜色深浅表示潜力值，选中任一地块弹出信息窗显示村名、地块编号、面积、当前质量等级、目标等级、潜力分值

#### Scenario: 农户地块诊断
- **WHEN** 农户询问"我这块地到底有啥毛病？"
- **THEN** 智能体 SHALL 给出地块耕地质量等级和诊断结论，重点标出地块的主要障碍因子，同时配上示意图

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ProblemIdentificationAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。

**模型输入**（来源：xlsx 总览表）：
- 一级农业区、二级农业区、土壤pH、有机质、pH、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、地块唯一编码、地块经纬度、地块边界、行政区划边界、农田类型（水田/旱地）

**模型输出**（来源：xlsx 总览表）：
- 主要障碍因素、次要障碍因素、pH障碍等级、有机质障碍等级、有效磷障碍等级、速效钾障碍等级、容重障碍等级、耕层质地障碍等级、灌溉能力障碍等级、排水能力障碍等级、地形部位障碍等级、质地构型障碍等级、有效土层障碍等级、障碍因素组合

#### Scenario: 障碍因素识别
- **WHEN** 用户询问"全省耕地质量存在哪些问题？"
- **THEN** 智能体 SHALL 返回全省/市范围内的主要障碍因素、次要障碍因素和障碍组合统计

#### Scenario: 指标障碍等级统计
- **WHEN** 智能体接收到地块指标数据
- **THEN** 智能体 SHALL 输出每个指标的障碍等级（1~10级频数统计），最后一列为该指标是否主要、次要障碍因素

#### Scenario: 县域障碍诊断
- **WHEN** 县域执行端用户询问"县/乡镇里的耕地在哪些方面有问题"
- **THEN** 智能体 SHALL 统计全区域内的信息，每个指标为一行，列为每个指标1~10等级的频数统计，最后一列为是否主要、次要障碍因素

#### Scenario: 农户地块问题
- **WHEN** 农户询问"我这块地有没有问题？"
- **THEN** 智能体 SHALL 用简单语言说明耕地质量等级、列举低等级的指标

```

Full source: openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md

## openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md

- Source: openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md
- Lines: 1-34
- SHA256: 74788d25a95ed151c1d9dc531e85058c53b7ff552e2f41a90ce0ad8d10c2a7b4

```md
## MODIFIED Requirements

### Requirement: Question Type Identification
系统 SHALL 根据用户问题识别问题类型（question_type），路由到对应的专业模型。问题类型关键词 SHALL 覆盖 `专业模型总览表(2).xlsx` 中 3 角色（省市管理端、县域执行端、农户种植端）的经典问题。

问题类型与模型映射：
- TYPE_1（酸化程度/退化风险）→ StabilityRiskAgent (model-1)
- TYPE_2（治理/石灰/改良方案）→ AcidificationRemediationAgent (model-4)
- TYPE_3（氮肥/化肥/酸化原因）→ ProblemIdentificationAgent (model-3) / PotentialAssessmentAgent (model-2)
- TYPE_4（有机肥/施肥/肥力/有机碳）→ FertilityMLAgent (model-6) / OrganicMatterAgent (model-5)

#### Scenario: 识别省市管理端问题
- **WHEN** 用户询问"查询区域内耕地质量等级整体稳定吗？"（省市管理端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_1 并路由到 StabilityRiskAgent

#### Scenario: 识别县域执行端问题
- **WHEN** 用户询问"本县哪些乡镇或地块等级稳定性较弱？"（县域执行端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_1 并路由到 StabilityRiskAgent

#### Scenario: 识别农户种植端问题
- **WHEN** 用户询问"我的这块田质量等级稳不稳？"（农户种植端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_1 并路由到 StabilityRiskAgent

#### Scenario: 识别酸化治理问题
- **WHEN** 用户询问"我的田酸化了，pH是XX，我要施加多少碱性调理剂？"（农户种植端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_2 并路由到 AcidificationRemediationAgent

#### Scenario: 识别有机质培肥问题
- **WHEN** 用户询问"为了提升耕地土壤有机质，有机肥每亩施用量多少？"（农户种植端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_4 并路由到 FertilityMLAgent 或 OrganicMatterAgent

#### Scenario: 关键词优先于向量匹配
- **WHEN** 问题包含具体模型关键词（如"有机肥""酸化程度"）
- **THEN** 系统 SHALL 优先使用关键词匹配路由，即使向量匹配的相关性分数较低

```
