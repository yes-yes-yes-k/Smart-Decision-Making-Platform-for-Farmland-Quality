# Task 5 Review — AgentManager 集成与按需过滤

## 1. Approve/Reject 决定

**APPROVED（fix 后）**

Implementer 的 5 处必改点已全部正确落地，无计划外改动，无既有测试被修改。通过 `git diff af6fb2e 175e7e3 -- framework/agents/manager.py` 逐行核对：

| # | 必改点 | 落地位置 | 状态 |
|---|--------|----------|------|
| 1 | 顶部新增 `FERTILITY_KEYWORDS` 常量 | `framework/agents/manager.py` line 8-14 | ✅ 与 `FertilityMLAgent.FERTILITY_KEYWORDS`（`fertility_ml_agent.py` line 10-15）逐字一致 |
| 2 | `_register_agents` 中 model-6 spec 改为 `FertilityMLAgent` | line 55 `("model-6", "FertilityMLAgent", "耕地肥力 SOC/Dose ML 预测", "fertility_ml")` | ✅ |
| 3 | `self.agents["model-6"].dependencies = []` | line 71（原 `["model-4", "model-5"]`） | ✅ |
| 4 | `_load_real_agents` model-6 改为 import `FertilityMLAgent` | line 101-105（原 `ComprehensiveImprovementAgent`） | ✅ |
| 5 | 新增 `_should_execute_agent` 方法 | line 177-182（位于 `_topological_sort` 之后、`_summarize` 之前） | ✅ |
| 6 | `_execute_with_dependencies` 加入按需过滤逻辑 | line 126-138（for 循环开头跳过分支，写入 `status="skipped"` + `simulated=True`） | ✅ |

附加核查：
- `tests/test_agent_manager.py` 新增 7 个测试函数（line 63-128），按 plan 原文逐字落地，既有 5 个测试函数（line 9-60）与 `if __name__ == "__main__":` 块（line 131-137）未改动。
- 未删除 `comprehensive_agent.py`、未修改 `__init__.py`（Task 6 职责未被越界）。
- commit message 严格使用 plan 原话。

## 2. Concern 分析结论

**确认 Concern 属实，且为 brief/plan 设计缺陷，非 implementer 缺陷。**

### Concern 复述

brief 同时存在两个数学上不可同时满足的断言：

1. **新测试 `test_topological_sort_model6_no_dep`**（brief line 72-80）调用 `_topological_sort(["model-4", "model-5", "model-6"])`，断言 `ordered[-1] != "model-6"`（要求 model-6 不在末尾）。
2. **既有测试 `test_manager_process_farmer_returns_structured_result`**（受 brief 约束 2「不要修改既有 5 个测试函数」保护）通过 `process(...)` 间接调用 `_summarize._topological_sort(["model-4","model-5","model-6"])`，断言 `data["agents_invoked"] == ["model-4", "model-5", "model-6"]`（model-6 在末尾）。

### 根因分析

`_topological_sort` 采用后序 DFS 实现（`for agent_id in agent_ids: visit(agent_id)` + `for dep in deps: visit(dep); order.append(node)`）。当所有节点依赖为空时，append 顺序完全跟随输入顺序。因此输入 `["model-4", "model-5", "model-6"]` 时输出仍是 `["model-4", "model-5", "model-6"]`，model-6 在末尾。

- 这导致新测试 `test_topological_sort_model6_no_dep` FAIL（`ordered[-1] == "model-6"` 与断言 `ordered[-1] != "model-6"` 冲突）。
- 同时 brief Step 5 Expected 预测的「`test_manager_topological_sort_farmer` 会 FAIL」并未发生——该测试反而 PASS，因为后序 DFS 在依赖为空时保留输入顺序，model-6 仍在末尾，满足其断言 `ordered[-1] == "model-6"`。

### 责任归属

