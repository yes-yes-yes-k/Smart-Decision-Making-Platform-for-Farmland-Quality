## Why

当前系统已启用 LangSmith 远端追踪（覆盖 LLM 调用），但缺少本地持久化调用日志、路由混淆矩阵、路由回归自动化、路由看板与结果追溯链。五维路由（P1）已落地，系统无法量化"正确路由率、重叠 Agent 混淆率、漏调用率"，也无法对"不调用或错调用"进行精准定位与自动回归。P9 目标是补齐本地可观测性闭环。

## What Changes

- 新增本地路由/调用日志落库：记录候选 Agent 列表、路由理由、五维上下文、排他规则命中、降级状态、耗时、失败原因与结果版本。
- 新增混淆矩阵测试：对 model-1/5、model-2/3 两组易混淆对各准备不少于 20 条正反例，输出分类性能统计。
- 扩充路由回归自动化：接入 test_question_type_keywords.py，每次修改提示词、路由规则、接口或模型版本后自动运行并输出混淆矩阵。
- 新增路由看板：实时展示路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率等关键指标。
- 新增结果可追溯链：每个结果均可追溯到数据版本、Agent 版本、参数与调用时间。

## Capabilities

### New Capabilities
- `routing-observability`: 本地路由/调用日志、混淆矩阵、路由回归、路由看板与结果追溯链的完整可观测性能力

### Modified Capabilities
- `langsmith-monitoring`: 在远端追踪基础上补充本地持久化调用日志，形成远端 trace 与本地日志并行覆盖的观测体系

## Impact

- 新增模块：`framework/observability/`（路由日志、混淆矩阵、看板、追溯链）
- 扩展 `framework/agents/router.py` / `exclusive_rules.py`：注入路由观测点
- 扩展测试：`tests/test_question_type_keywords.py`、新增 `tests/test_routing_observability.py`
- 新增回归脚本：`scripts/run_routing_regression.py`
- 依赖：Python 标准库 `logging`/`json`（沿用现有 audit_logger 的 JSON 落盘模式），无新增第三方依赖