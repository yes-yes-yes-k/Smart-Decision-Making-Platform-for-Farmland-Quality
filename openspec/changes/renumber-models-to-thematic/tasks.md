## 1. 核心注册表更新

- [ ] 1.1 更新 `framework/agents/capabilities.py`：重新编号 PROFESSIONAL_CAPABILITIES（model-1=obstacle-diagnosis, model-2=acidification-remediation, model-3=organic-matter-improvement, model-4=stability-risk-evaluation, model-5=quality-grade-evaluation），移除 model-2/improvement-potential-assessment 和 model-6/fertility-soc-dose-prediction，更新 question_type 为 1-5
- [ ] 1.2 更新 `src/ai_culti_demo/thematic_models.py`：MODEL_SPECS 移除 fertility-soc-dose-prediction 和 improvement-potential-assessment 相关条目，更新 NON_PROFESSIONAL_CATEGORIES 引用

## 2. 路由逻辑更新

- [ ] 2.1 更新 `framework/agents/routing.py`：question_type 关键词映射从 1-7 重新编号为 1-5，移除 type 4（SOC/Dose）和 type 6（潜力）关键词组，将原 type 1（稳定性）关键词映射到 type 4，原 type 3（障碍）映射到 type 1，原 type 7（有机质）映射到 type 3
- [ ] 2.2 更新 `framework/agents/exclusive_rules.py`：移除 model-2（潜力）和 model-6（有机质投入量）相关排他规则，更新所有 model 编号引用为新编号，更新易混淆对为 model-1/5 和 model-2/3
- [ ] 2.3 更新 `framework/agents/nodes.py`：路由节点引用更新为新 model 编号和 question_type

## 3. Agent 注册与编排更新

- [ ] 3.1 更新 `framework/agents/manager.py`：AgentManager 注册表移除 PotentialAssessmentAgent（原 model-2）和 FertilityMLAgent（原 model-6），更新剩余 Agent 的 agent_id 为新编号
- [ ] 3.2 更新 `framework/agents/orchestrator.py`：工作流图节点和边引用更新为新 agent_id，移除原 model-2 和 model-6 相关节点

## 4. API 与文档更新

- [ ] 4.1 更新 `framework/api/routes/chat.py`：确保 API 响应中 agent_id 和 question_type 使用新编号
- [ ] 4.2 更新 `framework/api/routes/models.py`：模型列表 API 返回 5 个模型
- [ ] 4.3 更新 `docs/openapi.json` 和 `docs/api.md`：同步模型编号和数量

## 5. 测试套件更新

- [ ] 5.1 更新 `tests/test_question_type_keywords.py`：所有 model-N 引用更新为新编号，移除 model-2/model-6 相关测试用例，question_type 断言更新为 1-5，更新易混淆对为 model-1/5 和 model-2/3
- [ ] 5.2 更新 `tests/test_exclusive_rules.py`：排他规则测试更新 model 引用，移除 model-2/model-6 相关测试
- [ ] 5.3 更新 `tests/test_multi_agent.py`：多 Agent 测试更新 agent_id 引用，移除 model-2/model-6 相关断言
- [ ] 5.4 运行路由相关测试套件验证全部通过
