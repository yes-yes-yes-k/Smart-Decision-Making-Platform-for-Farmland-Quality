## 1. 五维路由特征扩展

- [x] 1.1 在 `framework/agents/capabilities.py` 的 `ProfessionalCapability` 中增加 `analysis_scale`（省/县/片区/地块）与 `data_type`（指标数据/评价结果/处方用量）字段，并为 7 个 capability 填充默认维度
- [x] 1.2 新增 `framework/agents/routing.py` 独立路由模块，迁移 `identify_question_type`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`check_relevance` 等判定逻辑，保持对外函数签名不变
- [x] 1.3 在 `framework/agents/nodes.py` 中改为从 `routing.py` 导入路由函数，保留图节点状态组装与分支调度

## 2. 排他规则配置

- [x] 2.1 新增排他规则配置文件（如 `framework/agents/exclusive_rules.py`），以数据驱动方式声明 model-3/7、model-2/7、model-4/6 三组易混淆对及其判别条件
- [x] 2.2 实现排他规则判定逻辑：现状评价→model-3；潜力→model-2；有机质投入量→model-6；酸化调理剂→model-4；稳定性风险→model-1；质量等级评价→model-7
- [x] 2.3 实现「模型边界待确认」降级状态 `routing_status: "boundary_pending"`，重叠无法消解时返回显式降级而非自行选择

## 3. 路由集成与 API 响应

- [x] 3.1 在 `route_models` 分支中处理「模型边界待确认」降级信号，不调用任一易混淆专业 Agent
- [x] 3.2 在 `aggregate_results` 中透传 `routing_status` 与「模型边界待确认」提示到 `/api/v1/chat/` 响应结构
- [x] 3.3 运行现有测试确认五维路由叠加不破坏既有 `question_type` 1:1 路由行为

## 4. 路由测试集扩充

- [x] 4.1 扩充 `tests/test_question_type_keywords.py`，新增 model-3/7 易混淆对测试（≥20 条正例 + 反例）
- [x] 4.2 新增 model-2/7 易混淆对测试（≥20 条正例 + 反例）
- [x] 4.3 新增 model-4/6 易混淆对测试（≥20 条正例 + 反例）
- [x] 4.4 新增排他规则与「模型边界待确认」降级状态测试
- [x] 4.5 运行全部路由测试并生成扩充报告，确认整体正确率达标