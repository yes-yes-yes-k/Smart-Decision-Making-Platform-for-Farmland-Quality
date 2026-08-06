---
comet_change: renumber-models-to-thematic
role: technical-design
canonical_spec: openspec
---

# 技术设计：模型编号对齐专题模型编号

## 背景

当前系统注册了 7 个专业模型（model-1~7），其 agent_id 编号与实际专题模型编号不一致。实际专题模型仅有 5 个：障碍诊断、酸化改良、有机质提升、稳定性风险、质量等级。model-2（提升潜力评估）和 model-6（肥力 SOC/Dose 预测）为占位符模型。

## 编号映射

| 新 agent_id | 专题模型 | model_id（不变） | 原 agent_id | 原 question_type | 新 question_type |
|---|---|---|---|---|---|
| model-1 | 障碍诊断 | obstacle-diagnosis | model-3 | 3 | 1 |
| model-2 | 酸化改良 | acidification-remediation | model-4 | 2 | 2 |
| model-3 | 有机质提升 | organic-matter-improvement | model-5 | 7 | 3 |
| model-4 | 稳定性风险 | stability-risk-evaluation | model-1 | 1 | 4 |
| model-5 | 质量等级 | quality-grade-evaluation | model-7 | 5 | 5 |

移除：model-2/improvement-potential-assessment（原 type 6）、model-6/fertility-soc-dose-prediction（原 type 4）

## 实现方案

### 1. capabilities.py

重写 `PROFESSIONAL_CAPABILITIES` 元组：
- 5 个能力按新 agent_id（model-1~5）排列
- question_type 改为 1-5，与新 agent_id 一一对应
- `analysis_scale` 和 `data_type` 字段保留
- `LEGACY_MODEL_ALIASES` 保持不变（字符串标识符未变）
- 移除 model-2/improvement-potential-assessment 和 model-6/fertility-soc-dose-prediction

### 2. routing.py

关键词映射表按新 question_type 重新编号：
- type 1（障碍诊断）：障碍诊断、障碍因素、障碍类型、精准识别、障碍组合、多重障碍、障碍叠加
- type 2（酸化改良）：酸化程度、酸化分区、酸化评价、改良方案、调理剂、酸化治理、改良措施
- type 3（有机质提升）：有机质、有机肥、秸秆还田、培肥、有机质提升
- type 4（稳定性风险）：稳定性、稳定吗、质量稳定、退化风险、持续退化、掉级风险、退化趋势
- type 5（质量等级）：质量等级、几等、等级评价、障碍度、障碍因子、主要障碍、限制因素

移除原 type 4（SOC/Dose/施肥量预测）和 type 6（潜力/提升空间）关键词组。

### 3. exclusive_rules.py

- 移除规则：潜力→model-2、有机质投入量→model-6
- 更新剩余规则的 target model 编号：
  - 现状评价→model-1（原 model-3）
  - 酸化调理剂→model-2（原 model-4）
  - 有机质培肥→model-3（原 model-5）
  - 稳定性风险→model-4（原 model-1）
  - 质量等级评价→model-5（原 model-7）
- 易混淆对调整为：model-1/5（障碍诊断 vs 质量等级）、model-2/3（酸化 vs 有机质）

### 4. manager.py

- 移除 PotentialAssessmentAgent（原 model-2）和 FertilityMLAgent（原 model-6）注册
- 剩余 5 个 Agent 按新 agent_id 注册
- 更新 `QUESTION_TYPE_TO_MODEL_ID` 或等价映射为 1-5 一一对应

### 5. orchestrator.py 和 nodes.py

- 工作流图节点引用更新为新 agent_id
- 路由节点 `route_models` 的分支引用更新
- `boundary_pending_node` 保持不变

### 6. API 路由

- `chat.py`：API 响应中 agent_id 和 question_type 使用新编号
- `models.py`：模型列表 API 返回 5 个模型
- `thematic_models.py`：MODEL_SPECS 移除 fertility-soc-dose-prediction 和 improvement-potential-assessment

### 7. 测试

- `test_question_type_keywords.py`：所有 model-N 引用更新为新编号，移除 model-2/model-6 测试用例，question_type 断言更新为 1-5，易混淆对更新为 model-1/5 和 model-2/3
- `test_exclusive_rules.py`：排他规则测试更新 model 引用
- `test_multi_agent.py`：Agent 注册和调用断言更新

## 关键取舍与风险

1. **不保留旧 agent_id 别名**：agent_id 是内部标识，API 对外返回 model_id（字符串不变），影响可控
2. **question_type 编号变化**：运行时路由值不持久化，无影响
3. **关键词冲突**：type 1（障碍）和 type 5（等级）均含"障碍"关键词，但"障碍诊断/因素/类型" vs "障碍度/因子/主要障碍"可区分，排他规则兜底
4. **model_id 字符串不变**：obstacle-diagnosis、acidification-remediation 等字符串标识符保持不变，API 消费者不受影响

## 测试策略

- 路由相关三文件套件（test_question_type_keywords.py、test_exclusive_rules.py、test_multi_agent.py）全部通过为验收标准
- 全量回归测试确认无新增失败
