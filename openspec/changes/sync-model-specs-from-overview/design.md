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