implementer 严格遵守 brief 约束 2（不修改既有测试）、约束 5（不重写 manager.py，按 5 处必改点逐一修改）以及「按 plan 原文逐字落地，不要修改断言」的指示，如实报告矛盾。行为完全正确，无任何缺陷。矛盾的本质是 brief/plan 在设计新测试时未考虑到 `_topological_sort` 实现细节（后序 DFS + 输入顺序保留）导致的语义冲突。

## 3. 应用的 fix

### 方案选择：**方案 A（最小化）**

**修改对象**：`tests/test_agent_manager.py` 中新测试 `test_topological_sort_model6_no_dep` 的输入参数（仅此一处）。

**修改内容**：
- 文件：`d:\17417\Documents\agent_culti_demo\tests\test_agent_manager.py`
- 行号：line 103
- 旧：`ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])`
- 新：`ordered = mgr._topological_sort(["model-6", "model-4", "model-5"])`
- 断言 `assert ordered[-1] != "model-6" or len(ordered) == 1`（line 106）**保持不变**。
- 既有 5 个测试函数（包括 `test_manager_topological_sort_farmer` line 32 的同款输入调用）**未修改**。

### 方案 A 的语义验证

**新行为（model-6 deps=[]，fix 后输入 `["model-6", "model-4", "model-5"]`）**：
- `visit("model-6")` → 无依赖 → `append("model-6")`；order=`["model-6"]`
- `visit("model-4")` → 无依赖 → `append("model-4")`；order=`["model-6", "model-4"]`
- `visit("model-5")` → 无依赖 → `append("model-5")`；order=`["model-6", "model-4", "model-5"]`
- 输出：`["model-6", "model-4", "model-5"]`
- `ordered[-1] == "model-5"` → `ordered[-1] != "model-6"` 为 True → 断言 PASS（GREEN 正确）✅

**旧行为反推（若 model-6 deps=[model-4, model-5]，RED 阶段验证）**：
- `visit("model-6")` → 递归 `visit("model-4")` → `append("model-4")`；递归 `visit("model-5")` → `append("model-5")`；`append("model-6")`；order=`["model-4", "model-5", "model-6"]`
- `visit("model-4")` → 已访问，跳过
- `visit("model-5")` → 已访问，跳过
- 输出：`["model-4", "model-5", "model-6"]`
- `ordered[-1] == "model-6"` → `ordered[-1] != "model-6"` 为 False，`len(ordered) == 1` 为 False → 断言 FAIL（RED 正确）✅

### 选择方案 A 的理由

1. **保留 plan 核心意图**：plan 注释明确「model-6 不再依赖 model-4/5，不强制排最后」，方案 A 通过把 model-6 放在输入第一位，使后序 DFS 输出末位为 model-5，精准体现「model-6 不被强制排到末尾」的语义。
2. **最小违反 brief 约束**：brief 约束「不要修改新测试断言」——方案 A 仅修改输入参数（`agent_ids` 列表），断言 `ordered[-1] != "model-6" or len(ordered) == 1` 原样保留。
3. **不引发既有测试回归**：`test_manager_topological_sort_farmer` 和 `test_manager_process_farmer_returns_structured_result` 仍 PASS（它们调用 `_topological_sort` 时输入仍为 `["model-4", "model-5", "model-6"]`，输出 `["model-4", "model-5", "model-6"]`，model-6 在末尾，符合既有断言）。
4. **保留 RED/GREEN 区分能力**：方案 A 使新测试具备区分新旧行为的能力（旧行为 FAIL，新行为 PASS），未沦为方案 B 的「仅 set 相等」弱断言。
5. **方案 B/C 的劣势**：方案 B（删除 `ordered[-1] != "model-6"` 断言）使测试失去区分能力；方案 C（保持 FAIL 推迟到 Task 7）扩张 Task 7 范围且违背 Task 7「all pass」目标。

## 4. Fix 后测试结果

命令：`python -m pytest tests/test_agent_manager.py -v`

