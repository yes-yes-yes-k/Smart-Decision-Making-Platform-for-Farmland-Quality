## Why

当前系统有 7 个专业模型（model-1~7），其编号与实际专题模型编号不一致，且其中 model-2（提升潜力评估）和 model-6（肥力 SOC/Dose 预测）为占位符模型，没有对应的实际专题模型。需要将 model 编号与实际专题模型编号一一对应，仅保留 5 个实际专题模型。

## What Changes

- **BREAKING** 重新编号 agent_id，使其与专题模型编号一一对应：
  - model-1：障碍诊断（原 model-3，obstacle-diagnosis）
  - model-2：酸化改良（原 model-4，acidification-remediation）
  - model-3：有机质提升（原 model-5，organic-matter-improvement）
  - model-4：稳定性风险（原 model-1，stability-risk-evaluation）
  - model-5：质量等级（原 model-7，quality-grade-evaluation）
- **BREAKING** 移除占位符模型 model-2（improvement-potential-assessment）和 model-6（fertility-soc-dose-prediction）
- **BREAKING** question_type 从 1-7 重新编号为 1-5，与新 model 编号对齐
- 更新排他规则，移除对 model-2/model-6 的引用，更新所有 model 编号
- 更新路由关键词映射，同步 question_type 新编号
- 更新 API 响应中的 agent_id 和 model 编号
- 更新测试套件中所有硬编码的 model-N / question_type 引用

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `role-based-routing`：question_type 从 1-7 改为 1-5，映射关系从 1→model-1/2→model-4/... 改为 1→model-1/2→model-2/... 一一对应；移除 type 4（SOC/Dose 预测）和 type 6（提升潜力）路由场景
- `routing-exclusive-rules`：排他规则中移除 model-2（潜力）和 model-6（有机质投入量）相关条目；更新所有 model 编号引用
- `callable-thematic-model-stubs`：正式专业模型从 7 个减为 5 个；移除 model-2/improvement-potential-assessment 和 model-6/fertility-soc-dose-prediction
- `professional-model-agents`：Agent 目录从 7 项减为 5 项；agent_id 重新编号；移除 PotentialAssessmentAgent 和 FertilityMLAgent 及其相关场景

## Impact

- `framework/agents/capabilities.py`：PROFESSIONAL_CAPABILITIES 重新编号和裁剪
- `framework/agents/routing.py`：question_type 关键词映射重新编号
- `framework/agents/exclusive_rules.py`：排他规则更新 model 引用
- `framework/agents/nodes.py`：路由节点引用更新
- `framework/agents/orchestrator.py`：Agent 注册和图边更新
- `framework/agents/manager.py`：AgentManager 注册表更新
- `framework/api/routes/chat.py`：API 响应字段更新
- `src/ai_culti_demo/thematic_models.py`：MODEL_SPECS 和能力目录更新
- `tests/test_question_type_keywords.py`：测试用例更新 model/question_type 引用
- `tests/test_exclusive_rules.py`：排他规则测试更新
- `tests/test_multi_agent.py`：多 Agent 测试更新
- `docs/openapi.json`、`docs/api.md`：API 文档更新
