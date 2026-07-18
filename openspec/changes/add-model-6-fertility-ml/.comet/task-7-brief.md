# Task 7 Implementer Brief — 测试套件整合与全量验证

## 上下文

- **Change**: `add-model-6-fertility-ml`
- **Phase**: build (subagent-driven-development, tdd_mode=tdd, review_mode=standard)
- **Branch**: `feature/20260718/add-model-6-fertility-ml`
- **BASE（HEAD）**: `8b84179`（Task 6 checkoff）
- **Plan**: `docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` Task 7（line 1573-1654）
- **Tasks.md**: `openspec/changes/add-model-6-fertility-ml/tasks.md` 7.1-7.4

## TDD 硬约束

implementer 必须先加载 `test-driven-development` skill，遵循 RED → GREEN → REFACTOR。Task 7 是测试套件修复任务，RED = 运行 pytest 确认失败用例清单，GREEN = 修复后重新运行确认 PASS。**禁止** 在没有运行证据的情况下提交。

## 任务目标

修复 Task 3-6 model-6 重构（ComprehensiveImprovementAgent → FertilityMLAgent）导致的既有测试失败，确保全量测试套件通过。

## 已知失败用例（协调者已运行 pytest 确认）

运行命令 `python -m pytest tests/test_agent_manager.py tests/test_agent_integration.py tests/test_agent_specialized.py tests/test_agent_base.py tests/test_multi_agent.py -v` 的结果：

- **54 passed, 3 failed**
- 3 个失败用例全部位于 `tests/test_agent_integration.py`：

### 失败 1: `test_chat_api_returns_structured_multi_agent_result` (line 96)

```python
assert isinstance(data.get("recommendations"), list)  # AssertionError: assert False
# data.get("recommendations") returns None
```

**根因**：
- 测试问题 "我的田施氮肥施多少？" 中 "施氮肥" 不在 `FERTILITY_KEYWORDS`（关键词是 "施肥" 不是 "施氮肥"），导致 model-6 被 `_should_execute_agent` 跳过
- model-4 (acidification) else 分支未匹配 "治理"/"施加"/"调理剂"/"石灰" 关键词，evidence 无 `recommendation` 字段
- model-5 (organic_matter) else 分支未匹配 "含量"/"分布"/"现状" 或 "施用量"/"有机肥" 关键词，evidence 无 `recommendation` 字段
- `framework/api/routes/chat.py:111-112` 中 `if recommendations: response_data["recommendations"] = recommendations` 在空列表时不写入字段
- 因此 `data.get("recommendations")` 返回 None

### 失败 2: `test_e2e_farmer_role_routing` (line 139)

```python
m6_evidence = str(data["details"]["model-6"]["evidence"])
assert "model-4" in m6_evidence or "model-5" in m6_evidence or "石灰" in m6_evidence or "有机肥" in m6_evidence
# AssertionError: assert ('model-4' in '[]' or ...)
```

**根因**：
- 测试问题 "我的田施氮肥施多少？这块地质量怎么样？" 不含肥力关键词，model-6 被跳过
- 跳过时 `evidence: []`，`str([]) == "[]"`
- 旧 `ComprehensiveImprovementAgent` 总是返回 `evidence: [{"source": "model-4", ...}, {"source": "model-5", ...}, ...]`，因此该断言之前 PASS
- 新 `FertilityMLAgent` 跳过时 evidence 为空，断言 FAIL

### 失败 3: `test_e2e_recommendations_aggregated` (line 150)

```python
assert len(data["recommendations"]) >= 1  # assert 0 >= 1
```

**根因**：
- 测试问题 "我的田怎么改良？" 不含肥力关键词，model-6 被跳过
- "改良" 不匹配 model-4 的 "治理"/"施加"/"调理剂"/"石灰" 关键词，else 分支无 recommendation
- "改良" 不匹配 model-5 的 "含量"/"分布"/"现状" 或 "施用量"/"有机肥" 关键词，else 分支无 recommendation
- 三方均无 recommendation/source 进入汇总 → 空列表

## Plan 指定的修复（Step 1-2）

### Step 1: 修复 `tests/test_agent_manager.py` 中 `test_manager_topological_sort_farmer`

注意：此测试当前实际 PASS（DFS 保留输入顺序，model-6 仍在末尾）。但 plan 要求弱化断言以反映新行为（model-6 无依赖，不强制排最后）。按 plan 修改：

```python
def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5, model-6]，model-6 依赖为空，
    三个 agent 均无互相依赖，拓扑排序包含全部三个。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    print("✓ 拓扑排序包含 farmer 角色全部三个智能体")
```

（移除 `assert ordered[-1] == "model-6"` 行和过时的 docstring "model-6 应排在最后"）

### Step 2: 修复 `tests/test_agent_manager.py` 中 `test_manager_process_farmer_returns_structured_result`

