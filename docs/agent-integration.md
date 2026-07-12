# 未来 Agent 接入说明

## 接入定位

当前仓库不实现 Agent，只提供未来 Agent 可调用的基础能力。Agent 接入时应把这些能力视为确定性工具，而不是自然语言问答服务。

## 建议工具列表

| 工具名 | 对应能力 | 输入 | 输出 |
| --- | --- | --- | --- |
| `get_county_overview` | 县域总览 | `area_code` | 图层、区域、来源和可靠性 |
| `diagnose_county` | 县域诊断 | `topic`、`area_code`、可选坐标 | 结构化诊断结果 |
| `build_report_summary` | 结果整理 | 成功诊断结果 | 摘要、发现、建议、行动项 |
| `verify_standalone_runtime` | 运行时校验 | 无 | 非侵入式检查结果 |

## 推荐调用顺序

1. 调用 `verify_standalone_runtime`，确认当前能力可独立运行。
2. 调用 `get_county_overview`，获取区域、图层和来源上下文。
3. 根据用户意图映射 `topic`，调用 `diagnose_county`。
4. 将诊断结果传给 `build_report_summary`，生成可展示或可汇报内容。

## 主题映射建议

| 用户意图 | `topic` |
| --- | --- |
| 酸化严重、pH 偏低、土壤酸化 | `acidification` |
| 质量现状、总体情况、一张图 | `quality` |
| 怎么治理、怎么提升、优先措施 | `improvement` |

## Agent 侧注意事项

- 不要把 `demo_stub` 结果表述为真实模型结论。
- 当 `fallback.used=true` 时，应在回答中说明哪些字段使用了回退。
- 当接口返回 `status=error` 时，应优先展示 `error.code` 和 `error.message`。
- 后续接入真实模型时，应保持当前字段名称稳定，避免破坏已有 Agent 工具封装。
