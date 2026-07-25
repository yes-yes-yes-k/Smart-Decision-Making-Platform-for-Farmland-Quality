# Comet Design Handoff

- Change: add-parcel-id-and-type5-coverage
- Phase: design
- Mode: compact
- Context hash: d06f4ab204d19b60a1cb75a42722e3561e78c3e9f9d0166e2ec706e6b15ac37c

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-parcel-id-and-type5-coverage/proposal.md

- Source: openspec/changes/add-parcel-id-and-type5-coverage/proposal.md
- Lines: 1-37
- SHA256: c6d1a69a8f9bfc4e01d75b3d6e138ba348dd601e1a739e9ca5a3c00cd23f2681

```md
## Why

智能体能力验证报告（`verification_full_report.md`）暴露两个验证盲点：(1) model-7（Fortran exe 耕地质量等级评价）从未被触发——`REFERENCE_QUESTIONS` 只覆盖 type 1-4，且 `RoleRouter.ROLE_AGENTS` 三个角色都不含 model-7；(2) 所有 farmer 角色问题返回固定 mock 数据（pH=5.5、有机质=22.0 g/kg），因为 `execute_models` 构建上下文时没有从 `request` 提取 `parcel_id`/`parcel_code` 透传给 `AgentManager.process`，而 model-1/3/4/7 的真实计算路径早已就绪——管道未接通，agents 收不到地块标识符。

根因不是缺少真实计算能力，而是缺少把地块标识符从请求传到 agents 的管道，以及缺少触发 model-7 的问题与路由。

## What Changes

- **`execute_models` 透传地块标识符**：从 `state["request"]` 提取 `parcel_id`（数字字符串，给 model-1/3/4 查 stability_db/diagnosis_db）和 `parcel_code`（字母数字，给 model-7 调 fortran exe）并加入 `context`，让 agents 的真实计算路径能收到地块标识符。
- **farmer 角色追加 model-7**：在 `ROLE_AGENTS['farmer']` 列表追加 `model-7`，使 farmer 问「我的田质量等级」时自动触发 model-7。
- **`REFERENCE_QUESTIONS` 新增 type 5 条目**：补充 3-5 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」），让验证覆盖 model-7。
- **验证脚本预设地块标识符**：`scripts/gen_full_verification_report.py` 为 farmer 问题预设真实 `parcel_id`（如 "1"，来自 stability_db/diagnosis_db）和 `parcel_code`（如 "A0001"，来自 fortran exe 数据库），让验证报告显示真实数据而非 mock。
- **生产 API 接受 `parcel_id`/`parcel_code`**：`POST /api/v1/...` 请求体支持可选的 `parcel_id` 和 `parcel_code` 字段，透传到 orchestrator。
- **双 ID 并存（非破坏性）**：`parcel_id` 与 `parcel_code` 是两套无映射关系的 ID 空间，各管各的。未传时 agents 维持现有 mock + `need_input` 提示行为，不破坏向后兼容。

## Capabilities

### New Capabilities

（无——本次变更是对现有 orchestrator 和路由能力的扩展，不引入新独立能力。）

### Modified Capabilities

- `multi-agent-orchestrator`: `execute_models` 节点新增从 `request` 提取 `parcel_id`/`parcel_code` 并透传到 `context` 的逻辑；`REFERENCE_QUESTIONS` 新增 type 5（质量等级评价）问题条目，使验证覆盖 model-7。
- `role-based-routing`: `ROLE_AGENTS['farmer']` 追加 `model-7`，使 farmer 角色问题能触发耕地质量等级评价。

## Impact

- **代码**：
  - `framework/agents/nodes.py`（`execute_models` 透传逻辑 + `REFERENCE_QUESTIONS` type 5 条目 + `_identify_question_type_keyword` 分支 5）
  - `framework/agents/router.py`（`ROLE_AGENTS['farmer']` 追加 `model-7`）
  - `scripts/gen_full_verification_report.py`（farmer 问题预设 `parcel_id`/`parcel_code`，type 5 问题路由断言）
  - 生产 API 路由文件（接受 request body 的 `parcel_id`/`parcel_code` 并传入 orchestrator.run）
- **API**：`POST /api/v1/...` 请求体新增两个可选字段 `parcel_id`（string，数字格式）和 `parcel_code`（string，字母数字格式）。非破坏性——未传时行为不变。
- **依赖**：无新依赖。复用现有 `stability_db` / `diagnosis_db` / fortran exe 部署。
- **数据**：无 schema 变更。`parcel_id` 用 stability_db/diagnosis_db 现有数字 ID（如 "1"），`parcel_code` 用 fortran exe 数据库现有字母数字代码（如 "A0001"）。两套 ID 无映射关系，各管各的。
- **测试**：新增 type 5 问题路由测试、parcel_id/parcel_code 透传测试、farmer 角色含 model-7 的路由测试。

```

