# Conservative Test Suite Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove eight pytest cases that provide no unique regression protection while preserving one working public-entry stability test and all business, compatibility, specification, and environment-conditional coverage.

**Architecture:** This is a test-only cleanup. Four files lose assertion-free, migration-only, or duplicate fixture-size checks; one integration file collapses three equivalent stability happy-path tests into one canonical test that uses the existing Flask application-context fixture.

**Tech Stack:** Python 3.12, pytest 9.1.1, Flask application context, Git.

## Global Constraints

- Do not modify production code.
- Do not delete OpenSpec synchronization, public API, compatibility, database-conditional, or helper-assertion tests.
- Preserve the user's existing modifications to `docs/superpowers/plans/2026-08-25-kb-semantic-enrichment.md` and `docs/superpowers/specs/2026-08-25-kb-semantic-enrichment-design.md`.
- Run pytest with `D:\miniconda3\python.exe -B -m pytest -p no:cacheprovider` from `D:\17417\Documents\agent_culti_demo`.
- The final suite must collect 783 tests, with no failures and only environment-conditional skips.

## File Map

- Modify `tests/test_multi_agent.py`: remove the assertion-free routing smoke test and its manual runner call.
- Modify `tests/test_agent_manager.py`: remove three negative assertions for private symbols deleted during a completed migration and their manual runner calls.
- Modify `tests/test_question_type_router.py`: remove the completed-migration `RoleRouter` absence check and its manual runner call.
- Modify `tests/test_question_type_keywords.py`: remove one of two equivalent batch-size meta-tests.
- Modify `tests/test_stability_and_grade_integration.py`: keep one canonical stability happy path, supply its existing Flask fixture, and remove two duplicate entry-path tests.

---

### Task 1: Remove assertion-free, migration-only, and duplicate meta-tests

**Files:**
- Modify: `tests/test_multi_agent.py:38-52,163-170`
- Modify: `tests/test_agent_manager.py:182-224`
- Modify: `tests/test_question_type_router.py:65-78`
- Modify: `tests/test_question_type_keywords.py:401-414`

**Interfaces:**
- Consumes: Existing positive behavior tests for `identify_question_type`, `AgentManager.process`, `QuestionTypeRouter.get_agents_for_type`, and `_expand` routing batches.
- Produces: Four test modules containing 68 source-level test functions in total: 6, 17, 4, and 41 respectively.

- [ ] **Step 1: Capture the five obsolete test nodes and one duplicate meta-test in the current collection**

Run:

```powershell
Set-Location -LiteralPath 'D:\17417\Documents\agent_culti_demo'
& 'D:\miniconda3\python.exe' -B -m pytest -p no:cacheprovider --collect-only -q tests/test_multi_agent.py tests/test_agent_manager.py tests/test_question_type_router.py tests/test_question_type_keywords.py
```

Expected: collection includes these six nodes:

```text
tests/test_multi_agent.py::test_question_type_identification
tests/test_agent_manager.py::test_should_execute_agent_method_removed
tests/test_agent_manager.py::test_fertility_keywords_constant_removed
tests/test_agent_manager.py::test_grade_keywords_constant_removed
tests/test_question_type_router.py::test_role_router_removed
tests/test_question_type_keywords.py::test_confusing_pair_positive_and_negative_batches_ge_20
```

- [ ] **Step 2: Remove the assertion-free multi-agent smoke test**

Delete this function from `tests/test_multi_agent.py`:

```python
def test_question_type_identification():
    """测试问题类型识别"""
    # 测试通用问题
    q_type, relevance = identify_question_type("今天天气怎么样？")
    print(f"  通用问题: type={q_type}, relevance={relevance:.2f}")

    # 测试酸化评估问题
    q_type, relevance = identify_question_type("全省耕地酸化程度如何？")
    print(f"  酸化评估: type={q_type}, relevance={relevance:.2f}")

    # 测试治理方案问题
    q_type, relevance = identify_question_type("如何治理强酸性耕地？")
    print(f"  治理方案: type={q_type}, relevance={relevance:.2f}")

    print("✓ 问题类型识别成功")
```

Also delete this line from the `__main__` block:

```python
test_question_type_identification()
```

Remove the now-unused name from the import list:

```diff
     aggregate_results,
     check_relevance,
-    identify_question_type,
 )
```

- [ ] **Step 3: Remove three completed-migration checks from AgentManager tests**

Delete these complete function blocks from `tests/test_agent_manager.py`:

