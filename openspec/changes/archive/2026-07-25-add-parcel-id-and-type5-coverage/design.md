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

### D5: 验证脚本预设 ID 策略

**选择**：`gen_full_verification_report.py` 的 `REFERENCE_QUESTIONS` 扩展为带元数据的结构，每个问题附带 `parcel_id` 和/或 `parcel_code`：
- type 1-4 的 farmer 问题：预设 `parcel_id="1"`（来自 stability_db/diagnosis_db）
- type 5 问题：预设 `parcel_code="A0001"`（来自 fortran exe 数据库）
- county/province 问题：不预设（model-1/3 按 area_code 查询，不需 parcel_id）

**理由**：
- 按问题类型预设对应的 ID，避免传错 ID 空间
- 验证脚本是测试代码，可以硬编码真实 ID

## Risks / Trade-offs

- **[farmer 角色膨胀]** farmer 现在调用 4 个 agent（model-4/5/6/7），比之前多一个。model-7 的 fortran exe 调用有 30s 超时。→ **缓解**：D4 的问题感知过滤确保 model-7 只在质量等级问题执行，其他问题跳过（skipped，不调 exe）。
- **[双 ID 用户混淆]** 生产 API 用户可能不知道该传 `parcel_id` 还是 `parcel_code`。→ **缓解**：两个字段都可选，API 文档明确说明 `parcel_id` 用于 DB 查询（数字）、`parcel_code` 用于质量等级评价（字母数字）。未传时 agents 返回 mock + `need_input` 提示。
- **[model-2/5 占位桩干扰]** model-2/5 是占位桩，收到 parcel_id 也只返回 stub 回复。→ **缓解**：不影响真实计算 agent（model-1/3/4/7）的结果。验证报告已标注 model-2/5 为占位桩。
- **[fortran exe 部署依赖]** model-7 真实计算依赖 `bin/farmland_quality_eval/` 下的 exe+dat 文件。→ **缓解**：`grade_agent.py` 已有 `GRADE_EVAL_AVAILABLE` 检查和 `check_deployment` 校验，部署缺失时返回 mock + 提示，不报错。
- **[spec drift]** 现有 `role-based-routing` spec 的 farmer 场景写的是 "ComprehensiveImprovementAgent"，但代码实际是 FertilityMLAgent（model-6）。→ **缓解**：本次 MODIFIED requirement 修正为实际状态（model-4/5/6/7）。

## Migration Plan

- **非破坏性变更**：所有改动都是新增字段/agent，不删除现有字段/agent。未传 `parcel_id`/`parcel_code` 时行为不变（agents 返回 mock + `need_input` 提示）。
- **部署步骤**：
  1. 修改 `execute_models` 透传逻辑 + `ROLE_AGENTS['farmer']` 追加 model-7 + `REFERENCE_QUESTIONS` type 5 + `_identify_question_type_keyword` 分支 5
  2. 修改 `_should_execute_agent` 增加 model-7 关键词过滤
  3. 更新验证脚本预设 ID
  4. 修改生产 API 路由接受 `parcel_id`/`parcel_code`
  5. 运行测试套件验证非破坏性
- **回滚策略**：所有改动在 4 个文件内（nodes.py, router.py, manager.py, API 路由），`git revert` 即可回滚。

## Open Questions

（已全部通过用户确认解决——双 ID 并存、model-7 加到 farmer、按问题类型预设 ID。无遗留问题。）
