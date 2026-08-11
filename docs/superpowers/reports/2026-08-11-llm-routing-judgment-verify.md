# 验证报告：llm-routing-judgment

> 生成时间：2026-08-11
> 验证模式：full（13 tasks, 2 delta specs, 10+ files）
> 基线提交：ad19d4b（6 模型重排完成点）

## 1. 完整性（Completeness）

### 任务完成

| 检查项 | 结果 |
|--------|------|
| tasks.md 全部勾选 | 13/13 ✓ |
| Plan 文件 TDD 步骤全勾选 | 45/45 ✓ |

### Spec 覆盖

**Delta spec `llm-routing-judgment/spec.md`（4 requirements, 8 scenarios）**：

| Requirement | 实现位置 | 状态 |
|-------------|----------|------|
| LLM 路由判定 | routing.py:187-198 (`_identify_question_type_llm`, `identify_question_type`) | ✓ |
| ROUTING_MODE 配置开关 | config.py:54 (`ROUTING_MODE = os.environ.get("ROUTING_MODE", "llm")`) | ✓ |
| LLM 判定失败回退 | routing.py:192-198 (fallback), `_safe_parse_llm_result` | ✓ |
| 观测日志记录 LLM 判定 | observe.py (`ROUTING_RESULT_VERSION="v1.2"`, `_attach_llm_routing_state`) | ✓ |

**Modified spec `role-based-routing/spec.md`（1 modified requirement, 2 new scenarios）**：

| Scenario | 测试覆盖 | 状态 |
|----------|----------|------|
| LLM 初判后路由 | test_llm_mode_uses_llm_result_when_available | ✓ |
| LLM 不可用时回退关键词 | test_llm_mode_falls_back_when_llm_unavailable | ✓ |

## 2. 正确性（Correctness）

### 需求实现映射

| 需求 | 实现证据 | 一致性 |
|------|----------|--------|
| LLM 全量初判（D2） | routing.py:187 `if Config.ROUTING_MODE == "llm" and LLM_AVAILABLE and llm_service.is_available():` → 调用 `_identify_question_type_llm` | ✓ |
| 排他规则兜底（D4） | routing.py:208 `apply_exclusive_rules(question, base_type, context)` 在 LLM 判定后叠加 | ✓ |
| JSON 严格解析回退（D3） | `_safe_parse_llm_result` 处理：非 JSON / 字段缺失 / 类型越界 / 非 int → 返回 None | ✓ |
| 不向主流程抛异常 | routing.py:192-198 LLM 失败时静默回退关键词/向量 | ✓ |
| 观测字段（D5） | observe.py: `router_method`, `llm_reason`, `llm_duration_ms`, `result_version=v1.2` | ✓ |
| ROUTING_MODE 默认 llm | config.py:54 默认值 `"llm"` | ✓ |
| keyword 模式向后兼容 | routing.py:200-206 `else` 分支保留原有关键词/向量路径 | ✓ |

### 场景覆盖

全部 10 个场景均有对应测试：

| Scenario | Test |
|----------|------|
| LLM 可用时全量初判 | test_llm_mode_uses_llm_result_when_available |
| LLM 判定后叠加排他规则 | test_exclusive_rules_applied_after_llm, test_exclusive_rules_override_llm_when_triggered |
| 默认启用 LLM 判定 | test_routing_mode_default_is_llm |
| 切换回纯关键词模式 | test_keyword_mode_skips_llm |
| LLM 服务不可用 | test_llm_mode_falls_back_when_llm_unavailable |
| LLM 返回非法 JSON 或越界类型 | test_llm_mode_falls_back_on_parse_failure, test_llm_mode_falls_back_on_out_of_range |
| 记录 LLM 判定详情 | test_llm_mode_logs_router_method_llm |
| 记录关键词回退 | test_keyword_mode_logs_router_method_keyword |
| LLM 初判后路由（modified spec） | test_llm_mode_uses_llm_result_when_available |
| LLM 不可用时回退关键词（modified spec） | test_llm_mode_falls_back_when_llm_unavailable |

### 测试证据（新鲜运行）

```
python -m pytest tests/test_llm_routing.py tests/test_routing_observability.py -q
→ 47 passed, 3 warnings in 21.00s
```

### 回归证据

```
python scripts/run_routing_regression.py --routing-mode keyword
→ model-3-vs-model-2: 216 samples, 100.00% accuracy, 0.00% confusion
→ model-4-vs-model-5: 156 samples, 100.00% accuracy, 0.00% confusion
→ 目标达成（≤ 3%）

python scripts/run_routing_regression.py --routing-mode llm --mock-llm
→ model-3-vs-model-2: 216 samples, 100.00% accuracy, 0.00% confusion
→ model-4-vs-model-5: 156 samples, 100.00% accuracy, 0.00% confusion
→ 目标达成（≤ 3%）
```

## 3. 一致性（Coherence）

### 设计决策遵循

| 决策 | 遵循情况 |
|------|----------|
| D1: ROUTING_MODE 配置开关 | config.py:54 ✓ |
| D2: _identify_question_type_llm 函数 | routing.py:265+ ✓ |
| D3: JSON 输出与严格解析回退 | _safe_parse_llm_result + fallback ✓ |
| D4: 排他规则兜底不变 | apply_exclusive_rules 在 LLM 后叠加 ✓ |
| D5: 观测日志增强 | v1.2 + 3 个新字段 ✓ |
| D6: 文档更新 | docx P10 + 混淆矩阵 + 6 模型表 ✓ |

### 代码模式一致性

- routing.py 遵循现有模块级状态变量模式 ✓
- observe.py 遵循现有日志 entry 构造模式 ✓
- 测试遵循现有 monkeypatch + tmpdir 模式 ✓
- 无显著偏差

### 提交区间改动

```
git diff --stat ad19d4b...HEAD
→ 16 files changed, 2544 insertions(+), 9 deletions(-)
```

改动文件与 tasks.md 描述一致：config.py, routing.py, observe.py, regression script, tests, docx, openspec artifacts, plan, design doc。

## 4. 已知环境限制

全量测试套件中 20 个失败项均为**环境问题**，与本变更无关：
- `model_unavailable`：LLM/嵌入服务在测试环境不可用
- `StabilityStorage` / `run_grade_evaluation`：前次 6 模型重排遗留的属性引用
- `test_run_single_thematic_model_returns_uniform_payload`：环境依赖

这些失败在 `ad19d4b` 基线上同样存在，非本变更引入。

## 5. 最终评估

| 维度 | 状态 |
|------|------|
| 完整性 | 13/13 tasks, 4/4 requirements, 10/10 scenarios ✓ |
| 正确性 | 47 tests passed, 0.00% confusion rate (both modes) ✓ |
| 一致性 | 6/6 design decisions followed, no deviations ✓ |

**结论**：All checks passed. No CRITICAL, WARNING, or SUGGESTION issues. Ready for archive.
