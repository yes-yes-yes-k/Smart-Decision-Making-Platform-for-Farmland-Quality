# Brainstorm Summary

- Change: sync-model-specs-from-overview
- Date: 2026-07-24

## 确认的技术方案

- **Scenario 粒度**：提炼版（约 30 个），从 xlsx 3 角色×5 问题经典问题提炼核心行为，非逐个对应。delta spec 已采用此方式（每模型 4-7 个 scenario）。
- **模型6 处理**：xlsx 模型6 输入/输出/经典问题完全空白，保留现有 FertilityMLAgent 实现（输入输出+7 个 scenario），spec 名称改为「耕地综合地力改良提升模型」（xlsx 名称），标注「xlsx 未填写，基于现有实现」。ML 预测能力不丢失。
- **Agent 代码修改**：最小化改动——仅修改 6 个 agent 的 `answer_question` 回复模板对齐 xlsx 经典回复 + 更新 `nodes.py` 关键词覆盖 xlsx 经典问题。不重构架构，不修改 router.py 路由结构。

## 关键取舍与风险

- 模型6 xlsx 空白 → 保留现有实现，spec 标注来源差异（非 xlsx 来源）
- scenario 提炼版 vs 完整版 90 个 → 提炼版工作量适中，覆盖核心行为；完整版含模型6 无法生成
- agent 回复质量依赖 LLM → 经典问题回复模板写入代码作为 fallback，LLM 不可用时降级
- xlsx 模型2-5「是否完成填写」=否 → 以现有内容为准，标注待补充

## 测试策略

- **spec 一致性测试**：验证 delta spec 输入输出与 xlsx 一致（模型1-5），模型6 标注非 xlsx 来源
- **关键词路由测试**：xlsx 经典问题能正确路由到对应 question_type 和模型
- **agent Q&A 测试**：6 个 agent 能回答 xlsx 3 角色经典问题（回复模板覆盖）
- **回归测试**：全量测试不破坏现有功能（model_6_execution SOC/Dose 预测不受影响）

## Spec Patch

- 更新 `design.md` D3：scenario 粒度从「3 角色×5 问题=90 个」改为「提炼版约 30 个」，与 delta spec 实际一致
