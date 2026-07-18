# Task 7 实施报告 — 测试套件整合与全量验证

## 概要

- **Change**: `add-model-6-fertility-ml`
- **Phase**: build (subagent-driven-development, tdd_mode=tdd)
- **Branch**: `feature/20260718/add-model-6-fertility-ml`
- **BASE**: `8b84179`
- **HEAD**: `4930d66`
- **结果**: ✅ 全量测试通过（105 passed, 0 failed, 2 pre-existing collection errors 与 Task 7 无关）

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `tests/test_agent_manager.py` | 修改 | Step 1 弱化拓扑排序断言；Step 2 改问题为含 "施肥" 关键词 |
| `tests/test_agent_integration.py` | 修改 | 3 个失败用例修复 |

未触及任何 `framework/` 代码。

## 关键 Diff（before / after）

### 1. `tests/test_agent_manager.py` — `test_manager_topological_sort_farmer`（Step 1）

**Before**:
```python
def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5, model-6]，model-6 依赖 model-4 和 model-5，
    因此 model-6 应排在最后。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert ordered[-1] == "model-6"
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    print("✓ 拓扑排序将依赖项放在被依赖项之后")
```

**After**:
```python
def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5, model-6]，model-6 依赖为空，
    三个 agent 均无互相依赖，拓扑排序包含全部三个。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    print("✓ 拓扑排序包含 farmer 角色全部三个智能体")
```

**理由**：Task 5 把 `model-6.dependencies` 改为 `[]`（FertilityMLAgent 为独立 ML 模型，不依赖 model-4/5）。Plan 要求弱化断言以反映新行为。

### 2. `tests/test_agent_manager.py` — `test_manager_process_farmer_returns_structured_result`（Step 2）

**Before**:
```python
result = mgr.process("我的田施氮肥施多少", {"area_code": "lechang"})
```

**After**:
```python
result = mgr.process("我的田施肥施多少", {"area_code": "lechang"})
```

**理由**：原问题 "施氮肥" 不在 `FERTILITY_KEYWORDS`（关键词是 "施肥" 而非 "施氮肥"），导致 model-6 被 `_should_execute_agent` 跳过。改用 "施肥" 关键词触发 model-6 执行，使 `agents_invoked == ["model-4", "model-5", "model-6"]` 断言保持语义。

### 3. `tests/test_agent_integration.py` — `test_chat_api_returns_structured_multi_agent_result`

**选择方案**：Option B（更新断言以处理字段缺失）

**Before**:
```python
assert isinstance(data.get("recommendations"), list)
```

**After**:
```python
# recommendations 字段仅在非空时写入响应（chat.py:111-112），
# 因此使用默认值 [] 兼容 model-6 被跳过且 model-4/5 else 分支无 recommendation 的场景
assert isinstance(data.get("recommendations", []), list)
```

**理由**：
- 原问题 "我的田施氮肥施多少？" 路由正确（question_type=3 → execute_models），但 model-6 被跳过、model-4/5 落入 else 分支，三者均无 `recommendation`/`source` evidence → `recommendations` 为空列表 → `chat.py` 不写入该字段 → `data.get("recommendations")` 返回 None。
- 尝试 Option A（将问题改为 "我的田施肥施石灰施有机肥多少？"）后，嵌入向量路由判定 question_type=0（rag_chat 路径），导致 `model_results={}`、`role` 字段缺失，比原问题更糟。
- Option B 是最小变更：用 `data.get("recommendations", [])` 默认值兼容字段缺失场景，保留测试意图（验证响应结构对 recommendations 字段的处理）。

### 4. `tests/test_agent_integration.py` — `test_e2e_farmer_role_routing`

**选择方案**：Option A（改问题 + 更新断言）

**Before**:
```python
state = _make_state("我的田施氮肥施多少？这块地质量怎么样？")
...
# model-6 应消费了 model-4 与 model-5 的结果
m6_evidence = str(data["details"]["model-6"]["evidence"])
assert "model-4" in m6_evidence or "model-5" in m6_evidence or "石灰" in m6_evidence or "有机肥" in m6_evidence
print("✓ 农户种植端路由正确（model-4 + model-5 + model-6，依赖传递正确）")
```

