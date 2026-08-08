---
change: unify-model2-real-integration
design-doc: docs/superpowers/specs/2026-08-08-unify-model2-real-integration-design.md
base-ref: 0ceac011526a9027e3a2d69f643a110f9a9ac72c
---

# 模型2真实能力归并 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将真实耕地质量评价和潜力分析统一接入 model-2，彻底删除独立 model-7，使运行时只注册六个专题模型。

**Architecture:** 保留 `src/ai_culti_demo/farmland_grade_eval` 作为内部真实计算包，在 `PotentialAssessmentAgent.execute()` 依据 `question_type` 调用质量等级、单地块潜力或县域潜力函数。能力目录允许 type 5 与 type 6 共同映射 model-2，AgentManager 只注册 model-1 至 model-6。

**Tech Stack:** Python 3.12、Flask、现有 AgentManager/BaseAgent、pytest、OpenSpec、标准库 CSV/数学计算。

## Global Constraints

- Python 相关命令必须使用 `C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe`。
- `model-7`、`quality-grade-evaluation` 和其兼容别名必须从运行时、公开能力和文档中彻底删除。
- type 5 与 type 6 均只能调用 `model-2`；结果 `agents_invoked` 不得出现 model-7。
- 缺少 `parcel_code` 必须返回 `status: "error"` 和 `error.code: "MISSING_PARCEL_CODE"`，不得返回模拟指标。
- 底层 `farmland_grade_eval` 的公式、默认 CSV 路径和 A0001 数值回归不得改变。

---

### Task 1: 收敛能力目录与路由

**Files:**
- Modify: `framework/agents/capabilities.py`
- Modify: `framework/agents/router.py`
- Test: `tests/test_model_specs_sync.py`
- Test: `tests/test_question_type_router.py`

**Interfaces:**
- Consumes: `ProfessionalCapability` 与现有 `CAPABILITY_BY_QUESTION_TYPE`。
- Produces: type 5/type 6 均映射到 `model-2` 的 `TYPE_AGENTS`，且正式能力目录只有 6 项。

- [ ] **Step 1: 写入失败测试，固定六模型和共享路由契约**

```python
assert len(PROFESSIONAL_CAPABILITIES) == 6
assert "model-7" not in CAPABILITY_BY_AGENT_ID
assert TYPE_AGENTS[5] == ["model-2"]
assert TYPE_AGENTS[6] == ["model-2"]
assert get_capability_by_model_id("quality-grade-evaluation") is None
```

- [ ] **Step 2: 运行定向路由测试，确认当前实现失败**

Run:

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' -m pytest tests/test_model_specs_sync.py tests/test_question_type_router.py -q
```

Expected: 现有 model-7 注册和 type 5 路由断言导致失败。

- [ ] **Step 3: 扩展能力数据结构并删除 model-7 能力**

在 `ProfessionalCapability` 中添加不可变的 `question_type_aliases: tuple[int, ...] = ()`，将模型2的规范 `question_type` 保持为 6、别名设为 `(5,)`；从 `PROFESSIONAL_CAPABILITIES` 删除 model-7；由规范类型加别名构造 `CAPABILITY_BY_QUESTION_TYPE`；在 `public_capability_descriptor()` 暴露 `question_types`。

```python
def _question_type_map() -> Dict[int, ProfessionalCapability]:
    mapping: Dict[int, ProfessionalCapability] = {}
    for item in PROFESSIONAL_CAPABILITIES:
        for question_type in (item.question_type, *item.question_type_aliases):
            mapping[question_type] = item
    return mapping
```

- [ ] **Step 4: 运行定向路由测试，确认通过**

Run:

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' -m pytest tests/test_model_specs_sync.py tests/test_question_type_router.py -q
```

Expected: PASS，type 5/type 6 均只路由到 model-2。

### Task 2: 实现模型2真实计算入口

