# localize-chat-public-fields Proposal

## Why

专题模型的结构化计算结果仍会使用 `GGNL`、`DXBW`、`SXJ`、`JHX`、`SOCbe`、`Dose` 等内部字段码。现有规范已经约束专题模型公共结果使用稳定的机器字段，也在综合报告中维护了少量展示映射，但普通聊天总结、确定性降级答复、SSE token、历史消息回放和综合报告没有共享同一套用户展示规则。因此，同一地块的诊断答复可能出现“GGNL（灌溉能力不足）”等技术文本，不适合业务用户阅读。

本变更补齐“机器字段保持稳定、用户可见文本统一中文化”的展示边界。它不修改模型计算、版本化结果或结构化 API 字段，只规范自然语言答复。

## What Changes

- 新增统一的用户展示字段字典，覆盖当前 Model-2 至 Model-5 可能进入自然语言答复的评价、障碍、酸化和培肥字段码。
- 普通答复、确定性摘要、综合报告、`report_draft`、推荐文本和助手历史消息统一使用中文标准字段名称。
- 非流式聊天和 SSE 聊天使用同一转换规则；SSE 必须正确处理 `G` + `GNL` 等跨 token 分片字段码。
- 新助手消息在持久化前转换；既有历史消息在读取及重新进入 LLM 会话上下文时转换，无需批量改写数据库。
- 最终 LLM prompt 明确禁止展示内部字段缩写，但最终输出边界仍执行确定性转换，不能仅依赖 LLM 遵循提示词。
- 结构化 `models`、`result`、审计快照、版本化计算结果和模型输入字段保持原有机器契约，不转换 JSON 键。

## Capabilities

### New Capabilities

- `chat-public-field-labeling`: 统一管理专业字段的中文展示名称，并约束聊天、报告、流式输出、持久化与历史消息的用户可见文本。

### Modified Capabilities

- 无。现有 `thematic-model-output-contract` 继续定义机器可读字段，现有 `multi-agent-orchestrator` 继续定义聊天响应包络；本能力只处理其中的用户可见自然语言文本。

## Impact

- 主要代码：`framework/domain/public_field_labels.py`、`framework/agents/output_contract.py`、`framework/agents/nodes.py`、`framework/agents/orchestrator.py`、`framework/agents/workflows/comprehensive/reporting.py`。
- API 边界：`framework/api/services/chat_service.py`、`framework/api/routes/chat.py`。
- 数据库：无表结构变化；新消息保存中文展示文本，旧消息保留原始存储但读取时中文化。
- API 兼容性：机器可读字段和响应结构不变；仅 `answer`、`report_draft`、文本型 `recommendations` 和助手消息 `content` 的展示文字发生变化。
- 测试：增加字段映射、词边界、确定性摘要、综合报告、持久化边界和跨 SSE 分片场景。

## Non-Goals

- 不修改任何专题模型公式、阈值、输入映射或预计算结果。
- 不重命名结构化 API、模型结果、数据库或审计 JSON 中的机器字段。
- 不将所有英文技术术语一律翻译；只转换已登记且具有明确业务含义的专业字段码。
- 不批量更新历史消息数据库记录。