## openspec/changes/add-parcel-id-and-type5-coverage/design.md

- Source: openspec/changes/add-parcel-id-and-type5-coverage/design.md
- Lines: 1-114
- SHA256: 893f4faf418331d660d5f27e1bd0e4cbc27fc07b42f22e6bbc9e042a89d707d9

[TRUNCATED]

```md
## Context

智能体能力验证报告（`verification_full_report.md`）暴露两个验证盲点：

1. **model-7 未被触发**：`REFERENCE_QUESTIONS`（`framework/agents/nodes.py`）只覆盖 type 1-4；type 5（质量等级）的 `QUESTION_TYPE_5_KEYWORDS` 已定义但 `_identify_question_type_keyword` 没有对应分支，`REFERENCE_QUESTIONS` dict 也没有 key 5。更关键的是 `RoleRouter.ROLE_AGENTS`（`framework/agents/router.py:14-18`）三个角色都不含 model-7——即使识别出 type 5 问题，farmer 角色也只会路由到 model-4/5/6。

2. **farmer 问题全返回 mock 数据**：`execute_models`（`framework/agents/nodes.py:283-298`）构建 context 时只提取 `area_code`/`data`/`longitude`/`latitude`/`target_ph`，**不提取 `parcel_id`/`parcel_code`**。而 model-1/3/4 的 `answer_question` 早已写好 `context.get("parcel_id")` 真实查库路径，model-7 早已写好 `context.get("parcel_code")` 调 fortran exe 路径——管道未接通，agents 收不到地块标识符，只能返回 mock + `need_input` 提示。

**ID 空间不对齐**（已确认的硬约束）：
- `stability_db`（5488 条）和 `diagnosis_db`（14585 条）用数字字符串 ID（"1"、"10"、"100"）
- fortran exe 用字母数字代码（"A0001"）
- 两套 ID 无映射关系，A0001 在两个 DB 里都不存在

**agents 现状**（无需改动）：
- model-1 `stability_agent.py:72` 读 `context.get("parcel_id")` → `StabilityStorage.get_result(parcel_id)`
- model-3 `problem_agent.py:83` 读 `context.get("parcel_id")` → `query_parcel(parcel_id, db_path)`
- model-4 `acidification_agent.py:82` 读 `context.get("parcel_id")` → `query_acidification(parcel_id, db_path)`
- model-7 `grade_agent.py:70,90` 读 `context.get("parcel_code")` → `run_grade_evaluation(parcel_code, exe_path, dat_path)`
- model-6 `fertility_ml_agent.py:61` 读 `context.get("data")`（土壤特征 dict，不按地块查库，本次不涉及）

## Goals / Non-Goals

**Goals:**
- `execute_models` 从 `state["request"]` 提取 `parcel_id` 和 `parcel_code` 并透传到 `context`
- `ROLE_AGENTS['farmer']` 追加 model-7，使 farmer 角色问题能触发耕地质量等级评价
- `REFERENCE_QUESTIONS` 新增 type 5 条目（3-5 个质量等级评价问题），`_identify_question_type_keyword` 新增 type 5 分支
- 验证脚本为 farmer 问题预设真实 `parcel_id`（"1"）和 `parcel_code`（"A0001"），重新生成的验证报告显示 model-7 被成功调用且 farmer 问题返回真实数据
- 生产 API `POST /api/v1/chat/` 接受可选 `parcel_id` 和 `parcel_code` 字段

**Non-Goals:**
- 不做 fortran exe parcel_code 与 DB parcel_id 的映射表（无数据支撑）
- 不改 model-6（按特征预测，不按地块查库）
- 不重构 agents 的真实计算路径（已就绪）
- 不改 storage 层和 fortran exe 本身
- 不改 county/province 角色（model-7 仅加到 farmer）

## Decisions

### D1: 双 ID 并存（parcel_id + parcel_code）

**选择**：context 同时携带 `parcel_id`（数字字符串，给 model-1/3/4）和 `parcel_code`（字母数字，给 model-7）。`execute_models` 从 request 提取两个字段，各自独立透传。

**理由**：
- 现有 agents 已分别读 `parcel_id`（model-1/3/4）和 `parcel_code`（model-7），命名不一致是历史事实
- 两套 ID 空间无映射关系，无法统一
- 双 ID 并存是改动最小、风险最低的方案——不触碰 agents 的字段名

**备选**（已否决）：
- 统一用 `parcel_code`：需要改 model-1/3/4 的存储层接受字母数字 ID，或在 storage 内做转换。工作量大且无映射数据。
- 统一用 `parcel_id`：需要改 model-7 的 `grade_agent.py` 读 `parcel_id` 而非 `parcel_code`。但 fortran exe 的概念就是 "parcel code"，改名会引起语义混淆。

### D2: model-7 加到 farmer 角色

**选择**：在 `ROLE_AGENTS['farmer']` 列表末尾追加 `model-7`，变成 `["model-4", "model-5", "model-6", "model-7"]`。

**理由**：
- farmer 关心自己的地块，质量等级评价是 farmer 的核心诉求之一
- model-7 的 `answer_question` 已有 `need_parcel_hint` 机制——缺 `parcel_code` 时返回 mock + 提示，不报错，不影响其他 agent
- 不需要新增 `grade` 角色，路由逻辑改动最小

**备选**（已否决）：
- 新增 `grade` 角色：需要新增 `ROLE_KEYWORDS['grade']` 和 `ROLE_AGENTS['grade']`，改动更大，且 quality-grade 问题与 farmer 场景重叠
- AgentManager 动态追加：在 `process` 里按 `question_type==5` 动态追加 model-7，绕过 RoleRouter。破坏了角色路由的单一职责。

### D3: type 5 问题只在 farmer 角色触发

**选择**：type 5（质量等级）问题由 farmer 角色承载。`REFERENCE_QUESTIONS[5]` 的问题文本包含 "我的田"、"地块" 等 farmer 关键词，确保 RoleRouter 识别为 farmer。

**理由**：
- 质量等级评价是地块级查询，天然属于 farmer 场景
- 避免改动 county/province 角色

### D4: model-7 的问题感知过滤

**选择**：在 `AgentManager._should_execute_agent` 中对 model-7 增加关键词过滤——只有问题含 `QUESTION_TYPE_5_KEYWORDS`（"质量等级"、"等级评价"、"综合指数"、"障碍度排序"等）时才执行 model-7，否则跳过（status=`skipped`, reason=`question_not_related`）。

**理由**：
- 与 model-6 的肥力关键词过滤模式一致
- 避免 model-7 对非质量等级问题做无意义的 fortran exe 调用
- model-7 的 fortran exe 调用有 30s 超时，跳过无关问题可节省时间

```

