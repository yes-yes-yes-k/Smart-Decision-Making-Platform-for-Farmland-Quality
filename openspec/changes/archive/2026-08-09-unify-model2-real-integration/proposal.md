## Why

项目当前把真实的耕地质量评价与潜力分析实现注册为 `model-7`，而公开的专题模型2（`model-2`）仍使用固定模拟指标。这样导致“耕地质量提升潜力评估模型”的公开能力与真实模型实现错位，潜力问题无法使用真实地块数据计算。需要统一模型身份，消除重复的第七个专题入口。

## What Changes

- 将 `farmland_grade_eval` 的真实质量评价、障碍度和潜力分析能力统一公开为 `model-2/improvement-potential-assessment`。
- 让专题模型2按地块编码、结构化指标和县域参数调用真实 Python 计算逻辑，移除固定 `MOCK_INDICATORS` 作为正常结果来源。
- 删除 `model-7/quality-grade-evaluation` 作为独立注册能力、路由目标和公开能力描述；底层模块目录可保留为实现细节。
- 将问题类型路由收敛为 6 个专题模型，质量等级和提升潜力相关问题统一进入 `model-2`，并同步更新 Agent 注册、API 能力目录、文档、验证脚本和测试。
- **BREAKING**：彻底删除 `model-7/quality-grade-evaluation` 标识、路由和兼容别名；公开能力列表和路由中不再保留其历史记录。

## Capabilities

### New Capabilities

无。本次是现有专业模型能力的身份统一和真实实现接入。

### Modified Capabilities

- `openspec/specs/professional-model-agents/spec.md`：将真实质量评价与潜力分析归入 `model-2`，并将正式专题模型数量从 7 项调整为 6 项。
- `openspec/specs/role-based-routing/spec.md`：更新问题类型到 Agent 的映射，移除独立 `model-7` 路由并将相关问题归入 `model-2`。
- `openspec/specs/farmland-quality-grade-evaluation/spec.md`：调整公开模型归属和调用契约，保留底层 Python 评价、单地块潜力及县域潜力函数。
- `openspec/specs/multi-agent-orchestrator/spec.md`：更新 Agent 注册数量、能力枚举和路由行为。

## Impact

- 受影响代码：`framework/agents/capabilities.py`、`framework/agents/manager.py`、`framework/agents/router.py`、`framework/agents/specialized/potential_agent.py`、`framework/agents/specialized/grade_agent.py`、`src/ai_culti_demo/farmland_grade_eval/` 及相关 API 路由。
- 受影响接口：专业能力列表、统一聊天路由、模型执行结果中的 `agent_id/model_id` 和 `agents_invoked`。
- 数据与运行时：继续使用项目内置 CSV；真实计算要求提供 `parcel_code` 或完整结构化指标，数据缺失时返回明确的输入不足/部署错误，而不是伪装成真实结果。
- 测试和文档：所有“7 个专业模型”、`type 5 -> model-7`、`type 6 -> model-2` 的断言和说明都需要按新的六模型契约更新。