将问题从 "我的田施氮肥施多少" 改为 "我的田施肥施多少"（"施肥" 在 FERTILITY_KEYWORDS 中），确保 model-6 执行：

```python
def test_manager_process_farmer_returns_structured_result():
    """process 返回符合 API 规范的结构化字典"""
    mgr = AgentManager()
    result = mgr.process("我的田施肥施多少", {"area_code": "lechang"})
    # ... 其余断言保持不变
```

## 实施步骤

1. **加载 TDD skill**：`Skill: test-driven-development`
2. **RED 阶段**：运行 `python -m pytest tests/test_agent_manager.py tests/test_agent_integration.py tests/test_agent_specialized.py tests/test_agent_base.py tests/test_multi_agent.py -v` 确认上述 3 个失败用例（同时确认 `test_manager_topological_sort_farmer` 当前 PASS）
3. **GREEN 阶段 Step 1-2**：按 plan 修改 `tests/test_agent_manager.py`（Step 1 弱化断言、Step 2 改问题为 "我的田施肥施多少"）
4. **GREEN 阶段 Step 3-4**：修复 `tests/test_agent_integration.py` 3 个失败用例。**推荐方案**（implementer 可自行选择更优方案，但需在报告中说明）：
   - `test_chat_api_returns_structured_multi_agent_result`: 将问题改为包含肥力关键词且能触发 recommendation 的问题，如 "我的田施肥施石灰施有机肥多少？"（"施肥" 触发 model-6 执行，"石灰" 触发 model-4 recommendation 分支，"有机肥" 触发 model-5 recommendation 分支）
   - `test_e2e_farmer_role_routing`: 将问题改为 "我的田施肥施多少？施石灰多少？"（"施肥" 触发 model-6 执行，model-6 的 evidence 含 `{"metric": "dose_prediction", ...}` 等；断言可调整为 `"dose_prediction" in m6_evidence or "施肥" in m6_evidence`）
   - `test_e2e_recommendations_aggregated`: 将问题改为 "我的田施石灰多少？" 或 "我的田施有机肥多少？"（触发 model-4 或 model-5 的 recommendation 分支，确保 recommendations 非空）
5. **运行全量测试套件**：`python -m pytest tests/ -v`，确认全部 PASS（集成测试可能 SKIP）
6. **提交**：

```bash
git add tests/test_agent_manager.py tests/test_agent_integration.py
git commit -m "test(agent): 修复 model-6 重构导致的既有测试断言，全量测试通过"
```

## 边界与约束

- **允许修改的文件**：仅 `tests/test_agent_manager.py` 和 `tests/test_agent_integration.py`
- **禁止修改**：`framework/` 下任何文件（model_6.py、fertility_ml_agent.py、manager.py、chat.py 等），如发现需要修改 framework 文件请报告 DONE_WITH_CONCERNS
- **禁止修改的测试**：不得修改其他通过测试的断言或问题，避免范围蔓延
- **不要修改 `tests/test_agent_base.py`**：其 `test_router_get_agents_for_role` 只检查 router 输出，与 model-6 deps 无关，当前 PASS
- **不要修改 `tests/test_multi_agent.py`**：不涉及 farmer/model-6 场景，当前 PASS
- **不要修改 `tests/test_fertility_ml_prediction.py`**：Task 3 已完成，13 单元 + 3 集成测试当前 PASS
- **不要修改 `tests/test_agent_specialized.py`**：Task 4/6 已完成，6 FertilityMLAgent + 5 既有 agent 测试当前 PASS

## 风险信号自报（implementer 必须在报告中回答）

回答以下问题（是/否 + 简短说明）：
1. 跨模块/跨子系统协调改动？
2. 安全敏感面（认证/授权/加解密/SQL/外部输入/密钥）？
3. 并发/锁/共享可变状态？
4. 数据或 schema 迁移？
5. 公共 API 契约或对外接口变更？
6. 是否返回 DONE_WITH_CONCERNS？
7. 单任务 diff 超过 200 行？

## 完成标准

- 所有 3 个失败用例 PASS
- 全量测试套件 `python -m pytest tests/ -v` 全部 PASS（集成测试可能 SKIP）
- 风险信号自报 0 命中或弱命中
- 单个 commit 完成所有修复
- 报告中包含 RED 证据（失败用例清单）和 GREEN 证据（修复后 PASS 输出）

## 报告格式

完成后写入 `openspec/changes/add-model-6-fertility-ml/.comet/task-7-report.md`，包含：
- 修改文件清单
- 修改前后对比（关键 diff）
- RED 证据（pytest 失败输出片段）
- GREEN 证据（pytest PASS 输出片段，至少最后 5 行 summary）
- 风险信号自报（7 项）
- Commit hash
- 任何 Minor finding 或 concern