```
============================= test session starts =============================
platform win32 -- Python 3.12.1, pytest-9.1.1, pluggy-1.6.0 -- D:\miniconda3\python.exe
cachedir: .pytest_cache
rootdir: D:\17417\Documents\agent_culti_demo
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.10.2
collecting 12 items

tests/test_agent_manager.py::test_manager_register_six_agents PASSED     [  8%]
tests/test_agent_manager.py::test_manager_topological_sort_province PASSED [ 16%]
tests/test_agent_manager.py::test_manager_topological_sort_farmer PASSED [ 25%]
tests/test_agent_manager.py::test_manager_process_farmer_returns_structured_result PASSED [ 33%]
tests/test_agent_manager.py::test_manager_process_unknown_question_defaults_farmer PASSED [ 41%]
tests/test_agent_manager.py::test_should_execute_model6_fertility_question PASSED [ 50%]
tests/test_agent_manager.py::test_should_skip_model6_non_fertility_question PASSED [ 58%]
tests/test_agent_manager.py::test_should_execute_other_agents_always PASSED [ 66%]
tests/test_agent_manager.py::test_model6_dependencies_empty PASSED       [ 75%]
tests/test_agent_manager.py::test_topological_sort_model6_no_dep PASSED  [ 83%]
tests/test_agent_manager.py::test_model6_skipped_in_details_for_non_fertility PASSED [ 91%]
tests/test_agent_manager.py::test_manager_loads_fertility_ml_agent PASSED [100%]

============================= 12 passed in 2.33s ==============================
```

**12 PASS（5 既有 + 7 新增），0 FAIL。** 满足 brief Step 5「既有测试应 PASS」与 Step 4「7 个新测试全部 PASS」的验收标准。

## 5. 新 commit hash

- **原 commit**：`175e7e3`（implementer 的 commit）
- **新 commit**：`5c8447e`（amend 后，commit message 保持原话 `feat(manager): AgentManager 集成 FertilityMLAgent 并新增按需过滤` 不变）
- **分支**：`feature/20260718/add-model-6-fertility-ml`（未 push，amend 安全）
- **diff stat**：`2 files changed, 101 insertions(+), 4 deletions(-)`（与原 commit 一致，因 fix 是 in-place 修改单行未引入净行数变化）
- **amend 命令**：
  ```powershell
  git add tests/test_agent_manager.py
  git commit --amend --no-edit
  ```

## 6. Minor findings

### plan-mandated（无需修复，属 plan 已知设计）

1. **brief Step 5 Expected 与实际不符**：brief line 413-417 预测「`test_manager_topological_sort_farmer` 会 FAIL（原断言 `ordered[-1] == "model-6"` 不再成立）」，但实际该测试在 implementer 改动后仍 PASS（后序 DFS 在依赖为空时保留输入顺序，model-6 仍在末尾）。这是 plan 对 `_topological_sort` 实现行为预判错误，不影响验收——实际结果比 plan 预期更好（既有测试无需 Task 7 修复）。建议 plan 作者在 Task 7 checkoff 时更新 plan 注释。

2. **brief BASE 与实际 BASE 微小差异**：brief line 141-147 的 BASE 版本中 `_StubAgent.answer_question` 的 `evidence` 字段为 `[]`，但实际 `af6fb2e` 的 `framework/agents/manager.py` 中该字段为 `[{"source": "stub", "model_id": self.model_id}]`。这是 brief BASE 快照过时，implementer 未触碰该字段，无影响。

### 可选（不阻塞验收）

- 无。

## 7. 是否阻塞 Task 5 验收

**不阻塞。fix 后 Task 5 视为 APPROVED。**

- 5 处必改点全部正确落地（manager.py）。
- 7 个新测试全部 PASS（含 fix 后的 `test_topological_sort_model6_no_dep`）。
- 5 个既有测试全部 PASS（无回归）。
- commit 已 amend 到 `5c8447e`，commit message 保持 plan 原话。
- 风险信号自报 7 项与实际 diff 一致。
- Concern 已通过方案 A 最小化修复，未扩张到 manager.py 或既有测试。

**Task 5 可移交给 coordinator 做 checkoff commit（task-5-brief.md / task-5-report.md / task-5-review.md）并启动 Task 6。**
