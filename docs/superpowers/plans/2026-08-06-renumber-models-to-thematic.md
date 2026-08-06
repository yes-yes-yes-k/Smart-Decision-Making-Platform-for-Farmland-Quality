---
change: renumber-models-to-thematic
design-doc: docs/superpowers/specs/2026-08-06-renumber-models-to-thematic-design.md
base-ref: 6238591761227cdf78a84e611c320cb50b374efb
archived-with: 2026-08-06-renumber-models-to-thematic
---

# 实施计划：模型编号对齐专题模型编号

## Task 1: 更新核心注册表 capabilities.py

### Step 1: 重写 PROFESSIONAL_CAPABILITIES
- [x] 重写 `framework/agents/capabilities.py` 的 `PROFESSIONAL_CAPABILITIES` 元组：
  - model-1: obstacle-diagnosis, question_type=1（原 model-3, type 3）
  - model-2: acidification-remediation, question_type=2（原 model-4, type 2）
  - model-3: organic-matter-improvement, question_type=3（原 model-5, type 7）
  - model-4: stability-risk-evaluation, question_type=4（原 model-1, type 1）
  - model-5: quality-grade-evaluation, question_type=5（原 model-7, type 5）
  - 移除 improvement-potential-assessment 和 fertility-soc-dose-prediction
- [x] 验证 CAPABILITY_BY_AGENT_ID、CAPABILITY_BY_MODEL_ID、CAPABILITY_BY_QUESTION_TYPE 自动更新

### Step 2: 更新 thematic_models.py
- [x] 移除 MODEL_SPECS 中 fertility-soc-dose-prediction 和 improvement-potential-assessment 条目（如有）
- [x] 确认 NON_PROFESSIONAL_CATEGORIES 引用不受影响

## Task 2: 更新路由逻辑 routing.py

### Step 3: 重新编号关键词映射
- [x] 将 QUESTION_TYPE_1_KEYWORDS 改为障碍诊断关键词（原 type 3）
- [x] QUESTION_TYPE_2_KEYWORDS 保持酸化改良关键词（原 type 2，不变）
- [x] 将 QUESTION_TYPE_3_KEYWORDS 改为有机质提升关键词（原 type 7）
- [x] 将 QUESTION_TYPE_4_KEYWORDS 改为稳定性风险关键词（原 type 1）
- [x] QUESTION_TYPE_5_KEYWORDS 保持质量等级关键词（原 type 5，不变）
- [x] 移除 QUESTION_TYPE_6_KEYWORDS（潜力）和 QUESTION_TYPE_7_KEYWORDS（有机质，已迁移到 type 3）
- [x] 更新 REFERENCE_QUESTIONS 字典键从 1-7 改为 1-5
- [x] 更新 _identify_question_type_keyword 函数中的列表引用
- [x] 更新 _identify_question_type_vector 函数中的参考向量引用

## Task 3: 更新排他规则 exclusive_rules.py

### Step 4: 更新排他规则数据
- [x] 移除 model-2（潜力）和 model-6（有机质投入量）相关规则
- [x] 更新剩余规则的 target model 编号：
  - 现状评价→model-1（原 model-3）
  - 酸化调理剂→model-2（原 model-4）
  - 有机质培肥→model-3（原 model-5）
  - 稳定性风险→model-4（原 model-1）
  - 质量等级评价→model-5（原 model-7）
- [x] 更新易混淆对为 model-1/5 和 model-2/3
- [x] 更新 model_id_to_question_type 映射

## Task 4: 更新 AgentManager manager.py

### Step 5: 更新 Agent 注册
- [x] 移除 PotentialAssessmentAgent（原 model-2）和 FertilityMLAgent（原 model-6）注册
- [x] 更新剩余 5 个 Agent 的 agent_id 为新编号
- [x] 更新 _register_agents() 中的依赖关系
- [x] 更新 _load_real_agents() 中的加载逻辑
- [x] 更新 _synthesize_comprehensive_result() 中的 model-1/model-3 引用为新编号
- [x] 更新 _summarize() 中的 model 引用

## Task 5: 更新编排器和节点 orchestrator.py + nodes.py

### Step 6: 更新工作流图
- [x] 更新 orchestrator.py 中的节点和边引用（如有 model-N 引用）
- [x] 更新 nodes.py 中 route_models 的分支引用
- [x] 确认 boundary_pending_node 不需要改动

## Task 6: 更新 API 和文档

### Step 7: 更新 API 路由
- [x] 更新 framework/api/routes/chat.py 中的 model 引用（如有）
- [x] 更新 framework/api/routes/models.py 中的模型列表
- [x] 更新 docs/openapi.json 和 docs/api.md 中的模型编号

## Task 7: 更新测试套件

### Step 8: 更新路由测试
- [x] 更新 tests/test_question_type_keywords.py：
  - 所有 model-N 引用更新为新编号
  - 移除 model-2/model-6 相关测试用例
  - question_type 断言更新为 1-5
  - 易混淆对更新为 model-1/5 和 model-2/3
  - 更新 MODEL4_STEMS 等测试数据引用
- [x] 更新 tests/test_exclusive_rules.py：排他规则测试更新 model 引用
- [x] 更新 tests/test_multi_agent.py：Agent 注册和调用断言更新

### Step 9: 运行测试验证
- [x] 运行 `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q`
- [x] 全部通过为验收标准

