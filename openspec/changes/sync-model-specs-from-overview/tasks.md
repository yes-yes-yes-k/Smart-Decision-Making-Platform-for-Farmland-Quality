# Tasks: sync-model-specs-from-overview

## 1. Spec 文档同步

- [x] 1.1 更新 `professional-model-agents` delta spec 中 model 1 (StabilityRiskAgent) 的输入输出定义和经典问题场景
- [x] 1.2 更新 model 2 (PotentialAssessmentAgent) 的输入输出定义和经典问题场景
- [x] 1.3 更新 model 3 (ProblemIdentificationAgent) 的输入输出定义和经典问题场景
- [x] 1.4 更新 model 4 (AcidificationRemediationAgent) 的输入输出定义和经典问题场景
- [x] 1.5 更新 model 5 (OrganicMatterAgent) 的输入输出定义和经典问题场景
- [x] 1.6 更新 model 6 (FertilityMLAgent) 名称回退为"耕地综合地力改良提升模型"，保留 ML 预测为内部实现
- [x] 1.7 更新 `role-based-routing` delta spec 的问题类型关键词和路由映射

## 2. 问题类型关键词更新

- [x] 2.1 更新 `nodes.py` 的 QUESTION_TYPE_1_KEYWORDS 覆盖 xlsx model-1 经典问题关键词（等级稳定性、退化风险、关注清单等）
- [x] 2.2 更新 QUESTION_TYPE_2_KEYWORDS 覆盖 model-4 经典问题关键词（酸化程度、调理剂、碱性材料等）
- [x] 2.3 更新 QUESTION_TYPE_3_KEYWORDS 覆盖 model-2/3 经典问题关键词（潜力、障碍因素、主要问题等）
- [x] 2.4 更新 QUESTION_TYPE_4_KEYWORDS 覆盖 model-5/6 经典问题关键词（有机质、有机肥、肥力、秸秆等）
- [x] 2.5 验证关键词匹配优先于向量匹配的逻辑（已实现，确认覆盖 xlsx 经典问题）

## 3. Agent 代码对齐

- [x] 3.1 更新 `StabilityRiskAgent.answer_question` 的回复模板，对齐 xlsx 省市/县域/农户三端经典回复
- [x] 3.2 更新 `PotentialAssessmentAgent.answer_question` 的回复模板
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