**Files:**
- Modify: `framework/agents/specialized/potential_agent.py`
- Delete: `framework/agents/specialized/grade_agent.py`
- Test: `tests/test_agent_specialized.py`
- Test: `tests/test_farmland_grade_eval.py`

**Interfaces:**
- Consumes: `run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)`、`run_potential_analysis(parcel_code, csv_path=None)`、`run_county_potential(xqmc_code, scenario, csv_path=None)`。
- Produces: 模型2的 `execute(payload)` 返回 `{status, result|error, metadata: {simulated: False}}`。

- [ ] **Step 1: 写入真实模型2失败测试**

```python
agent = PotentialAssessmentAgent()
grade = agent.execute({"question_type": 5, "parcel_code": "A0001"})
assert grade["status"] == "ok"
assert grade["metadata"]["simulated"] is False
assert grade["result"]["quality_grade"] == "10等"

potential = agent.execute({"question_type": 6, "parcel_code": "A0001"})
assert potential["status"] == "ok"
assert "full_potential" in potential["result"]

missing = agent.execute({"question_type": 5})
assert missing["error"]["code"] == "MISSING_PARCEL_CODE"
```

- [ ] **Step 2: 运行专题模型测试，确认固定模拟实现失败**

Run:

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' -m pytest tests/test_agent_specialized.py -q
```

Expected: 真实等级、潜力字段和缺少地块编码错误断言失败。

- [ ] **Step 3: 用真实引擎重写 PotentialAssessmentAgent.execute()**

导入真实函数，按 `question_type` 分派，保留底层错误码：

```python
if question_type == 5:
    result = run_grade_evaluation(parcel_code, dat_path=csv_path)
elif question_type == 6 and parcel_code:
    result = run_potential_analysis(parcel_code, csv_path)
elif question_type == 6:
    result = run_county_potential(xqmc_code, scenario, csv_path)
```

所有成功和失败返回均写入 `metadata={"simulated": False}`；缺少必要参数时构造 `MISSING_PARCEL_CODE` 或对应县域参数错误。删除 `MOCK_INDICATORS`、`POTENTIAL_RULES` 和模拟阈值逻辑；将聊天摘要基于 `analysis` 真实结果生成。

- [ ] **Step 4: 删除独立等级 Agent 并替换导入引用**

删除 `grade_agent.py`，确保没有生产代码、测试或文档仍导入 `FarmlandGradeAgent`。`farmland_grade_eval` 包不删除。

- [ ] **Step 5: 运行模型2与底层回归测试**

Run:

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' -m pytest tests/test_agent_specialized.py tests/test_farmland_grade_eval.py -q
```

Expected: PASS，A0001 综合指数约 `0.6728`、质量等级 `10等`，且模型2结果均为真实计算。

### Task 3: 收敛 AgentManager 与聊天编排

**Files:**
- Modify: `framework/agents/manager.py`
- Modify: `framework/agents/nodes.py`
- Modify: `framework/api/routes/chat.py`
- Test: `tests/test_agent_manager.py`
- Test: `tests/test_agent_integration.py`
- Test: `tests/test_execute_models_pipeline.py`

**Interfaces:**
- Consumes: 6 项能力目录与模型2真实 `execute()`。
- Produces: 只注册 6 个 Agent，type 5/type 6 的 `agents_invoked == ["model-2"]`。

- [ ] **Step 1: 写入失败测试，断言注册表和编排结果不存在 model-7**

```python
manager = AgentManager()
assert set(manager.agents) == {"model-1", "model-2", "model-3", "model-4", "model-5", "model-6"}
assert manager.process("A0001 的质量等级", {"question_type": 5, "parcel_code": "A0001"})["data"]["agents_invoked"] == ["model-2"]
```

- [ ] **Step 2: 删除 model-7 注册、依赖和加载逻辑**

从 `_register_agents()` 删除 `self.agents["model-7"]` 依赖声明，从 `_load_real_agents()` 删除 `FarmlandGradeAgent` 导入和赋值；更新注释为“6 个专业智能体”。