```python
def test_should_execute_agent_method_removed():
    """_should_execute_agent 方法应已删除"""
    mgr = AgentManager()
    assert not hasattr(mgr, "_should_execute_agent"), "_should_execute_agent 仍存在"
    print("✓ _should_execute_agent 已移除")


def test_fertility_keywords_constant_removed():
    """FERTILITY_KEYWORDS 常量应已删除"""
    import framework.agents.manager as mgr_mod
    assert not hasattr(mgr_mod, "FERTILITY_KEYWORDS"), "FERTILITY_KEYWORDS 仍存在"
    print("✓ FERTILITY_KEYWORDS 已移除")


def test_grade_keywords_constant_removed():
    """GRADE_KEYWORDS 常量应已删除"""
    import framework.agents.manager as mgr_mod
    assert not hasattr(mgr_mod, "GRADE_KEYWORDS"), "GRADE_KEYWORDS 仍存在"
    print("✓ GRADE_KEYWORDS 已移除")
```

Delete their three calls from the `__main__` block:

```python
test_should_execute_agent_method_removed()
test_fertility_keywords_constant_removed()
test_grade_keywords_constant_removed()
```

The positive routing and execution tests immediately above them remain unchanged.

- [ ] **Step 4: Remove the completed RoleRouter migration check**

Delete this complete function from `tests/test_question_type_router.py`:

```python
def test_role_router_removed():
    """RoleRouter 类已移除"""
    import framework.agents.router as router_mod
    assert not hasattr(router_mod, "RoleRouter"), "RoleRouter 仍存在，应已删除"
    print("✓ RoleRouter 已移除")
```

Delete this call from the `__main__` block:

```python
test_role_router_removed()
```

- [ ] **Step 5: Remove the duplicate routing-batch size test**

Delete this complete function from `tests/test_question_type_keywords.py`; keep `test_all_confusing_pair_batches_size_ge_20` immediately above it:

```python
def test_confusing_pair_positive_and_negative_batches_ge_20():
    """两组易混淆对的正例与反例批量均 ≥20（反例与正例同源句干联动）。"""
    for name, stems in (("model-3", MODEL3_STEMS), ("model-2", MODEL2_STEMS),
                        ("model-4", MODEL4_STEMS), ("model-5", MODEL5_STEMS)):
        batch = _expand(stems, PREFIXES, SUFFIXES)
        assert len(batch) >= 20, f"{name} 正例/反例批量应 ≥20，实际 {len(batch)}"
```

- [ ] **Step 6: Run the four modified modules**

Run:

```powershell
Set-Location -LiteralPath 'D:\17417\Documents\agent_culti_demo'
& 'D:\miniconda3\python.exe' -B -m pytest -p no:cacheprovider -q tests/test_multi_agent.py tests/test_agent_manager.py tests/test_question_type_router.py tests/test_question_type_keywords.py
```

Expected: 68 tests pass and none of the six deleted node IDs appear.

- [ ] **Step 7: Commit Task 1 without staging unrelated documentation**

```powershell
git add -- tests/test_multi_agent.py tests/test_agent_manager.py tests/test_question_type_router.py tests/test_question_type_keywords.py
git commit -m "test: remove obsolete routing checks"
```

Expected: the commit contains only the four test files.

---

### Task 2: Consolidate the stability-model public-entry happy path

**Files:**
- Modify: `tests/test_stability_and_grade_integration.py:97-124,221-247,466-495`

**Interfaces:**
- Consumes: Existing `flask_app_context` pytest fixture and `run_thematic_model(payload: dict) -> dict` public entry point.
- Produces: One canonical success-path test named `TestStabilityOnlineQuery::test_normal_query_returns_ok` covering status, model ID, reliability, and analysis payload.

- [ ] **Step 1: Reproduce the three equivalent failures**

Run:

```powershell
Set-Location -LiteralPath 'D:\17417\Documents\agent_culti_demo'
& 'D:\miniconda3\python.exe' -B -m pytest -p no:cacheprovider -q tests/test_stability_and_grade_integration.py::TestStabilityOnlineQuery::test_normal_query_returns_ok tests/test_stability_and_grade_integration.py::TestCoreEngineDispatch::test_dispatch_stability_with_parcel_id tests/test_stability_and_grade_integration.py::TestEndToEndIntegration::test_e2e_stability_full_pipeline
```

Expected: all three fail because `out["status"]` is `"degraded"` after a `Working outside of application context` persistence error.

- [ ] **Step 2: Supply the existing Flask fixture to the canonical test**

Change only the canonical test signature:

```diff
-    def test_normal_query_returns_ok(self):
+    def test_normal_query_returns_ok(self, flask_app_context):
```

Keep its existing mock indicators and assertions:

