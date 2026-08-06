## Why

当前路由为两阶段路由（关键词优先 + 向量回退），在重叠模型之间（model-3/障碍诊断与 model-7/质量等级评价、model-2/提升潜力与 model-7/质量等级评价、model-4/酸化调理剂与 model-6/有机质投入量）容易误选，系统无法区分"业务任务、分析尺度、数据类型、预期输出、模型依赖"这五类路由特征。缺少排他规则导致易混淆问题被路由到错误的专业 Agent，且对尚未由专业团队确认的重叠关系（如 model-3 与 model-7 的评价维度重叠）系统会自行选择而非明确降级提示。

## What Changes

- 在 `framework/agents/capabilities.py` 的 `ProfessionalCapability` 中增加**分析尺度**（省/县/片区/地块）与**数据类型**（指标数据/评价结果/处方用量）维度。
- 在 `framework/agents/router.py` 中实现可维护、可版本化的**排他规则配置**：现状评价→model-3；潜力→model-2；有机质投入量→model-6；酸化调理剂→model-4；稳定性风险→model-1；质量等级评价→model-7。
- 实现「模型边界待确认」降级状态：对未由专业团队确认的重叠关系返回显式降级提示，而非自行选择。
- 将路由判定逻辑从 `framework/agents/nodes.py` 模块化为独立路由模块，便于版本管理与回归测试。
- 扩充路由测试集：针对 model-3/7、model-2/7、model-4/6 三组易混淆对，各准备不少于 20 条正例和反例问题。

## Capabilities

### New Capabilities
- `routing-exclusive-rules`: 五维路由特征与排他规则配置，用于消除重叠模型之间的误选，并对未确认的重叠关系提供「模型边界待确认」降级。

### Modified Capabilities
- `role-based-routing`: 现有问题类型路由将升级为五维路由（业务任务-分析尺度-数据类型-预期输出-模型依赖），并引入排他规则与「模型边界待确认」降级状态。

## Impact

- 代码：`framework/agents/capabilities.py`、`framework/agents/router.py`、`framework/agents/nodes.py`（路由逻辑模块化）、新增独立路由模块。
- 测试：`tests/test_question_type_keywords.py` 扩充，新增三组易混淆对测试集。
- API：路由结果可能新增「模型边界待确认」降级状态，影响 `/api/v1/chat/` 响应结构。