# Brainstorm Summary

- Change: add-routing-exclusive-rules
- Date: 2026-08-06

## 确认的技术方案

在现有两阶段路由（关键词优先 + 向量回退）之上叠加五维路由判定层（业务任务-分析尺度-数据类型-预期输出-模型依赖），核心是区分「问题分类」与「模型选择」两层职责。

- **决策 A**：`identify_question_type(question)` 扩展为 `identify_question_type(question, context=None)`，context 可选携带 parcel_id/area_code/scale，保持向后兼容。
- **决策 B**：五维特征来源——业务任务=现有 question_type 判定；分析尺度=context.scale 或问题文本；数据类型=上下文推断；预期输出=关键词；模型依赖=排他规则配置。
- **决策 C**：排他规则数据驱动，`exclusive_rules.py` 声明规则列表（pair/discriminator/condition/target），可版本化、可单测。
- **决策 D**：边界待确认降级——排他规则无法消解重叠时返回 `routing_status: "boundary_pending"` + 「模型边界待确认」提示，不调用任何 Agent。
- **决策 E**：模块化——新建 `framework/agents/routing.py`（判定逻辑）+ `exclusive_rules.py`（规则配置），nodes.py 仅保留图节点组装。

## 关键取舍与风险

- [五维特征提取不完整] → 未确定维度回退 question_type
- [排他规则冲突] → 边界待确认降级兜底，禁止静默选择
- [模块化破坏现有测试] → 保持 identify_question_type 签名兼容

## 测试策略

- model-3/7、model-2/7、model-4/6 三组混淆对，各 ≥20 条正例 + 反例
- 排他规则单元测试 + 边界待确认降级测试
- 现有 470 个测试回归通过

## Spec Patch

无