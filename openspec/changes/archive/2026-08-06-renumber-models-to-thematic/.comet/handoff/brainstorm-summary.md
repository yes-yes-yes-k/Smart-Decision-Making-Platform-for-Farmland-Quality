# Brainstorm Summary

- Change: renumber-models-to-thematic
- Date: 2026-08-06

## 确认的技术方案

一次性全量重编号策略（big-bang），不保留旧 agent_id 别名。

- capabilities.py：重写 PROFESSIONAL_CAPABILITIES，5 个能力按新编号排列，question_type 1-5
- routing.py：关键词映射按新 question_type 重新编号，移除 type 4（SOC/Dose）和 type 6（潜力）
- exclusive_rules.py：移除 model-2/model-6 相关规则，更新剩余规则目标编号，易混淆对调整为 model-1/5 和 model-2/3
- manager.py：AgentManager 移除 2 个 Agent，剩余 5 个按新 agent_id 注册
- orchestrator.py / nodes.py：工作流图和路由节点引用更新
- 测试：全量更新硬编码 model-N/question_type 引用

## 关键取舍与风险

- 不保留旧 agent_id 别名：agent_id 是内部标识，API 对外返回 model_id（字符串不变），影响可控
- question_type 编号变化：运行时路由值不持久化，无影响
- 关键词冲突：type 1（障碍）和 type 5（等级）均含"障碍"关键词，但"障碍诊断/因素/类型" vs "障碍度/因子/主要障碍"可区分，排他规则兜底

## 测试策略

- 更新 test_question_type_keywords.py：model-N 引用更新为新编号，易混淆对调整为 model-1/5 和 model-2/3
- 更新 test_exclusive_rules.py：排他规则测试同步更新
- 更新 test_multi_agent.py：Agent 注册和调用断言更新
- 路由相关套件全部通过为验收标准

## Spec Patch

无。delta spec 已在 open 阶段完整定义。
