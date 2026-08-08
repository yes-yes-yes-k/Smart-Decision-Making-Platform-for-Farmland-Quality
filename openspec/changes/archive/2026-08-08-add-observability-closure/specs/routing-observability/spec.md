# routing-observability Specification

## ADDED Requirements

### Requirement: 本地路由调用日志落库

系统 SHALL 将每次路由判定记录为本地 JSON 行式日志，包含候选 Agent 列表、路由理由、五维上下文、排他规则命中、降级状态、耗时、失败原因与结果版本。

#### Scenario: 记录一次正常路由

- **WHEN** 一次路由判定完成（命中排他规则且无冲突）
- **THEN** 本地日志追加一条记录，包含 question、question_type、目标 Agent、命中排他规则、routing_status=normal、耗时
- **AND** 记录带唯一 trace_id

#### Scenario: 记录边界待确认降级

- **WHEN** 多条排他规则同时命中且无法消解
- **THEN** 本地日志记录 routing_status=boundary_pending
- **AND** 不记录任何被调用的 Agent 结果

### Requirement: 路由混淆矩阵

系统 SHALL 提供混淆矩阵计算，对 model-1/5、model-2/3 两组易混淆对基于真实标签与预测结果输出 TP/FP/FN/TN、路由正确率与混淆率。

#### Scenario: 计算混淆矩阵

- **WHEN** 输入一组真实标签与预测结果
- **THEN** 输出包含 TP/FP/FN/TN、accuracy、confusion_rate 的统计字典

#### Scenario: 混淆率目标

- **WHEN** 统计两组易混淆对的路由结果
- **THEN** 重叠 Agent 混淆率不高于 3%

### Requirement: 路由回归自动化

系统 SHALL 提供可自动运行的路由回归脚本，对 model-1/5、model-2/3 两组易混淆对各提供不少于 20 条正反例并输出混淆矩阵。

#### Scenario: 运行回归脚本

- **WHEN** 执行路由回归脚本
- **THEN** 对两组易混淆对各运行不少于 20 条正反例
- **AND** 输出混淆矩阵与分类性能统计
- **AND** 退出码反映是否满足正确率与混淆率目标

### Requirement: 路由看板

系统 SHALL 提供看板，展示路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率等关键指标。

#### Scenario: 生成看板

- **WHEN** 执行看板命令
- **THEN** 输出文本看板，包含路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率
- **AND** 可导出为 Markdown 报告

### Requirement: 结果可追溯链

系统 SHALL 使每个结果可通过 trace_id 追溯到数据版本、Agent 版本、参数与调用时间。

#### Scenario: 追溯结果

- **WHEN** 按 trace_id 查询
- **THEN** 返回该次调用的数据版本、Agent 版本、参数与调用时间
- **AND** 结果可追溯率为 100%