# Proposal: fix-chat-answer-quality — 修复聊天回答质量缺陷（酸化缺数据误报 / 稳定性答非所问 / 字段幻觉）

## Why

聊天智能体对真实地块的回答存在系统性质量缺陷：**数据库确有实测 pH（soil_ph=5.17）与 3 期历史等级快照，回复却报"缺少 pH、无法判断酸化严重程度"**；"我的田质量等级稳不稳，退化风险高吗"只被回答为"5 等"，稳定性与退化风险未答；障碍度排序直接把 Python dict 字面量暴露给用户，且 LLM 正文将"耕层质地"幻觉为"耕作制度"。根因链已由运维证据（生产 DB、会话消息、git 历史）部分确认，需要在路由、模型输出契约、字段直查渲染与降级兜底四层修复。

## What Changes

- **酸化缺数据误报修复（P1）**：Model-4 在三项输入实测存在（SJD=soil_ph=5.17、Hex、Alex）时 SHALL 在结果中携带 `soil_ph` 与 `acidification_level`；回复 SHALL 报告实测 pH 及分级，禁止在已有实测时声称"无实测酸碱度"。对无 pH 数据的真实缺测地块，回复 SHALL 给出明确原因、分级阈值与补测引导，而不是笼统"无法判断"。**BREAKING**：修复 `框架/agents/orchestrator.py` 与 `框架/agents/nodes.py` 中"正文为空只回前缀"的路径，任何回答正文 SHALL NOT 为空。
- **稳定性答非所问修复（P2）**：在 `ROUTING_MODE=llm` 下，当问题同时命中稳定性意图（"稳不稳/退化风险/等级稳定/掉级"）与等级意图时，路由 SHALL 保底到 Model-1（并联动 Model-2 供字段直查），由 LLM 初判覆盖的关键词命中不得被丢弃。当存在 ≥2 期历史等级快照时 Model-1 SHALL 输出稳定性与退化风险结论；历史不足时 SHALL 按契约输出明确原因与补救路径。
- **字段幻觉与 dict 字面量修复（P3）**：障碍度排序字段直查 SHALL 逐项渲染（字段名+数值），禁止 `str(dict)` 字面量；LLM 总结 SHALL 只允许使用模型结果中存在的标准字段名，新增"字段白名单"校验，禁止"耕作制度"式幻觉字段，并补充"耕层质地/质地构型"等别名映射。
- **回归保护**：为上述行为补充自动化验证（会话消息断言、路由保底断言、字段白名单断言），并把工作区未提交的酸化解释恢复改动纳入提交与测试，避免再次被 Revert。**BREAKING**：新增会话消息校验：若地块实测数据存在，助手回复 SHALL NOT 出现"无实测…无法判断"类句式。

## Capabilities

### New Capabilities

（暂无新增能力，问题均落在既有能力契约未覆盖/被回归的场景上）

### Modified Capabilities

- `multi-agent-orchestrator`: 新增"回答正文完整性"需求——最终回答 SHALL 包含业务正文；正文生成失败或为空时 SHALL 使用确定性模型总结兜底，禁止只返回"分析对象/地块前缀"。
- `thematic-model-output-contract`: 修改 Model-4 结果契约——实测输入存在时 `result` SHALL 携带 `soil_ph` 与 `acidification_level`；修改 Model-1 结果契约——历史快照充足时 SHALL 输出稳定性/退化风险结论，禁止"只回等级"。新增"结果字段白名单"需求，禁止输出模型结果中不存在的字段名。
- `llm-routing-judgment`（协作：`routing-exclusive-rules`）: 新增"稳定性复合意图保底"需求——LLM 初判结果 SHALL NOT 覆盖命中稳定性关键词（稳不稳/退化风险/等级稳定/掉级）的复合意图问题；关键词保底 SHALL 在 LLM 初判之后、排他规则之前生效，冲突消解表 `{model-1, model-2} → model-1` 对所有路由模式生效。
- `chat-public-field-labeling`: 修改障碍度排序展示——字段直查对有序字典 SHALL 逐项渲染（`字段名 数值`），禁止输出 Python dict 字面量；补充"耕层质地=耕层质地、质地构型=质地构型"等标准标签映射，防止 LLM 改名或漏项。

## Impact

- 代码：`framework/agents/routing.py`、`framework/agents/exclusive_rules.py`、`framework/agents/nodes.py`、`framework/agents/orchestrator.py`、`framework/agents/output_contract.py`、`framework/agents/parcel_field_query.py`、`framework/agents/specialized/acidification_agent.py`、`framework/agents/specialized/stability_agent.py`、`framework/function_calling/specialized_tools.py`、`framework/domain/calculations/acidification_calculation.py`。
- 数据：Model-4 输入/输出字段语义（`soil_ph`、`acidification_level`、`SJD`）；Model-1 历史快照读取（`parcel_history_snapshot`）。
- 测试：新增会话级回答断言与路由保底断言；现有 `tests/test_parcel_field_query.py` 等字段渲染断言需同步。
- 风险：LLM 初判与关键词保底的优先级变更可能影响少量历史用例，需对照 `routing_decision_log` 回归；修改仅针对回复呈现与结果携带，不改变模型计算内核。