- [ ] **Step 3: 保证编排上下文完整透传**

在 `execute_models` 与 API chat 路由的说明和测试中，将 `parcel_code` 的归属由 model-7 改为 model-2，并确保 `question_type`、`parcel_code`、`xqmc_code`、`scenario` 和 `csv_path` 进入 `AgentManager._analysis_payload()`。

- [ ] **Step 4: 运行 AgentManager 和聊天链路测试**

Run:

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' -m pytest tests/test_agent_manager.py tests/test_agent_integration.py tests/test_execute_models_pipeline.py -q
```

Expected: PASS，type 5/type 6 均仅调用 model-2；缺少 `parcel_code` 返回 `MISSING_PARCEL_CODE`，无 model-7。

### Task 4: 清理接口、文档和验证资产

**Files:**
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/openapi.json`
- Modify: `docs/deployment/data-deployment.md`
- Modify: `scripts/verify_agent_capabilities.py`
- Modify: `scripts/gen_full_verification_report.py`
- Modify: 受影响测试中的 model-7 文案和断言

**Interfaces:**
- Consumes: 6 模型能力目录、type 5/type 6 到模型2路由。
- Produces: 文档和验证报告不再列出 model-7 或 `quality-grade-evaluation`。

- [ ] **Step 1: 搜索并分类 model-7/quality-grade-evaluation 残留**

Run:

```powershell
rg -n -S "model-7|quality-grade-evaluation|FarmlandGradeAgent" README.md docs framework src scripts tests
```

Expected: 将生产代码、用户文档、验证脚本、活跃测试与历史归档区分；仅修改非归档的当前资产。

- [ ] **Step 2: 更新公开能力和路由文档**

将所有“7 个专题模型”改为“6 个专题模型”；将 type 5/type 6 均说明为模型2真实能力；删除模型7接口和能力列表示例；明确 `parcel_code` 是模型2真实评价/潜力的必填输入。

- [ ] **Step 3: 更新验证报告映射**

将标准“耕地质量提升潜力评估模型”绑定到 `model-2`，移除追加的 model-2/model-5 历史占位桩说明中与模型2相关的行，删除 model-7 资源就绪与统计分支。

- [ ] **Step 4: 运行文档/验证脚本和残留扫描**

Run:

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' scripts/verify_agent_capabilities.py
rg -n -S "model-7|quality-grade-evaluation|FarmlandGradeAgent" README.md docs framework src scripts tests -g '!docs/superpowers/reports/**' -g '!docs/superpowers/specs/**'
```

Expected: 验证输出只列出 6 个正式模型；当前非历史资产无 model-7 残留。

### Task 5: 全量验证与变更收尾

**Files:**
- Modify: `openspec/changes/unify-model2-real-integration/tasks.md`
- Test: `tests/`

**Interfaces:**
- Consumes: 完成后的六模型运行时、文档和 OpenSpec 规格。
- Produces: 通过严格校验、完整测试和可追溯的任务完成状态。

- [ ] **Step 1: 运行 OpenSpec 严格校验**

Run:

```powershell
comet classic openspec -- validate "unify-model2-real-integration" --strict
```

Expected: `Change 'unify-model2-real-integration' is valid`。

- [ ] **Step 2: 运行完整 Python 测试套件**

Run:

```powershell
& 'C:\Users\PC\.conda\envs\agent_culti_demo_py312\python.exe' -m pytest tests/ -q --tb=short
```

Expected: 所有测试通过；若失败，先按失败类型修复能力目录、模型2错误契约或残留 model-7 断言。

- [ ] **Step 3: 更新 OpenSpec 任务状态并复查差异**

将已完成条目改为 `- [x]`，然后运行：

```powershell
git diff --check
git status --short
```

Expected: 无空白错误，变更范围仅包含模型2归并、测试、文档和本 change 产物。