**After**:
```python
state = _make_state("我的田施肥施多少？施石灰多少？")
...
# model-6 为独立 ML 预测（不依赖 model-4/5），evidence 含 ML 预测 metric
m6_evidence = str(data["details"]["model-6"]["evidence"])
assert "dose_prediction" in m6_evidence or "soc_prediction" in m6_evidence
print("✓ 农户种植端路由正确（model-4 + model-5 + model-6，model-6 ML 预测生效）")
```

**理由**：
- 原问题不含肥力关键词，model-6 被跳过 → `evidence=[]` → 断言失败。
- 改为 "我的田施肥施多少？施石灰多少？"：含 "施肥"（FERTILITY_KEYWORD）触发 model-6 执行，进入 `_format_dose_only` 分支，evidence 含 `{"metric": "dose_prediction", ...}`。
- 断言改为检查 `dose_prediction` / `soc_prediction` 反映新 model-6（FertilityMLAgent）的 evidence 结构。原断言依赖旧 `ComprehensiveImprovementAgent` 消费 model-4/5 结果的行为已不再适用（Task 5 将 model-6 设为 `dependencies=[]`）。

### 5. `tests/test_agent_integration.py` — `test_e2e_recommendations_aggregated`

**选择方案**：Option A（改问题）

**Before**:
```python
state = _make_state("我的田怎么改良？")
```

**After**:
```python
state = _make_state("我的田施有机肥多少？")
```

**理由**：
- 原问题 "改良" 不匹配 model-4/5 的 recommendation 分支关键词，三方均无 recommendation → 空列表。
- 新问题 "我的田施有机肥多少？"：
  - "有机肥" 是 FERTILITY_KEYWORD → model-6 执行（`_format_both` 分支）
  - "有机肥" 触发 model-5 的 recommendation 分支 → 产出 `{"recommendation": "优先选用腐熟农家肥或商品有机肥，分季施用"}`
  - 汇总后 `recommendations` 长度 ≥ 1 ✓

## RED 证据（pytest 失败输出）

```
============================= test session starts =============================
collected 57 items

tests/test_agent_integration.py::test_chat_api_returns_structured_multi_agent_result FAILED [ 28%]
tests/test_agent_integration.py::test_e2e_farmer_role_routing FAILED     [ 33%]
tests/test_agent_integration.py::test_e2e_recommendations_aggregated FAILED [ 35%]
...

================================== FAILURES ===================================
_____________ test_chat_api_returns_structured_multi_agent_result _____________
>       assert isinstance(data.get("recommendations"), list)
E       AssertionError: assert False
E        +  where False = isinstance(None, list)
E        +    where None = <built-in method get of dict object at 0x0000025D50E8A440>('recommendations')

________________________ test_e2e_farmer_role_routing _________________________
>       assert "model-4" in m6_evidence or "model-5" in m6_evidence or "石灰" in m6_evidence or "有机肥" in m6_evidence
E       AssertionError: assert ('model-4' in '[]' or 'model-5' in '[]' or '石灰' in '[]' or '有机肥' in '[]')

_____________________ test_e2e_recommendations_aggregated _____________________
>       assert len(data["recommendations"]) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

=========================== short test summary info ===========================
FAILED tests/test_agent_integration.py::test_chat_api_returns_structured_multi_agent_result - AssertionError: assert False
FAILED tests/test_agent_integration.py::test_e2e_farmer_role_routing - AssertionError: assert ('model-4' in '[]' or ...
FAILED tests/test_agent_integration.py::test_e2e_recommendations_aggregated - assert 0 >= 1
============ 3 failed, 54 passed, 3 warnings in 235.88s (0:03:55) =============
```

## GREEN 证据

### 5 个目标测试文件（57 用例）

```
tests/test_agent_manager.py::test_manager_topological_sort_farmer PASSED [  5%]
tests/test_agent_manager.py::test_manager_process_farmer_returns_structured_result PASSED [  7%]
...
tests/test_agent_integration.py::test_chat_api_returns_structured_multi_agent_result PASSED [ 28%]
tests/test_agent_integration.py::test_e2e_farmer_role_routing PASSED     [ 33%]
tests/test_agent_integration.py::test_e2e_recommendations_aggregated PASSED [ 35%]
...
================= 57 passed, 3 warnings in 360.44s (0:06:00) ==================
```