Full source: openspec/changes/add-parcel-id-and-type5-coverage/design.md

## openspec/changes/add-parcel-id-and-type5-coverage/tasks.md

- Source: openspec/changes/add-parcel-id-and-type5-coverage/tasks.md
- Lines: 1-49
- SHA256: 43b49b0d47fd24ab58fa2fb72184be15bc476a39b6ed8d6649a5c33183b88567

```md
## 1. 路由层：farmer 角色追加 model-7

- [ ] 1.1 修改 `framework/agents/router.py` 的 `ROLE_AGENTS['farmer']`，追加 `model-7`，变为 `["model-4", "model-5", "model-6", "model-7"]`
- [ ] 1.2 在 `framework/agents/manager.py` 的 `_should_execute_agent` 中增加 model-7 关键词过滤：仅当问题含 `QUESTION_TYPE_5_KEYWORDS` 任一关键词时执行 model-7，否则返回 `False`（跳过）
- [ ] 1.3 新增/更新单元测试 `tests/test_role_router.py`（或对应测试文件）：验证 farmer 角色返回 4 个 agent 含 model-7；验证 model-7 在非质量等级问题时被 `_should_execute_agent` 跳过

## 2. 问题类型识别：type 5 分支

- [ ] 2.1 修改 `framework/agents/nodes.py` 的 `_identify_question_type_keyword`，在 type 4 分支后新增 type 5 分支：当问题命中 `QUESTION_TYPE_5_KEYWORDS` 时返回 `(5, relevance)`
- [ ] 2.2 新增/更新单元测试：验证「我的田耕地质量等级是多少」识别为 type 5；验证「我的田肥力怎么样」仍识别为 type 4（非 5）

## 3. 问题库：REFERENCE_QUESTIONS 新增 type 5

- [ ] 3.1 在 `framework/agents/nodes.py` 的 `REFERENCE_QUESTIONS` dict 新增 key `5`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」）
- [ ] 3.2 确认 type 5 问题文本包含 farmer 关键词（"我的田"/"地块"/"这块地"），使 RoleRouter 识别为 farmer 角色
- [ ] 3.3 新增/更新单元测试：验证 `REFERENCE_QUESTIONS[5]` 存在且非空；验证 type 5 问题经 `identify_question_type` 返回 5

## 4. 管道接通：execute_models 透传地块标识符

- [ ] 4.1 修改 `framework/agents/nodes.py` 的 `execute_models`，从 `state["request"]` 提取 `parcel_id` 和 `parcel_code`，加入 `context` 字典（与现有 `area_code`/`data`/`longitude`/`latitude`/`target_ph` 并列）
- [ ] 4.2 确认 `context["parcel_id"]` 透传到 `agent_manager.process(question, context)`，model-1/3/4 能读到
- [ ] 4.3 确认 `context["parcel_code"]` 透传到 `agent_manager.process(question, context)`，model-7 能读到
- [ ] 4.4 新增/更新单元测试：验证 `execute_models` 在 request 含 `parcel_id`/`parcel_code` 时正确透传到 context（可用 monkeypatch 拦截 `agent_manager.process` 检查 context 内容）

## 5. 生产 API：接受 parcel_id/parcel_code

- [ ] 5.1 找到生产 API 路由文件（`POST /api/v1/chat/` 端点），在 request 解析逻辑中新增可选字段 `parcel_id`（string）和 `parcel_code`（string）
- [ ] 5.2 将 `parcel_id`/`parcel_code` 传入 `multi_agent_orchestrator.run(request)` 的 request dict
- [ ] 5.3 更新 API 文档/README：说明 `parcel_id`（数字，用于 DB 查询）和 `parcel_code`（字母数字，用于质量等级评价）的用途和可选性
- [ ] 5.4 新增/更新 API 集成测试：验证带 `parcel_id`/`parcel_code` 的请求被正确透传

## 6. 验证脚本：预设地块标识符 + type 5 覆盖

- [ ] 6.1 修改 `scripts/gen_full_verification_report.py`：扩展 `run_one_question` 接受可选 `parcel_id`/`parcel_code` 参数，传入 `orchestrator.run` 的 request
- [ ] 6.2 为 type 1-4 的 farmer 问题预设 `parcel_id="1"`（来自 stability_db/diagnosis_db）
- [ ] 6.3 为 type 5 问题预设 `parcel_code="A0001"`（来自 fortran exe 数据库）
- [ ] 6.4 county/province 问题不预设 parcel_id（model-1/3 按 area_code 查询）
- [ ] 6.5 运行验证脚本，确认 type 5 问题触发 model-7 且返回真实 fortran exe 结果（非 mock）
- [ ] 6.6 运行验证脚本，确认 farmer 问题（type 1-4）的 model-1/3/4 返回真实 DB 记录（非 mock pH=5.5）
- [ ] 6.7 重新生成 `verification_full_report.md`，确认 model-7 出现在 agents_invoked 列表且 answer 含真实质量等级

## 7. 回归测试与验收

- [ ] 7.1 运行现有测试套件（`pytest tests/`），确认无破坏性回归（特别是 test_role_router、test_question_type_keywords、test_interfaces）
- [ ] 7.2 运行新增的单元测试，确认全部通过
- [ ] 7.3 验证场景 A：问「我的田 A0001 耕地质量等级是多少」→ model-7 调 fortran exe 返回真实质量等级
- [ ] 7.4 验证场景 B：问「我的田肥力怎么样」+ parcel_id=1 → model-1/3/4 返回真实 DB 记录
- [ ] 7.5 验证场景 D：model-2/5 收到 parcel_id 仍返回 stub 回复（不报错）
- [ ] 7.6 验证场景 E：未传 parcel_id 时 agents 返回 mock + need_input 提示（现有行为不变）

```

