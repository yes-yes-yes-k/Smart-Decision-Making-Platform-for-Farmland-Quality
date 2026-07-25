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