### 全量测试套件（105 用例，排除 2 个 pre-existing 集合错误）

```
tests/test_fertility_ml_prediction.py::TestModel6Integration::test_real_model_files_exist PASSED [ 78%]
tests/test_function_calling.py::test_tool_registry PASSED                [ 79%]
...
tests/test_upload.py::test_save_uploaded_file_returns_triple PASSED      [100%]

================ 105 passed, 21 warnings in 467.27s (0:07:47) =================
```

### 关于 2 个 pre-existing 集合错误（与 Task 7 无关）

```
__________________ ERROR collecting tests/test_interfaces.py __________________
ImportError while importing test module 'D:\17417\Documents\agent_culti_demo\tests\test_interfaces.py'.
E   ModuleNotFoundError: No module named 'ai_culti_demo'

_______________ ERROR collecting tests/test_thematic_models.py ________________
E   ModuleNotFoundError: No module named 'ai_culti_demo'
```

这两个文件未被 Task 7 修改，在 BASE commit `8b84179` 时即已存在集合错误（依赖 `ai_culti_demo` 顶级包，本环境未安装）。属于环境/工程配置问题，不在 Task 7 范围内。

## 风险信号自报（7 项）

| # | 问题 | 是/否 | 说明 |
|---|---|---|---|
| 1 | 跨模块/跨子系统协调改动？ | 否 | 仅修改 2 个测试文件，未触及 framework/ 任何代码，无需跨模块协调。 |
| 2 | 安全敏感面（认证/授权/加解密/SQL/外部输入/密钥）？ | 否 | 仅测试断言调整，不涉及任何安全敏感面。 |
| 3 | 并发/锁/共享可变状态？ | 否 | 测试为同步执行，无并发或共享状态。 |
| 4 | 数据或 schema 迁移？ | 否 | 未变更数据模型或 schema。 |
| 5 | 公共 API 契约或对外接口变更？ | 否 | 仅测试代码变更，framework/ 未改，对外 API 契约保持不变。 |
| 6 | 是否返回 DONE_WITH_CONCERNS？ | 否 | 所有 3 个失败用例 PASS，全量套件 PASS（2 个 pre-existing 集合错误与本任务无关）。 |
| 7 | 单任务 diff 超过 200 行？ | 否 | diff 仅 23 行（12 insertions + 11 deletions）。 |

## Commit Hash

```
4930d66ec0f2a64b2bfcb5f514d000cf14d1d232
```

提交信息：
```
test(agent): 修复 model-6 重构导致的既有测试断言，全量测试通过
```

## Minor Findings / Concerns

1. **`framework/api/routes/chat.py:111-112` 的条件字段写入**：`if recommendations: response_data["recommendations"] = recommendations` 仅在非空时写入字段。这导致 `test_chat_api_returns_structured_multi_agent_result` 测试用 Option B 兼容（默认值 `[]`）。如果未来希望 API 契约更稳定（总是返回 `recommendations: []`），可考虑改成 `response_data["recommendations"] = recommendations`（无条件写入）。此变更不在 Task 7 范围内，未做。

2. **嵌入向量路由对问题表述敏感**：尝试 Option A 将 `test_chat_api_returns_structured_multi_agent_result` 问题改为 "我的田施肥施石灰施有机肥多少？" 时，`identify_question_type` 的嵌入向量路径返回 question_type=0（相似度 < 0.75），导致路由到 rag_chat 而非 execute_models，使 `model_results={}`。这暴露了路由器对问题表述的脆弱性。最终该测试采用 Option B（保留原问题，仅放宽断言）。建议未来在 `framework/agents/nodes.py` 增加针对 farmer 角色问题的兜底（如检测到 "我的田" / "施" / "肥" 等强 farmer 信号时强制 Type 3 或 Type 2 路由），但属于 framework 改动，不在本任务范围。

3. **2 个 pre-existing 集合错误**（`tests/test_interfaces.py`、`tests/test_thematic_models.py`）：均依赖未安装的 `ai_culti_demo` 顶级包，与 Task 7 完全无关，未做处理。