## openspec/changes/add-parcel-id-and-type5-coverage/specs/multi-agent-orchestrator/spec.md

- Source: openspec/changes/add-parcel-id-and-type5-coverage/specs/multi-agent-orchestrator/spec.md
- Lines: 1-72
- SHA256: 2b02ad6e28b21fac73e85e010d7109aa7591a29d65ae961e12f145f3b16225ca

```md
## ADDED Requirements

### Requirement: 地块标识符上下文透传
系统 SHALL 在 `execute_models` 节点从 `state["request"]` 提取 `parcel_id`（数字字符串，用于 stability_db/diagnosis_db 查询）和 `parcel_code`（字母数字字符串，用于 fortran exe 调用）并加入 `context`，使 AgentManager 内的 agents 能通过 `context.get("parcel_id")` 或 `context.get("parcel_code")` 获取地块标识符执行真实查询。

`parcel_id` 与 `parcel_code` 是两套无映射关系的 ID 空间：`parcel_id` 对应 stability_db/diagnosis_db 的数字 ID（如 "1"），`parcel_code` 对应 fortran exe 数据库的字母数字代码（如 "A0001"）。系统 SHALL NOT 尝试在两套 ID 之间做转换。

两个字段均为可选：未传时 agents SHALL 维持现有 mock 数据 + `need_input` 提示行为，不报错。

#### Scenario: 传递 parcel_id 触发 DB 真实查询
- **WHEN** request 包含 `parcel_id: "1"` 且问题路由到 model-1（StabilityRiskAgent）
- **THEN** `execute_models` SHALL 将 `parcel_id` 透传到 context
- **AND** model-1 SHALL 用 `parcel_id="1"` 查询 stability_db 返回真实稳定性记录（非 mock pH=5.5）

#### Scenario: 传递 parcel_code 触发 fortran exe 真实计算
- **WHEN** request 包含 `parcel_code: "A0001"` 且问题路由到 model-7（FarmlandGradeAgent）
- **THEN** `execute_models` SHALL 将 `parcel_code` 透传到 context
- **AND** model-7 SHALL 用 `parcel_code="A0001"` 调用 fortran exe 返回真实质量等级评价（非 mock）

#### Scenario: 双 ID 并存
- **WHEN** request 同时包含 `parcel_id: "1"` 和 `parcel_code: "A0001"`
- **THEN** context SHALL 同时携带两个字段
- **AND** model-1/3/4 SHALL 读 `parcel_id` 查 DB，model-7 SHALL 读 `parcel_code` 调 exe，互不干扰

#### Scenario: 未传地块标识符时降级
- **WHEN** request 不含 `parcel_id` 和 `parcel_code`
- **THEN** agents SHALL 返回 mock 数据并附加 `need_input` 提示（现有行为不变）
- **AND** SHALL NOT 抛出异常

### Requirement: Type 5 质量等级评价问题库
系统 SHALL 在 `REFERENCE_QUESTIONS` 字典中新增 key `5`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」），使验证脚本能覆盖 model-7。

`_identify_question_type_keyword` 函数 SHALL 新增 type 5 分支，当问题命中 `QUESTION_TYPE_5_KEYWORDS`（"质量等级"、"等级评价"、"综合指数"、"指标隶属度"、"障碍度排序"、"耕地质量等级"、"质量评价"、"等级评定"、"指标权重"）时返回 `(5, relevance)`。

#### Scenario: 识别质量等级问题为 type 5
- **WHEN** 用户询问「我的田耕地质量等级是多少」
- **THEN** `identify_question_type` SHALL 返回 `question_type=5`

#### Scenario: type 5 问题路由到含 model-7 的 agent 组合
- **WHEN** 问题被识别为 type 5 且角色为 farmer
- **THEN** RoleRouter SHALL 路由到 `["model-4", "model-5", "model-6", "model-7"]`
- **AND** model-7 SHALL 被执行（非 skipped）

### Requirement: model-7 问题感知过滤
系统 SHALL 在 `AgentManager._should_execute_agent` 中对 model-7 增加关键词过滤：只有问题含 `QUESTION_TYPE_5_KEYWORDS` 中的任一关键词时才执行 model-7，否则跳过（status=`skipped`, reason=`question_not_related`）。

#### Scenario: 非质量等级问题跳过 model-7
- **WHEN** farmer 角色问题不含质量等级关键词（如「我的田肥力怎么样」）
- **THEN** AgentManager SHALL 跳过 model-7（status=`skipped`, reason=`question_not_related`）
- **AND** SHALL NOT 调用 fortran exe

#### Scenario: 质量等级问题执行 model-7
- **WHEN** farmer 角色问题含「质量等级」关键词
- **THEN** AgentManager SHALL 执行 model-7
- **AND** model-7 SHALL 调用 fortran exe（如 parcel_code 可用）

### Requirement: 生产 API 接受地块标识符
系统 SHALL 在 `POST /api/v1/chat/` 请求体中支持可选的 `parcel_id`（string，数字格式）和 `parcel_code`（string，字母数字格式）字段，并透传到 `multi_agent_orchestrator.run(request)`。

#### Scenario: API 请求携带 parcel_id
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 含 `parcel_id: "1"`
- **THEN** 系统 SHALL 将 `parcel_id` 透传到 orchestrator request
- **AND** orchestrator SHALL 将其加入 context 供 agents 读取

#### Scenario: API 请求携带 parcel_code
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 含 `parcel_code: "A0001"`
- **THEN** 系统 SHALL 将 `parcel_code` 透传到 orchestrator request
- **AND** orchestrator SHALL 将其加入 context 供 model-7 读取

#### Scenario: API 请求不携带地块标识符
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 不含 `parcel_id` 和 `parcel_code`
- **THEN** 系统 SHALL 正常处理（现有行为不变），agents 返回 mock + `need_input` 提示

```