```python
assert out["status"] == "ok"
assert out["model"]["model_id"] == "stability-risk-evaluation"
assert out["reliability"]["level"] == "real_model"
assert "stability_modules" in out["analysis"]
```

- [ ] **Step 3: Delete the two duplicate success-path methods**

Delete these complete methods, including their decorators, mock dictionaries, public-entry calls, and assertions:

```python
@geopandas_required
def test_dispatch_stability_with_parcel_id(self):
    """stability-risk-evaluation + parcel_id 调用实际模型（analyze 包络 real_model）"""
    from ai_culti_demo.thematic_models import run_thematic_model

    mock_indicators = {
        "soil_ph": 5.5, "organic_matter": 20.0, "available_phosphorus": 15.0,
        "available_potassium": 100.0, "bulk_density": 1.2, "topsoil_thickness": 80.0,
        "plow_layer_thickness": 15.0, "soil_texture": "loam",
        "irrigation_condition": "irrigated", "drainage_capacity": "satisfied",
        "terrain_position": "lower", "soil_structure": "loose",
    }

    with patch("framework.agents.specialized.stability_agent.ParcelDataAccessor") as MockAccessor:
        MockAccessor.return_value.get_parcel_indicators.return_value = mock_indicators
        MockAccessor.return_value._map_indicators_to_inputs.return_value = mock_indicators
        out = run_thematic_model({
            "model_id": "stability-risk-evaluation",
            "parcel_id": "P001",
        })

    assert out["status"] == "ok"
    assert out["reliability"]["level"] == "real_model"


@geopandas_required
def test_e2e_stability_full_pipeline(self):
    """端到端：稳定性模型从调度到响应结构（analyze 包络）"""
    from ai_culti_demo.thematic_models import run_thematic_model

    mock_indicators = {
        "soil_ph": 5.5, "organic_matter": 20.0, "available_phosphorus": 15.0,
        "available_potassium": 100.0, "bulk_density": 1.2, "topsoil_thickness": 80.0,
        "plow_layer_thickness": 15.0, "soil_texture": "loam",
        "irrigation_condition": "irrigated", "drainage_capacity": "satisfied",
        "terrain_position": "lower", "soil_structure": "loose",
    }

    with patch("framework.agents.specialized.stability_agent.ParcelDataAccessor") as MockAccessor:
        MockAccessor.return_value.get_parcel_indicators.return_value = mock_indicators
        MockAccessor.return_value._map_indicators_to_inputs.return_value = mock_indicators
        out = run_thematic_model({
            "model_id": "stability-risk-evaluation",
            "parcel_id": "E2E001",
        })

    assert out["status"] == "ok"
    assert out["model"]["model_id"] == "stability-risk-evaluation"
    assert out["reliability"]["level"] == "real_model"
    assert out["fallback"]["used"] is False
    assert "analysis" in out
```

Do not change the grade-model tests or any degraded-path stability tests in those classes.

- [ ] **Step 4: Run the canonical test**

Run:

```powershell
Set-Location -LiteralPath 'D:\17417\Documents\agent_culti_demo'
& 'D:\miniconda3\python.exe' -B -m pytest -p no:cacheprovider -q tests/test_stability_and_grade_integration.py::TestStabilityOnlineQuery::test_normal_query_returns_ok
```

Expected: `1 passed` with no application-context persistence error.

- [ ] **Step 5: Run all five modified modules**

Run:

```powershell
Set-Location -LiteralPath 'D:\17417\Documents\agent_culti_demo'
& 'D:\miniconda3\python.exe' -B -m pytest -p no:cacheprovider -q tests/test_multi_agent.py tests/test_agent_manager.py tests/test_question_type_router.py tests/test_question_type_keywords.py tests/test_stability_and_grade_integration.py
```

Expected: 91 tests pass, with no failures.

- [ ] **Step 6: Run the full suite**

Run:

```powershell
Set-Location -LiteralPath 'D:\17417\Documents\agent_culti_demo'
& 'D:\miniconda3\python.exe' -B -m pytest -p no:cacheprovider -q tests
```

Expected: `761 passed, 22 skipped` and `783` total collected, with no failures. Warnings already present in the baseline are allowed.

- [ ] **Step 7: Verify scope and commit Task 2**

Run:

```powershell
git diff --check
git status --short
git diff -- tests/test_stability_and_grade_integration.py
```

Expected: no whitespace errors; the only unstaged user changes remain the two pre-existing 2026-08-25 documentation files and this implementation plan if it has not been committed separately.

Commit only the integration test:

```powershell
git add -- tests/test_stability_and_grade_integration.py
git commit -m "test: consolidate stability integration coverage"
```

Expected: the commit contains only `tests/test_stability_and_grade_integration.py`.