## openspec/changes/add-parcel-id-and-type5-coverage/specs/role-based-routing/spec.md

- Source: openspec/changes/add-parcel-id-and-type5-coverage/specs/role-based-routing/spec.md
- Lines: 1-27
- SHA256: 324d1d5fd7de53917f84b813043365db7c42451b2761ed2428e9cedad79d333a

```md
## MODIFIED Requirements

### Requirement: 用户角色识别
系统 SHALL 基于关键词匹配识别用户角色（省市管理端、县域执行端、农户种植端），并将问题路由到对应的智能体组合。

农户种植端（farmer）角色 SHALL 包含 model-7（FarmlandGradeAgent），使 farmer 问「我的田质量等级」时能触发耕地质量等级评价。model-7 的实际执行受 `AgentManager._should_execute_agent` 关键词过滤约束——仅当问题含 `QUESTION_TYPE_5_KEYWORDS` 时执行，否则跳过。

#### Scenario: 省市管理端路由
- **WHEN** 用户问题包含"全省"、"全市"、"全局"、"政策"等关键词
- **THEN** 系统 SHALL 识别角色为"省市管理端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent

#### Scenario: 县域执行端路由
- **WHEN** 用户问题包含"本县"、"乡镇"、"片区"、"任务"等关键词
- **THEN** 系统 SHALL 识别角色为"县域执行端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent + PotentialAssessmentAgent

#### Scenario: 农户种植端路由
- **WHEN** 用户问题包含"我的田"、"这块地"、"施氮肥"、"施多少"等关键词
- **THEN** 系统 SHALL 识别角色为"农户种植端"，路由到 AcidificationRemediationAgent (model-4) + OrganicMatterAgent (model-5) + FertilityMLAgent (model-6) + FarmlandGradeAgent (model-7)

#### Scenario: farmer 质量等级问题触发 model-7
- **WHEN** farmer 角色问题包含"质量等级"、"等级评价"、"综合指数"等 `QUESTION_TYPE_5_KEYWORDS` 关键词
- **THEN** 系统 SHALL 执行 model-7（FarmlandGradeAgent），调用 fortran exe 获取真实质量等级评价（如 `parcel_code` 可用）

#### Scenario: farmer 非质量等级问题跳过 model-7
- **WHEN** farmer 角色问题不含 `QUESTION_TYPE_5_KEYWORDS` 关键词（如「我的田肥力怎么样」）
- **THEN** 系统 SHALL 跳过 model-7（status=`skipped`, reason=`question_not_related`）
- **AND** SHALL 只执行 model-4/5/6

```
