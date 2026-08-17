---
change: persist-routing-observability
design-doc: docs/superpowers/specs/2026-08-17-persist-routing-observability-design.md
base-ref: 54e12f7c169aaee005739f017ac51e0e5553e637
---

# 路由可观测性数据库持久化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Each task uses a single `- [ ]` checkbox for comet guard tracking.

**Goal:** 将路由可观测性体系从纯文件存储升级为 DB 持久化（双写 + 动态规则 + 矩阵落库），保持 JSONL 作为降级备份与现有看板消费链不变。

**Architecture:** 复用 `framework/models/thematic_model.py` 已注册的 `RoutingDecisionLog` / `ModelEvaluationMetrics` / `ExclusiveRuleConfig` ORM 模型；在 `framework/observability/routing_log.py` 新增 DB 写入层（双写 + try/except 隔离 + JSONL 始终写入）；在 `framework/agents/exclusive_rules.py` 新增 `from_database()` + 模块级缓存 + `_get_active_rules()` 统一入口（DB 异常/为空回退硬编码）；在 `scripts/run_routing_regression.py` 新增 `write_metrics_to_db()` 批量落库。entry 字段对齐 `routing_decision_log` 表（`duration_ms`→`total_duration_ms` 完全重命名 + 新增 `relevance`/`five_dim_context`/`logged_at`）。

**Tech Stack:** Python 3.10+、Flask-SQLAlchemy 3.x、SQLAlchemy、PostgreSQL 16 + PostGIS 3.4、pytest。

## Global Constraints

- **数据库后端**：PostgreSQL 16 + PostGIS 3.4（`framework/config.py` 默认 `SQLALCHEMY_DATABASE_URI = postgresql+psycopg2://...`，`SQLiteConfig` 仅供测试套件临时数据库）。
- **任务 1.x 已完成**：`RoutingDecisionLog` / `ModelEvaluationMetrics` / `ExclusiveRuleConfig` 三个 ORM 模型已通过 `2026-08-16-add-thematic-model-orm` 变更定义于 `framework/models/thematic_model.py` L368-444，并已通过 `framework/models/__init__.py` 注册与 `init_db.py` 的 `db.create_all()` 建表。本计划只覆盖任务 2.x-7.x。
- **不删除 JSONL 文件存储**：作为降级备份与现有看板消费链保留；DB 失败时仅 `warnings.warn`，不传播异常。
- **不修改路由判定逻辑**：`identify_question_type`、`apply_exclusive_rules` 的匹配算法不变；`_get_active_rules()` 仅替换规则数据源。
- **`duration_ms`→`total_duration_ms` 完全重命名**（不保留别名，遵循 Design Doc §3.2.1 决策；OpenSpec tasks.md 3.4 "保留别名" 已被 Design Doc 否决）。
- **`five_dim_context` 仅保存 4 字段**（scale/data_type/business_task/expected_output），parcel_id/parcel_code 不入此字段（避免与 `model_execution_log.parcel_id` 重复存储）。
- **排他规则缓存运行时不自动刷新**：用户决策不引入后台线程，运行时配置变更需手动调用 `refresh_rules_cache()`。
- **测试依赖本地 PG**：`tests/conftest.py` 增加 `PG_AVAILABLE` 探测与 `@pytest.mark.skipif(not PG_AVAILABLE)` 跳过机制，避免无 PG 环境失败。
- **提交节奏**：每个任务结束 commit 一次；commit message 前缀 `feat:`/`refactor:`/`test:`/`chore:`。
- **DB 写入异常隔离边界**：`write_routing_log_to_db` 内部异常抛出 → `write_routing_log` 用 try/except 隔离并 `warnings.warn` → `observe._safe_write_log` 已有外层 try/except 兜底，DB 异常不影响路由主流程。

---

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `framework/observability/routing_log.py` | 修改 | 新增 `write_routing_log_to_db(entry)`；改造 `write_routing_log(entry)` 为双写 |
| `framework/observability/observe.py` | 修改 | entry 字段对齐：`duration_ms`→`total_duration_ms`、新增 `relevance`/`five_dim_context`/`logged_at`；`_matched_rules` 使用 `_get_active_rules()` |
| `framework/agents/exclusive_rules.py` | 修改 | 新增 `from_database()`/`_get_active_rules()`/`refresh_rules_cache()` + 模块级 `_db_rules_cache`；`apply_exclusive_rules` 使用 `_get_active_rules()` |
| `scripts/run_routing_regression.py` | 修改 | 新增 `write_metrics_to_db(matrix, evaluation_mode)`；`main()` 末尾调用 |
| `tests/conftest.py` | 修改 | 新增 `PG_AVAILABLE` 探测 + `pg_available` fixture |
| `tests/test_routing_log_db.py` | 新建 | 路由日志双写测试（PG 测试库） |
| `tests/test_exclusive_rules_db.py` | 新建 | 排他规则动态加载测试（PG 测试库） |
| `tests/test_regression_metrics_db.py` | 新建 | 混淆矩阵落库测试（PG 测试库） |
| `tests/test_routing_observability.py` | 修改 | L69 断言 `duration_ms`→`total_duration_ms` |

---

## Pre-flight：任务 1.x 已完成（仅校验，无需实现）

任务 1.x 已通过 `2026-08-16-add-thematic-model-orm` 变更完成，实施时只需校验存在性，不得重复创建：

- **1.1** `framework/models/thematic_model.py:368` 已定义 `RoutingDecisionLog`（表 `routing_decision_log`），16 个字段与 Design Doc §3.1.1 字段映射表完全一致。
- **1.2** `framework/models/thematic_model.py:401` 已定义 `ModelEvaluationMetrics`（表 `model_evaluation_metrics`），12 个字段。
- **1.3** `framework/models/thematic_model.py:425` 已定义 `ExclusiveRuleConfig`（表 `exclusive_rule_config`），10 个字段。
- **1.4** `framework/models/__init__.py:28-30` 已注册三个模型（`RoutingDecisionLog` / `ModelEvaluationMetrics` / `ExclusiveRuleConfig`）。
- **1.5** `init_db.py:47` 的 `db.create_all()` 已包含三张新表（PG 路径下自动建表 + V3.0 视图）。

**本计划只覆盖任务 2.x-7.x。**

---

## 任务 0.x：前置准备 — 导出 `db` 到 `framework/models/__init__.py`

### Task 0.1：在 `framework/models/__init__.py` 导出 `db`

- [x] **任务 0.1 完成**：在 `framework/models/__init__.py` 顶部新增 `from .user import db`，使后续任务中的 `from framework.models import db` 导入可用

**背景**：当前 `db = SQLAlchemy()` 定义于 `framework/models/user.py:4`，但 `framework/models/__init__.py` 未导出 `db`。现有代码使用 `from framework.models.user import db`。本计划后续任务（2.1、4.1、5.1）的代码片段使用 `from framework.models import db, ...`，需要 `__init__.py` 导出 `db` 才能工作。本任务统一导出路径。

**Files:**
- Modify: `framework/models/__init__.py`

**实施步骤:**

1. **修改 `framework/models/__init__.py`**：在文件最顶部（所有 model import 之前）新增一行：

```python
from .user import db
```

2. **冒烟验证**：

```bash
python -c "from framework.models import db, RoutingDecisionLog, ExclusiveRuleConfig, ModelEvaluationMetrics; print('ok', db, RoutingDecisionLog.__tablename__)"
```
Expected: `ok <SQLAlchemy object> routing_decision_log`

3. **提交**：

```bash
git add framework/models/__init__.py
git commit -m "chore(models): export db from framework.models for unified import path"
```

---

## 任务 2.x：路由日志 DB 双写层（Design Doc §3.1）

### Task 2.1：新增 `write_routing_log_to_db(entry)` 函数

- [x] **任务 2.1 完成**：在 `framework/observability/routing_log.py` 新增 `write_routing_log_to_db(entry)` 函数，封装 SQLAlchemy session 写入 `routing_decision_log` 表

**Files:**
- Modify: `framework/observability/routing_log.py`

**Interfaces:**
- Consumes: `framework.models.db`、`framework.models.RoutingDecisionLog`（任务 1.x 已就绪）
- Produces: `write_routing_log_to_db(entry: Dict[str, Any]) -> None`（供 Task 2.2 调用；内部异常抛出由调用方 try/except 隔离）

**实施步骤:**

1. **修改 `framework/observability/routing_log.py`**：在 `write_routing_log` 函数前新增 `write_routing_log_to_db`：

```python
def write_routing_log_to_db(entry: Dict[str, Any]) -> None:
    """将 entry 写入 routing_decision_log 表。

    抛出所有异常由调用方 try/except 隔离（IntegrityError/OperationalError/字段缺失等）。
    """
    from framework.models import db, RoutingDecisionLog
    log = RoutingDecisionLog(
        trace_id=entry["trace_id"],
        question=entry["question"],
        question_type=entry["question_type"],
        relevance=entry.get("relevance"),
        routing_status=entry.get("routing_status", "normal"),
        router_method=entry.get("router_method", "keyword"),
        candidate_agents=entry.get("candidate_agents"),
        hit_exclusive_rules=entry.get("hit_exclusive_rules"),
        llm_reason=entry.get("llm_reason"),
        llm_duration_ms=entry.get("llm_duration_ms"),
        total_duration_ms=entry.get("total_duration_ms"),
        degradation=entry.get("degradation"),
        five_dim_context=entry.get("five_dim_context"),
        data_version=entry.get("data_version"),
        agent_version=entry.get("agent_version"),
        result_version=entry.get("result_version", "v1.2"),
        failure_reason=entry.get("failure_reason"),
        logged_at=entry.get("logged_at"),
    )
    db.session.add(log)
    db.session.commit()
```

2. **冒烟验证（仅校验导入，DB 功能性验证在 Task 6.1）**：

```bash
python -c "from framework.observability.routing_log import write_routing_log_to_db; print('ok')"
```
Expected: `ok`

3. **提交**：

```bash
git add framework/observability/routing_log.py
git commit -m "feat(observability): add write_routing_log_to_db for routing_decision_log persistence"
```

---

### Task 2.2：修改 `write_routing_log(entry)` 实现双写

- [x] **任务 2.2 完成**：改造 `write_routing_log(entry)` 为双写：先写 DB（失败告警并回退 JSONL），JSONL 始终写入作为降级备份

**Files:**
- Modify: `framework/observability/routing_log.py:47-54`

**Interfaces:**
- Consumes: `write_routing_log_to_db(entry)`（Task 2.1 产出）
- Produces: 双写版 `write_routing_log(entry)`（供 `observe._safe_write_log` 调用；DB 异常仅 `warnings.warn` 不传播）

**实施步骤:**

1. **修改 `framework/observability/routing_log.py` 的 `write_routing_log`**：替换原实现为双写版本：

```python
def write_routing_log(entry: Dict[str, Any]) -> None:
    """双写：先写 DB，DB 失败告警并回退 JSONL；JSONL 始终写入作为降级备份。"""
    # 1. 先写 DB（失败仅告警，不传播）
    try:
        write_routing_log_to_db(entry)
    except Exception as exc:
        warnings.warn(f"[observability] routing_decision_log DB 写入失败，回退 JSONL: {exc}")

    # 2. JSONL 始终写入（降级备份 + 现有看板消费链）
    path = _resolve_log_path()
    if path is None:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

2. **冒烟验证**：

```bash
python -c "import inspect; from framework.observability.routing_log import write_routing_log; src=inspect.getsource(write_routing_log); assert 'write_routing_log_to_db' in src and 'warnings.warn' in src; print('ok')"
```
Expected: `ok`

3. **提交**：

```bash
git add framework/observability/routing_log.py
git commit -m "feat(observability): double-write routing log to DB + JSONL fallback"
```

---

### Task 2.3：DB 写入异常隔离边界校验

- [x] **任务 2.3 完成**：确保 DB 写入异常被 try/except 隔离，不传播到 `observe.py` 的 `_safe_write_log`（双重保险：`write_routing_log` 内层 + `_safe_write_log` 外层）

**Files:**
- 校验（已通过 Task 2.2 实现）：`framework/observability/routing_log.py`、`framework/observability/observe.py:32-41`

**Interfaces:**
- Produces：异常隔离契约（DB 异常路径：`write_routing_log_to_db` 抛出 → `write_routing_log` try/except 捕获并 warn → `_safe_write_log` 外层兜底）

**实施步骤:**

1. **校验 `routing_log.write_routing_log` 内层 try/except**：

```bash
python -c "import inspect; from framework.observability.routing_log import write_routing_log; src=inspect.getsource(write_routing_log); assert 'try:' in src and 'except Exception as exc' in src and 'warnings.warn' in src; print('inner ok')"
```
Expected: `inner ok`

2. **校验 `observe._safe_write_log` 外层 try/except 仍存在**（应为现状代码，未修改）：

```bash
python -c "import inspect; from framework.observability.observe import _safe_write_log; src=inspect.getsource(_safe_write_log); assert 'try:' in src and 'except Exception' in src and 'warnings.warn' in src; print('outer ok')"
```
Expected: `outer ok`

3. **无需提交**（本任务为校验任务，无文件变更；若前序任务已提交则跳过 commit）。

---

## 任务 3.x：observe.py entry 字段对齐（Design Doc §3.2）

### Task 3.1：补充 `relevance` 字段

- [x] **任务 3.1 完成**：在 `observe_routing` 的 entry 中补充 `relevance` 字段（从 `identify_question_type` 返回值获取）

**Files:**
- Modify: `framework/observability/observe.py:86-96`、`framework/observability/observe.py:97-101`

**Interfaces:**
- Consumes: `identify_question_type(question, context)` 返回 `(question_type, relevance)`（现状接口未变）
- Produces: `entry["relevance"]` 字段（供 Task 2.1 `write_routing_log_to_db` 落库到 `RoutingDecisionLog.relevance` 列）

**实施步骤:**

1. **修改 `framework/observability/observe.py`**：在 `observe_routing` 成功路径与异常路径都补充 `entry["relevance"]`。

成功路径（L86-96 区域，`question_type, relevance = identify_question_type(...)` 之后）：

```python
        question_type, relevance = identify_question_type(question, context)
        entry["relevance"] = relevance
        entry["candidate_agents"] = _router.get_agents_for_type(question_type)
        entry["hit_exclusive_rules"] = _matched_rules(question, context)
        final_type, routing_status = apply_exclusive_rules(question, question_type, context)
        entry["question_type"] = final_type
        entry["routing_status"] = routing_status
        entry["degradation"] = routing_status
        _attach_llm_routing_state(entry)
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        return question_type, relevance, final_type, routing_status
```

异常路径（L97-101 区域）：

```python
    except Exception as exc:
        entry["failure_reason"] = str(exc)
        _attach_llm_routing_state(entry)
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        raise
```

> 注：异常路径 `relevance` 字段缺失，`write_routing_log_to_db` 用 `entry.get("relevance")` 容错（落库为 NULL），不强制赋值。

2. **冒烟验证**：

```bash
python -c "import inspect; from framework.observability.observe import observe_routing; src=inspect.getsource(observe_routing); assert 'entry[\"relevance\"] = relevance' in src; print('ok')"
```
Expected: `ok`

3. **提交**：

```bash
git add framework/observability/observe.py
git commit -m "feat(observability): add relevance field to routing log entry"
```

---

### Task 3.2：补充 `five_dim_context` 字段（4 字段子集）

- [x] **任务 3.2 完成**：在 entry 中补充 `five_dim_context` 字段（仅 4 字段：scale/data_type/business_task/expected_output，parcel_id/parcel_code 不入此字段）

**Files:**
- Modify: `framework/observability/observe.py`（在 `_safe_write_log(entry)` 调用前赋值）

**Interfaces:**
- Consumes: `observe_routing(question, context=None, ...)` 的 `context` 参数（dict 或 None）
- Produces: `entry["five_dim_context"]`（dict，4 字段子集；供 `write_routing_log_to_db` 落库到 `RoutingDecisionLog.five_dim_context` 列）

**实施步骤:**

1. **修改 `framework/observability/observe.py`**：在 `observe_routing` 函数内、`_safe_write_log(entry)` 调用前，补充 `five_dim_context` 字段。

成功路径在 `_attach_llm_routing_state(entry)` 之后、`_safe_write_log(entry)` 之前插入：

```python
        _attach_llm_routing_state(entry)
        _FIVE_DIM_KEYS = ("scale", "data_type", "business_task", "expected_output")
        entry["five_dim_context"] = (
            {k: context.get(k) for k in _FIVE_DIM_KEYS} if context else {}
        )
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        return question_type, relevance, final_type, routing_status
```

异常路径在 `_attach_llm_routing_state(entry)` 之后、`_safe_write_log(entry)` 之前插入同样三行：

```python
    except Exception as exc:
        entry["failure_reason"] = str(exc)
        _attach_llm_routing_state(entry)
        _FIVE_DIM_KEYS = ("scale", "data_type", "business_task", "expected_output")
        entry["five_dim_context"] = (
            {k: context.get(k) for k in _FIVE_DIM_KEYS} if context else {}
        )
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        raise
```

2. **冒烟验证**：

```bash
python -c "import inspect; from framework.observability.observe import observe_routing; src=inspect.getsource(observe_routing); assert 'five_dim_context' in src and 'scale' in src and 'data_type' in src and 'business_task' in src and 'expected_output' in src and 'parcel_id' not in src; print('ok')"
```
Expected: `ok`

3. **提交**：

```bash
git add framework/observability/observe.py
git commit -m "feat(observability): add five_dim_context (4-field subset) to routing log entry"
```

---

### Task 3.3：补充 `logged_at` 字段

- [x] **任务 3.3 完成**：在 entry 中补充 `logged_at` 字段（UTC 时间戳，落库到 `RoutingDecisionLog.logged_at`）

**Files:**
- Modify: `framework/observability/observe.py`（顶部 import + entry 赋值）

**Interfaces:**
- Produces: `entry["logged_at"]`（`datetime` 对象，带时区；供 `write_routing_log_to_db` 落库）

**实施步骤:**

1. **修改 `framework/observability/observe.py` 顶部 import**：在 `import time` 旁补充 `datetime` 与 `timezone`：

```python
import time
import uuid
from datetime import datetime, timezone
```

2. **修改 `observe_routing` entry 赋值**：在 `entry` dict 初始化处补充 `logged_at` 字段（一次赋值，成功与异常路径共用）。在 `entry: Dict[str, Any] = {...}` 字典内新增一行：

```python
    entry: Dict[str, Any] = {
        "trace_id": tid,
        "question": question,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "logged_at": datetime.now(timezone.utc),
        "data_version": data_version,
        "agent_version": agent_version,
        "params": params or {},
        "result_version": ROUTING_RESULT_VERSION,
        "failure_reason": None,
    }
```

> 注：`timestamp` 字段保留不动（已有看板消费链依赖），`logged_at` 是新增的 DB 落库字段。

3. **冒烟验证**：

```bash
python -c "import inspect; from framework.observability.observe import observe_routing; src=inspect.getsource(observe_routing); assert 'logged_at' in src and 'datetime.now(timezone.utc)' in src; print('ok')"
```
Expected: `ok`

4. **提交**：

```bash
git add framework/observability/observe.py
git commit -m "feat(observability): add logged_at (UTC) to routing log entry"
```

---

### Task 3.4：重命名 `duration_ms` → `total_duration_ms`（完全重命名，不保留别名）

- [x] **任务 3.4 完成**：将 entry 的 `duration_ms` 完全重命名为 `total_duration_ms`（遵循 Design Doc §3.2.1 决策；不保留 `duration_ms` 别名）

> **冲突说明**：OpenSpec tasks.md 3.4 措辞为"保留 `duration_ms` 别名向后兼容"，但 Design Doc §3.2.1 明确"完全重命名，不保留别名"。本计划遵循 Design Doc（用户授权 `按 Design Doc §3 的小节拆分可执行任务`）。`entry["duration_ms"]` 仅在 `observe.py` 2 处赋值 + `tests/test_routing_observability.py:69` 1 处断言使用；`ModelExecutionLog.duration_ms` 与 `routing._last_llm_duration_ms` 是独立字段，不受影响。

**Files:**
- Modify: `framework/observability/observe.py`（L94、L100 两处赋值）
- 注：`tests/test_routing_observability.py:69` 断言更新延后到 Task 6.4（"运行现有测试套件确保无回归"步骤前置完成）

**Interfaces:**
- Produces: `entry["total_duration_ms"]` 字段（替代 `entry["duration_ms"]`；供 `write_routing_log_to_db` 落库到 `RoutingDecisionLog.total_duration_ms` 列）

**实施步骤:**

1. **修改 `framework/observability/observe.py` 成功路径 L94**：将 `entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)` 改为：

```python
        entry["total_duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        return question_type, relevance, final_type, routing_status
```

2. **修改 `framework/observability/observe.py` 异常路径 L100**：将异常路径的 `entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)` 改为：

```python
    except Exception as exc:
        entry["failure_reason"] = str(exc)
        _attach_llm_routing_state(entry)
        _FIVE_DIM_KEYS = ("scale", "data_type", "business_task", "expected_output")
        entry["five_dim_context"] = (
            {k: context.get(k) for k in _FIVE_DIM_KEYS} if context else {}
        )
        entry["total_duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        raise
```

3. **冒烟验证**：

```bash
python -c "import inspect; from framework.observability.observe import observe_routing; src=inspect.getsource(observe_routing); assert 'total_duration_ms' in src and 'duration_ms' not in src.replace('total_duration_ms',''); print('ok')"
```
Expected: `ok`

> 注：本步骤后 `tests/test_routing_observability.py:69` 断言会失败（`"duration_ms"` 不再是 entry key），由 Task 6.4 在跑全套测试前先更新该断言修复。

4. **提交**：

```bash
git add framework/observability/observe.py
git commit -m "refactor(observability): rename entry duration_ms to total_duration_ms (no alias)"
```

---

## 任务 4.x：排他规则动态加载（Design Doc §3.3）

### Task 4.1：新增 `from_database()` 函数

- [x] **任务 4.1 完成**：在 `framework/agents/exclusive_rules.py` 新增 `from_database()` 函数，从 `exclusive_rule_config` 表加载 `enabled=True` 的规则到 `ExclusiveRule` 元组

**Files:**
- Modify: `framework/agents/exclusive_rules.py`（在 `apply_exclusive_rules` 之前新增）

**Interfaces:**
- Consumes: `framework.models.db`、`framework.models.ExclusiveRuleConfig`（任务 1.x 已就绪）、`ExclusiveRule` dataclass（同文件 L23-35）
- Produces: `from_database() -> Tuple[ExclusiveRule, ...]`（供 Task 4.3 `_get_active_rules()` 调用；DB 异常返回空 tuple）

**实施步骤:**

1. **修改 `framework/agents/exclusive_rules.py` 顶部 import**：补充 `Optional`、`Tuple` 已存在；在 `from .capabilities import ...` 之后新增模块级缓存变量。在 `EXCLUSIVE_RULES` 元组定义之后、`_condition_matches` 之前新增：

```python
_db_rules_cache: Optional[Tuple["ExclusiveRule", ...]] = None


def from_database() -> Tuple[ExclusiveRule, ...]:
    """从 exclusive_rule_config 表加载 enabled=True 的规则。

    规则结构转换：DB JSON 字段 → ExclusiveRule dataclass
    - rule_pair (JSON list) → frozenset(rule_pair)
    - dimension_conditions (JSON dict) → dict
    - condition (str or None) → Optional[str]

    DB 异常时返回空 tuple（由 _get_active_rules 回退硬编码）。
    """
    from framework.models import db, ExclusiveRuleConfig
    try:
        rows = db.session.query(ExclusiveRuleConfig).filter_by(enabled=True).all()
        return tuple(
            ExclusiveRule(
                pair=frozenset(r.rule_pair),
                discriminator=r.discriminator,
                condition=r.condition,
                target=r.target,
                dimension_conditions=r.dimension_conditions or {},
            )
            for r in rows
        )
    except Exception:
        return tuple()
```

2. **冒烟验证**：

```bash
python -c "from framework.agents.exclusive_rules import from_database, _db_rules_cache; print('ok', _db_rules_cache)"
```
Expected: `ok None`

3. **提交**：

```bash
git add framework/agents/exclusive_rules.py
git commit -m "feat(exclusive_rules): add from_database() to load rules from exclusive_rule_config table"
```

---

### Task 4.2：模块级缓存 `_db_rules_cache`

- [x] **任务 4.2 完成**：新增模块级缓存 `_db_rules_cache`，首次加载后缓存，避免每次路由判定查询 DB

**Files:**
- 校验（Task 4.1 已声明 `_db_rules_cache`）：`framework/agents/exclusive_rules.py`

**Interfaces:**
- Produces: 模块级变量 `_db_rules_cache: Optional[Tuple[ExclusiveRule, ...]] = None`（供 Task 4.3 `_get_active_rules()` 与 Task 4.3+ `refresh_rules_cache()` 操作）

**实施步骤:**

1. **校验缓存变量已声明**（Task 4.1 已在 `from_database` 之前新增 `_db_rules_cache = None`）：

```bash
python -c "from framework.agents.exclusive_rules import _db_rules_cache; assert _db_rules_cache is None; print('ok')"
```
Expected: `ok`

2. **无需提交**（无新文件变更；缓存变量声明已在 Task 4.1 的 commit 中）。

---

### Task 4.3：新增 `_get_active_rules()` 统一入口

- [x] **任务 4.3 完成**：新增 `_get_active_rules()` 统一入口函数，优先返回 DB 缓存规则，DB 为空或不可用时回退硬编码 `EXCLUSIVE_RULES`

**Files:**
- Modify: `framework/agents/exclusive_rules.py`（在 `from_database` 之后新增）

**Interfaces:**
- Consumes: `from_database()`（Task 4.1）、`_db_rules_cache`（Task 4.2）、`EXCLUSIVE_RULES`（同文件硬编码）
- Produces: `_get_active_rules() -> Tuple[ExclusiveRule, ...]`（供 Task 4.4 `apply_exclusive_rules` 与 Task 4.5 `observe._matched_rules` 调用）

**实施步骤:**

1. **修改 `framework/agents/exclusive_rules.py`**：在 `from_database` 之后、`_condition_matches` 之前新增 `_get_active_rules`：

```python
def _get_active_rules() -> Tuple[ExclusiveRule, ...]:
    """优先返回 DB 缓存规则，DB 为空或不可用时回退硬编码 EXCLUSIVE_RULES。"""
    global _db_rules_cache
    if _db_rules_cache is None:
        _db_rules_cache = from_database()
    if _db_rules_cache:
        return _db_rules_cache
    # DB 为空或不可用：回退硬编码
    return EXCLUSIVE_RULES


def refresh_rules_cache() -> None:
    """手动刷新 DB 规则缓存。供运维/测试调用，运行时不自动刷新。

    场景：运维通过 DB 修改 exclusive_rule_config 表后，调用此函数使新规则生效。
    """
    global _db_rules_cache
    _db_rules_cache = None  # 清空缓存，下次 _get_active_rules() 重新加载
```

> 注：Task 4.3 顺带新增 `refresh_rules_cache()`（Design Doc §3.3.3），同属统一入口模块的对外 API，避免拆分过细。

2. **冒烟验证**：

```bash
python -c "from framework.agents.exclusive_rules import _get_active_rules, refresh_rules_cache; rs=_get_active_rules(); assert len(rs) > 0; print('rules count:', len(rs))"
```
Expected: `rules count: 8`（无 DB 时回退硬编码 8 条规则）

3. **提交**：

```bash
git add framework/agents/exclusive_rules.py
git commit -m "feat(exclusive_rules): add _get_active_rules + refresh_rules_cache with DB fallback"
```

---

### Task 4.4：修改 `apply_exclusive_rules` 使用 `_get_active_rules()`

- [x] **任务 4.4 完成**：修改 `apply_exclusive_rules` 中 `for rule in EXCLUSIVE_RULES` 为 `for rule in _get_active_rules()`，匹配算法不变

**Files:**
- Modify: `framework/agents/exclusive_rules.py:169-173`（`matched_targets` 集合推导式）

**Interfaces:**
- Consumes: `_get_active_rules()`（Task 4.3）
- Produces: 动态规则源的 `apply_exclusive_rules`（接口签名与返回值不变）

**实施步骤:**

1. **修改 `framework/agents/exclusive_rules.py`**：将 `apply_exclusive_rules` 函数内的规则遍历源从 `EXCLUSIVE_RULES` 改为 `_get_active_rules()`：

```python
    matched_targets = {
        rule.target
        for rule in _get_active_rules()
        if _rule_matches(rule, question, context)
    }
```

2. **冒烟验证**：

```bash
python -c "import inspect; from framework.agents.exclusive_rules import apply_exclusive_rules; src=inspect.getsource(apply_exclusive_rules); assert '_get_active_rules()' in src and 'EXCLUSIVE_RULES' not in src.replace('_get_active_rules',''); print('ok')"
```
Expected: `ok`

3. **提交**：

```bash
git add framework/agents/exclusive_rules.py
git commit -m "refactor(exclusive_rules): apply_exclusive_rules uses _get_active_rules() for dynamic rule source"
```

---

### Task 4.5：修改 `observe._matched_rules` 使用 `_get_active_rules()`

- [x] **任务 4.5 完成**：修改 `observe._matched_rules` 中 `for r in EXCLUSIVE_RULES` 为 `for r in _get_active_rules()`，与 `apply_exclusive_rules` 保持规则源一致

**Files:**
- Modify: `framework/observability/observe.py:27-29`

**Interfaces:**
- Consumes: `_get_active_rules()`（Task 4.3，从 `framework.agents.exclusive_rules` 导入）
- Produces: 动态规则源的 `_matched_rules`（接口签名不变，仍返回 `list[str]`）

**实施步骤:**

1. **修改 `framework/observability/observe.py` 顶部 import**：将 `EXCLUSIVE_RULES` 替换为 `_get_active_rules`：

```python
from framework.agents.exclusive_rules import (
    _get_active_rules,
    _rule_matches,
    apply_exclusive_rules,
)
```

> 注：删除 `EXCLUSIVE_RULES` 导入（不再使用）；`_rule_matches` 与 `apply_exclusive_rules` 仍保留。

2. **修改 `framework/observability/observe.py` 的 `_matched_rules`**：将 `EXCLUSIVE_RULES` 替换为 `_get_active_rules()`：

```python
def _matched_rules(question: str, context: Optional[dict]) -> list[str]:
    """返回命中的排他规则 target（只读，不改变路由行为）。"""
    return [r.target for r in _get_active_rules() if _rule_matches(r, question, context)]
```

3. **冒烟验证**：

```bash
python -c "import inspect; from framework.observability.observe import _matched_rules; src=inspect.getsource(_matched_rules); assert '_get_active_rules()' in src and 'EXCLUSIVE_RULES' not in src; print('ok')"
```
Expected: `ok`

4. **提交**：

```bash
git add framework/observability/observe.py
git commit -m "refactor(observe): _matched_rules uses _get_active_rules() for consistency with apply_exclusive_rules"
```

---

## 任务 5.x：混淆矩阵评估结果落库（Design Doc §3.3）

### Task 5.0：修复 `run_routing_regression.py` 的 `MODEL1_STEMS` 导入错误

- [x] **任务 5.0 完成**：修复 `scripts/run_routing_regression.py` 的 `MODEL1_STEMS` 导入错误，使后续 Task 5.2/5.3/6.3 的冒烟测试可字面执行

**背景**：`scripts/run_routing_regression.py:22-23` 导入 `MODEL1_STEMS` from `tests/test_question_type_keywords.py`，但 `MODEL1_STEMS` 已在模型编号重排 commit 中被删除（test 文件现存 `MODEL2_STEMS`/`MODEL3_STEMS`/`MODEL4_STEMS`/`MODEL5_STEMS`）。导致任何 `from run_routing_regression import ...` 都会 `ImportError: cannot import name 'MODEL1_STEMS'`。

**Files:**
- Modify: `scripts/run_routing_regression.py`（import 行 + SETS 数组）

**实施步骤**:

1. **调查映射**：读取 `tests/test_question_type_keywords.py` 确认各 `MODEL*_STEMS` 内容对应的模型语义（stability/grade/obstacle/acidification/organic_matter），与 `scripts/run_routing_regression.py` 的 SETS 数组对齐

2. **修复 import**：将 `MODEL1_STEMS` 替换为正确的 `MODEL*_STEMS` 变量

3. **修复 SETS**：更新 SETS 数组中的变量引用和模型编号，使其与新编号一致

4. **冒烟验证**：

```bash
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'scripts'); sys.path.insert(0, 'tests'); from run_routing_regression import SETS, _predict_model; print('ok', len(SETS))"
```
Expected: `ok 4`（SETS 有 4 项）

5. **提交**：

```bash
git add scripts/run_routing_regression.py
git commit -m "fix(regression): update MODEL1_STEMS import for new model numbering"
```

---

### Task 5.1：新增 `write_metrics_to_db(matrix, evaluation_mode)` 函数

- [x] **任务 5.1 完成**：在 `scripts/run_routing_regression.py` 新增 `write_metrics_to_db(matrix, evaluation_mode)` 函数，批量写入 `model_evaluation_metrics` 表

**Files:**
- Modify: `scripts/run_routing_regression.py`（在 `main` 之前新增；顶部 `import warnings`）

**Interfaces:**
- Consumes: `framework.models.db`、`framework.models.ModelEvaluationMetrics`（任务 1.x 已就绪）、`PAIR_POSITIVE` 字典（同文件 L40-43）
- Produces: `write_metrics_to_db(matrix: dict, evaluation_mode: str) -> None`（DB 写入失败时 `db.session.rollback()` + `warnings.warn`，不抛出）

**实施步骤:**

1. **修改 `scripts/run_routing_regression.py` 顶部 import**：补充 `warnings`：

```python
import argparse
import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path
```

2. **修改 `scripts/run_routing_regression.py`**：在 `_predict_model` 之后、`main` 之前新增 `write_metrics_to_db`：

```python
def write_metrics_to_db(matrix: dict, evaluation_mode: str) -> None:
    """批量写入 model_evaluation_metrics 表。

    matrix 格式：{pair_label: {tp, fp, fn, tn, total, accuracy, confusion_rate}}
    每对插入一条记录，positive_label 来自 PAIR_POSITIVE 映射。

    DB 写入失败时 rollback 并告警，不抛出（保留 JSON 文件输出）。
    """
    from framework.models import db, ModelEvaluationMetrics
    try:
        for pair_label, m in matrix.items():
            record = ModelEvaluationMetrics(
                model_pair=pair_label,
                positive_label=PAIR_POSITIVE.get(pair_label, ""),
                tp=m["tp"], fp=m["fp"], fn=m["fn"], tn=m["tn"],
                total=m["total"], accuracy=m["accuracy"],
                confusion_rate=m["confusion_rate"],
                evaluation_mode=evaluation_mode,
                sample_count=m["total"],
            )
            db.session.add(record)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        warnings.warn(f"[regression] model_evaluation_metrics DB 写入失败: {exc}")
```

3. **冒烟验证**：

```bash
python -c "import inspect; import sys; sys.path.insert(0, 'scripts'); from run_routing_regression import write_metrics_to_db; src=inspect.getsource(write_metrics_to_db); assert 'ModelEvaluationMetrics' in src and 'rollback' in src and 'warnings.warn' in src; print('ok')"
```
Expected: `ok`

4. **提交**：

```bash
git add scripts/run_routing_regression.py
git commit -m "feat(regression): add write_metrics_to_db for model_evaluation_metrics persistence"
```

---

### Task 5.2：`main()` 调用 `write_metrics_to_db` + DB 失败保留 JSON 输出

- [ ] **任务 5.2 完成**：在 `main()` 写入 JSON 文件后调用 `write_metrics_to_db(matrix, evaluation_mode="keyword")`，DB 写入失败时保留 JSON 文件输出并告警

**Files:**
- Modify: `scripts/run_routing_regression.py:80-85`（`main` 函数末尾）

**Interfaces:**
- Consumes: `write_metrics_to_db(matrix, evaluation_mode)`（Task 5.1）、`matrix` 字典（`main` 局部变量）
- Produces: 落库版 `main`（退出码逻辑不变）

**实施步骤:**

1. **修改 `scripts/run_routing_regression.py` 的 `main`**：在 `print(f"混淆矩阵已写入 {args.output}")` 之前、`json.dump` 之后插入 DB 落库调用：

```python
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    write_metrics_to_db(matrix, evaluation_mode="keyword")
    print(f"混淆矩阵已写入 {args.output}")
    print("目标达成" if not failed else "未达成：存在混淆率超目标的对")
    return 1 if failed else 0
```

> 注：`evaluation_mode` 固定为 `"keyword"`（回归脚本仅用关键词路由，不涉及 LLM 路由）。

2. **冒烟验证**：

```bash
python -c "import inspect; import sys; sys.path.insert(0, 'scripts'); from run_routing_regression import main; src=inspect.getsource(main); assert 'write_metrics_to_db(matrix, evaluation_mode=\"keyword\")' in src; print('ok')"
```
Expected: `ok`

3. **提交**：

```bash
git add scripts/run_routing_regression.py
git commit -m "feat(regression): main() calls write_metrics_to_db after JSON dump"
```

---

### Task 5.3：DB 写入失败不改变退出码校验

- [ ] **任务 5.3 完成**：确保 DB 写入失败不改变脚本退出码（`write_metrics_to_db` 内部 try/except 已隔离，`main` 退出码逻辑不受影响）

**Files:**
- 校验（Task 5.1 已实现）：`scripts/run_routing_regression.py`

**Interfaces:**
- Produces：退出码契约（DB 异常时退出码仍由 `failed`（混淆率是否超目标）决定，不被 DB 异常污染）

**实施步骤:**

1. **校验 `write_metrics_to_db` 异常隔离**：

```bash
python -c "import inspect; import sys; sys.path.insert(0, 'scripts'); from run_routing_regression import write_metrics_to_db; src=inspect.getsource(write_metrics_to_db); assert 'try:' in src and 'except Exception as exc' in src and 'rollback' in src and 'warnings.warn' in src; print('isolated ok')"
```
Expected: `isolated ok`

2. **校验 `main` 退出码逻辑未被 DB 调用包裹**（`return 1 if failed else 0` 不在 `write_metrics_to_db` 的 try/except 内）：

```bash
python -c "import inspect; import sys; sys.path.insert(0, 'scripts'); from run_routing_regression import main; src=inspect.getsource(main); assert 'return 1 if failed else 0' in src; print('exit code ok')"
```
Expected: `exit code ok`

3. **无需提交**（本任务为校验任务，无文件变更）。

---

## 任务 6.x：测试（Design Doc §3.5，PostgreSQL 测试库）

### Task 6.1：新增 `tests/test_routing_log_db.py` + `conftest.py` PG 跳过机制

- [ ] **任务 6.1 完成**：新增 `tests/test_routing_log_db.py`（3 个测试用例：双写正常路径、DB 失败回退 JSONL、entry 字段对齐）+ `tests/conftest.py` 增加 `PG_AVAILABLE` 探测与 `pg_available` fixture

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/test_routing_log_db.py`

**Interfaces:**
- Consumes: `observe_routing`（任务 3.x 已对齐字段）、`write_routing_log_to_db`（Task 2.1）、`set_log_path` / `set_log_enabled`（`routing_log.py` 现状）、`framework.models.db` / `RoutingDecisionLog`（任务 1.x）
- Produces: `PG_AVAILABLE` 模块级常量 + `pg_available` fixture（供 Task 6.2 / 6.3 复用）

**实施步骤:**

1. **修改 `tests/conftest.py`**：在文件末尾追加 PG 探测逻辑：

```python
"""Pytest 全局配置：统一注入项目根目录和 src/ 到 sys.path。

避免不同测试文件合并跑时，因 sys.path 顺序差异导致 framework.agents.specialized
在加载阶段触发 ai_culti_demo 导入失败，进而把 STABILITY_MODEL_AVAILABLE /
FARMland_DIAGNOSIS_AVAILABLE 等模块级常量冻结为 False（model_unavailable）。
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


# PostgreSQL 测试库可用性探测：供 routing_log_db / exclusive_rules_db / regression_metrics_db 跳过
def _probe_pg_available() -> bool:
    try:
        from framework.api.app import create_app
        from framework.models.user import db
        app = create_app("default")
        with app.app_context():
            db.session.execute(__import__("sqlalchemy").text("SELECT 1"))
            return True
    except Exception:
        return False


PG_AVAILABLE = _probe_pg_available()
```

2. **新建 `tests/test_routing_log_db.py`**：

```python
"""路由日志 DB 双写测试（PostgreSQL 测试库）。

PG 不可用时整个文件跳过（conftest.PG_AVAILABLE 控制）。
"""
import sys
import os
import json
import tempfile
import warnings

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import PG_AVAILABLE

pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL 测试库不可用")

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models import RoutingDecisionLog  # noqa: E402
from framework.observability.routing_log import set_log_path  # noqa: E402
from framework.observability.observe import observe_routing  # noqa: E402


@pytest.fixture
def pg_app():
    app = create_app("default")
    with app.app_context():
        db.session.query(RoutingDecisionLog).delete()
        db.session.commit()
        yield app
        db.session.query(RoutingDecisionLog).delete()
        db.session.commit()


@pytest.fixture
def routing_log_path():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "routing_calls_test.jsonl")
        set_log_path(path)
        yield path
        set_log_path("")  # 清除 override


class TestRoutingLogDb:
    def test_double_write_normal(self, pg_app, routing_log_path, monkeypatch):
        """执行 observe_routing，验证 JSONL 和 routing_decision_log 表均有记录，trace_id 一致。"""
        from framework.agents import routing as _routing
        monkeypatch.setattr(_routing, "EMBEDDING_AVAILABLE", False)
        trace_id = "db-test-001"
        observe_routing(
            "我的田耕地质量等级是多少", {"scale": "地块"},
            trace_id=trace_id,
            data_version="v2024.1", agent_version="model-2@1.0",
        )
        # JSONL 有记录
        with open(routing_log_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["trace_id"] == trace_id
        # DB 有记录
        rows = db.session.query(RoutingDecisionLog).filter_by(trace_id=trace_id).all()
        assert len(rows) == 1
        assert rows[0].question_type == 2
        assert rows[0].routing_status == "normal"

    def test_db_failure_fallback_jsonl(self, pg_app, routing_log_path, monkeypatch):
        """mock db.session.commit 抛异常，验证 JSONL 仍写入，warnings.warn 触发。"""
        from framework.agents import routing as _routing
        monkeypatch.setattr(_routing, "EMBEDDING_AVAILABLE", False)

        def _boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(db.session, "commit", _boom)

        trace_id = "db-fail-002"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            observe_routing(
                "我的田耕地质量等级是多少", {"scale": "地块"},
                trace_id=trace_id,
            )
            assert any("DB 写入失败" in str(w.message) for w in caught)
        # JSONL 仍写入
        with open(routing_log_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["trace_id"] == trace_id
        # DB 无记录（commit 失败）
        rows = db.session.query(RoutingDecisionLog).filter_by(trace_id=trace_id).all()
        assert len(rows) == 0

    def test_entry_field_alignment(self, pg_app, routing_log_path, monkeypatch):
        """验证 entry 包含 total_duration_ms、relevance、five_dim_context、logged_at 四个新字段。"""
        from framework.agents import routing as _routing
        monkeypatch.setattr(_routing, "EMBEDDING_AVAILABLE", False)
        trace_id = "db-align-003"
        observe_routing(
            "我的田耕地质量等级是多少",
            {"scale": "地块", "data_type": "评价结果",
             "business_task": "质量等级评价", "expected_output": "评价结果"},
            trace_id=trace_id,
        )
        with open(routing_log_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert "total_duration_ms" in entry
        assert "duration_ms" not in entry
        assert "relevance" in entry
        assert "five_dim_context" in entry
        assert set(entry["five_dim_context"].keys()) == {
            "scale", "data_type", "business_task", "expected_output"
        }
        assert "logged_at" in entry
```

3. **运行测试**（PG 可用时）：

```bash
pytest tests/test_routing_log_db.py -v
```
Expected: `3 passed`（PG 不可用时 `3 skipped`）

4. **提交**：

```bash
git add tests/conftest.py tests/test_routing_log_db.py
git commit -m "test(observability): add test_routing_log_db with PG skip mechanism"
```

---

### Task 6.2：新增 `tests/test_exclusive_rules_db.py`

- [ ] **任务 6.2 完成**：新增 `tests/test_exclusive_rules_db.py`（5 个测试用例：from_database 加载、DB 不可用回退、DB 为空回退、DB 规则与硬编码判定一致、refresh_rules_cache 生效）

**Files:**
- Create: `tests/test_exclusive_rules_db.py`

**Interfaces:**
- Consumes: `from_database` / `_get_active_rules` / `refresh_rules_cache` / `EXCLUSIVE_RULES` / `apply_exclusive_rules`（任务 4.x 产出）、`framework.models.ExclusiveRuleConfig`（任务 1.x）、`PG_AVAILABLE`（Task 6.1）

**实施步骤:**

1. **新建 `tests/test_exclusive_rules_db.py`**：

```python
"""排他规则动态加载测试（PostgreSQL 测试库）。

PG 不可用时整个文件跳过。
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import PG_AVAILABLE

pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL 测试库不可用")

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models import ExclusiveRuleConfig  # noqa: E402
from framework.agents.exclusive_rules import (  # noqa: E402
    from_database, _get_active_rules, refresh_rules_cache,
    EXCLUSIVE_RULES, apply_exclusive_rules,
)


@pytest.fixture
def pg_app():
    app = create_app("default")
    with app.app_context():
        db.session.query(ExclusiveRuleConfig).delete()
        db.session.commit()
        # 重置缓存，确保每个测试从干净状态开始
        refresh_rules_cache()
        yield app
        db.session.query(ExclusiveRuleConfig).delete()
        db.session.commit()
        refresh_rules_cache()


def _insert_rule(rule_name, pair, discriminator, target, condition=None,
                 dimension_conditions=None):
    row = ExclusiveRuleConfig(
        rule_name=rule_name,
        rule_pair=list(pair),
        discriminator=discriminator,
        condition=condition,
        target=target,
        dimension_conditions=dimension_conditions or {},
        enabled=True,
    )
    db.session.add(row)
    db.session.commit()


class TestExclusiveRulesDb:
    def test_from_database_loads(self, pg_app):
        """插入测试规则，验证 from_database() 返回正确规则。"""
        _insert_rule("test-rule-1", frozenset({"model-2", "model-3"}),
                     "业务任务", "model-3", condition="现状评价")
        refresh_rules_cache()
        rules = from_database()
        assert len(rules) == 1
        r = rules[0]
        assert r.target == "model-3"
        assert "model-2" in r.pair and "model-3" in r.pair
        assert r.condition == "现状评价"

    def test_db_unavailable_fallback(self, pg_app, monkeypatch):
        """mock db.session 抛异常，验证 _get_active_rules() 回退 EXCLUSIVE_RULES。"""
        def _boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(db.session, "query", _boom)
        refresh_rules_cache()  # 清空缓存，强制下次重新加载
        rules = _get_active_rules()
        assert rules == EXCLUSIVE_RULES
        assert len(rules) == len(EXCLUSIVE_RULES)

    def test_db_empty_fallback(self, pg_app):
        """表为空时回退硬编码 EXCLUSIVE_RULES。"""
        # pg_app fixture 已 delete all
        refresh_rules_cache()
        rules = _get_active_rules()
        assert rules == EXCLUSIVE_RULES

    def test_db_rules_match_hardcoded_judgment(self, pg_app):
        """构造 DB 规则等价于硬编码规则，验证 apply_exclusive_rules 判定结果一致。"""
        # 把硬编码 8 条规则全部插入 DB
        for idx, r in enumerate(EXCLUSIVE_RULES):
            _insert_rule(
                f"hardcoded-{idx}",
                list(r.pair),
                r.discriminator,
                r.target,
                condition=r.condition,
                dimension_conditions=r.dimension_conditions,
            )
        refresh_rules_cache()
        # 对一组正反例验证判定一致
        test_cases = [
            ("我的田耕地质量等级是多少", {"scale": "地块"}, 2),  # → model-2
            ("我的田耕地障碍诊断如何", {"scale": "地块",
                                      "business_task": "障碍诊断",
                                      "expected_output": "诊断报告"}, 3),  # → model-3
        ]
        for question, context, expected_qtype in test_cases:
            final_type, status = apply_exclusive_rules(question, expected_qtype, context)
            assert status == "normal"
            # 与硬编码路径对比：临时清缓存切回硬编码
            refresh_rules_cache()
            # DB 规则仍在，先记录 DB 路径结果
            db_final_type = final_type
            # 删除 DB 规则，验证硬编码路径给出相同结果
            db.session.query(ExclusiveRuleConfig).delete()
            db.session.commit()
            refresh_rules_cache()
            hardcoded_final_type, _ = apply_exclusive_rules(question, expected_qtype, context)
            assert db_final_type == hardcoded_final_type
            # 重新插入 DB 规则，恢复 DB 路径状态
            for idx2, r in enumerate(EXCLUSIVE_RULES):
                _insert_rule(
                    f"hardcoded-{idx2}",
                    list(r.pair),
                    r.discriminator,
                    r.target,
                    condition=r.condition,
                    dimension_conditions=r.dimension_conditions,
                )
            refresh_rules_cache()

    def test_refresh_rules_cache(self, pg_app):
        """调用 refresh_rules_cache() 后，新插入的规则立即可见。"""
        # 初始：DB 为空，回退硬编码
        refresh_rules_cache()
        assert _get_active_rules() == EXCLUSIVE_RULES
        # 插入一条新规则
        _insert_rule("refresh-test", frozenset({"model-2", "model-3"}),
                     "业务任务", "model-3", condition="现状评价")
        # 缓存未刷新：仍返回硬编码（缓存为空时刷新后回退硬编码，但缓存已建立为 EXCLUSIVE_RULES 的 fallback 路径）
        # 调用 refresh_rules_cache() 强制重新加载
        refresh_rules_cache()
        rules = _get_active_rules()
        assert len(rules) == 1
        assert rules[0].target == "model-3"
```

2. **运行测试**（PG 可用时）：

```bash
pytest tests/test_exclusive_rules_db.py -v
```
Expected: `5 passed`（PG 不可用时 `5 skipped`）

3. **提交**：

```bash
git add tests/test_exclusive_rules_db.py
git commit -m "test(exclusive_rules): add test_exclusive_rules_db with PG skip"
```

---

### Task 6.3：新增 `tests/test_regression_metrics_db.py`

- [ ] **任务 6.3 完成**：新增 `tests/test_regression_metrics_db.py`（2 个测试用例：评估结果落库、DB 失败保留 JSON 输出）

**Files:**
- Create: `tests/test_regression_metrics_db.py`

**Interfaces:**
- Consumes: `run_routing_regression.main` / `write_metrics_to_db`（任务 5.x 产出）、`framework.models.ModelEvaluationMetrics`（任务 1.x）、`PG_AVAILABLE`（Task 6.1）

**实施步骤:**

1. **新建 `tests/test_regression_metrics_db.py`**：

```python
"""混淆矩阵评估结果落库测试（PostgreSQL 测试库）。

PG 不可用时整个文件跳过。
"""
import sys
import os
import json
import tempfile
import warnings

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
from tests.conftest import PG_AVAILABLE

pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL 测试库不可用")

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models import ModelEvaluationMetrics  # noqa: E402
from run_routing_regression import main  # noqa: E402


@pytest.fixture
def pg_app():
    app = create_app("default")
    with app.app_context():
        db.session.query(ModelEvaluationMetrics).delete()
        db.session.commit()
        yield app
        db.session.query(ModelEvaluationMetrics).delete()
        db.session.commit()


class TestRegressionMetricsDb:
    def test_metrics_written_to_db(self, pg_app, tmp_path):
        """运行 main()，验证 model_evaluation_metrics 表有 2 条记录（model-1-vs-model-5 / model-2-vs-model-3）。"""
        output = tmp_path / "confusion_matrix.json"
        exit_code = main(["--output", str(output)])
        assert exit_code in (0, 1)  # 0=达成, 1=未达成（DB 写入不影响退出码）
        # JSON 文件输出
        assert output.exists()
        matrix = json.loads(output.read_text(encoding="utf-8"))
        assert set(matrix.keys()) == {"model-1-vs-model-5", "model-2-vs-model-3"}
        # DB 落库 2 条记录
        rows = db.session.query(ModelEvaluationMetrics).all()
        assert len(rows) == 2
        pairs = {r.model_pair for r in rows}
        assert pairs == {"model-1-vs-model-5", "model-2-vs-model-3"}
        for r in rows:
            assert r.evaluation_mode == "keyword"
            assert r.sample_count == r.total

    def test_db_failure_keeps_json(self, pg_app, monkeypatch, tmp_path):
        """mock db.session.commit 失败，验证 JSON 文件仍输出，退出码不变。"""
        original_commit = db.session.commit

        def _flaky_commit(*a, **k):
            # 仅 model_evaluation_metrics 写入路径抛异常（write_metrics_to_db 调用 commit）
            raise RuntimeError("db down")
        monkeypatch.setattr(db.session, "commit", _flaky_commit)

        output = tmp_path / "confusion_matrix.json"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            exit_code = main(["--output", str(output)])
            assert any("model_evaluation_metrics DB 写入失败" in str(w.message) for w in caught)
        # JSON 文件仍输出
        assert output.exists()
        # 退出码不为 DB 异常所污染（0 或 1，取决于混淆率）
        assert exit_code in (0, 1)
        # DB 无记录
        rows = db.session.query(ModelEvaluationMetrics).all()
        assert len(rows) == 0
```

2. **运行测试**（PG 可用时）：

```bash
pytest tests/test_regression_metrics_db.py -v
```
Expected: `2 passed`（PG 不可用时 `2 skipped`）

3. **提交**：

```bash
git add tests/test_regression_metrics_db.py
git commit -m "test(regression): add test_regression_metrics_db with PG skip"
```

---

### Task 6.4：更新现有 `test_routing_observability.py:69` + 运行现有测试套件确保无回归

- [ ] **任务 6.4 完成**：更新 `tests/test_routing_observability.py:69` 的 `duration_ms` 断言为 `total_duration_ms`，并运行现有测试套件确保无回归

**Files:**
- Modify: `tests/test_routing_observability.py:69`

**Interfaces:**
- Consumes: Task 3.4 的 `duration_ms`→`total_duration_ms` 重命名
- Produces: 与重命名后 entry 字段对齐的现有测试套件（无回归）

**实施步骤:**

1. **修改 `tests/test_routing_observability.py:69`**：将断言集合中的 `"duration_ms"` 改为 `"total_duration_ms"`：

```python
                assert {"trace_id", "candidate_agents", "hit_exclusive_rules",
                        "total_duration_ms", "result_version", "failure_reason"}.issubset(entry.keys())
```

2. **运行 `test_routing_observability.py` 验证修复**：

```bash
pytest tests/test_routing_observability.py -v
```
Expected: `3 passed`（`TestRoutingLog` 3 个 + `TestObserve` 2 个 = 应全部通过；具体数取决于现状）

3. **运行现有测试套件确保无回归**（不含 PG 测试文件，PG 不可用时自动 skip）：

```bash
pytest tests/ -v --tb=short
```
Expected: 所有现有测试通过；新增的 PG 测试文件在 PG 不可用时 `skipped`，PG 可用时 `passed`

4. **提交**：

```bash
git add tests/test_routing_observability.py
git commit -m "test(observability): update duration_ms assertion to total_duration_ms after rename"
```

---

## 任务 7.x：端到端验证（Design Doc §4）

### Task 7.1：运行 `init_db.py` 创建三张新表

- [ ] **任务 7.1 完成**：运行 `python init_db.py` 创建 `routing_decision_log` / `model_evaluation_metrics` / `exclusive_rule_config` 三张表（已通过任务 1.x 自动完成，本任务校验存在性）

**Files:**
- 校验：`init_db.py`、PostgreSQL 实例

**实施步骤:**

1. **运行 `init_db.py`**（PG 路径下 `db.create_all()` 包含三张新表 + V3.0 视图）：

```bash
python init_db.py
```
Expected: 输出含 `[初始化] PostGIS 扩展已就绪`、`[初始化] V3.0 视图创建完成 ...`，无错误退出

2. **校验三张表存在**：

```bash
python -c "
from framework.api.app import create_app
from framework.models.user import db
from sqlalchemy import inspect
app = create_app('default')
with app.app_context():
    insp = inspect(db.engine)
    tables = insp.get_table_names()
    for t in ['routing_decision_log', 'model_evaluation_metrics', 'exclusive_rule_config']:
        assert t in tables, f'missing table: {t}'
    print('all 3 tables exist')
"
```
Expected: `all 3 tables exist`

3. **无需提交**（建表为运行时操作，无文件变更）。

---

### Task 7.2：验证路由日志双写

- [ ] **任务 7.2 完成**：执行一次 observe_routing，确认 JSONL 和 routing_decision_log 表均有记录

**Files:**
- 运行时验证：`framework/observability/observe.py`、JSONL 日志路径、`routing_decision_log` 表

**实施步骤:**

1. **执行一次 observe_routing 并验证双写**：

```bash
python -c "
import os, tempfile, json
from framework.api.app import create_app
from framework.models.user import db
from framework.models import RoutingDecisionLog
from framework.observability.routing_log import set_log_path
from framework.observability.observe import observe_routing
from framework.agents import routing as _routing

app = create_app('default')
with app.app_context():
    db.session.query(RoutingDecisionLog).delete()
    db.session.commit()
    _routing.EMBEDDING_AVAILABLE = False
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'routing_calls_e2e.jsonl')
        set_log_path(path)
        tid = observe_routing('我的田耕地质量等级是多少', {'scale': '地块'})[0] and 'e2e-002' or 'e2e-002'
        # 重新调用拿 trace_id
        from framework.observability.observe import observe_routing as _ob
        # 简化：直接查最近一条
        rows = db.session.query(RoutingDecisionLog).order_by(RoutingDecisionLog.id.desc()).limit(1).all()
        assert len(rows) == 1
        print('DB row:', rows[0].trace_id, rows[0].question_type, rows[0].routing_status)
        with open(path, encoding='utf-8') as f:
            entry = json.loads(f.readline())
        assert entry['trace_id'] == rows[0].trace_id
        print('JSONL entry trace_id matches DB row trace_id:', entry['trace_id'])
"
```
Expected: 输出 `DB row: <trace_id> 2 normal` + `JSONL entry trace_id matches DB row trace_id: <trace_id>`

2. **无需提交**（端到端验证无文件变更）。

---

### Task 7.3：验证 DB 写入失败降级

- [ ] **任务 7.3 完成**：模拟 DB 异常，确认 JSONL 写入正常且告警输出

**Files:**
- 运行时验证：`framework/observability/routing_log.py`

**实施步骤:**

1. **模拟 DB commit 失败，验证 JSONL 降级与告警**：

```bash
python -c "
import os, tempfile, json, warnings
from framework.api.app import create_app
from framework.models.user import db
from framework.models import RoutingDecisionLog
from framework.observability.routing_log import set_log_path
from framework.observability.observe import observe_routing
from framework.agents import routing as _routing

app = create_app('default')
with app.app_context():
    db.session.query(RoutingDecisionLog).delete()
    db.session.commit()
    _routing.EMBEDDING_AVAILABLE = False
    # mock commit 抛异常
    import framework.observability.routing_log as _rl
    original = db.session.commit
    db.session.commit = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('mock db down'))
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'routing_calls_e2e_fail.jsonl')
        set_log_path(path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            observe_routing('我的田耕地质量等级是多少', {'scale': '地块'}, trace_id='e2e-fail-003')
            assert any('DB 写入失败' in str(w.message) for w in caught), 'warning not emitted'
        # JSONL 仍写入
        with open(path, encoding='utf-8') as f:
            entry = json.loads(f.readline())
        assert entry['trace_id'] == 'e2e-fail-003'
        # DB 无记录（commit 失败）
        rows = db.session.query(RoutingDecisionLog).filter_by(trace_id='e2e-fail-003').all()
        assert len(rows) == 0
        print('JSONL fallback ok, warning emitted, DB row count=0')
    db.session.commit = original
"
```
Expected: `JSONL fallback ok, warning emitted, DB row count=0`

2. **无需提交**。

---

### Task 7.4：验证排他规则动态加载

- [ ] **任务 7.4 完成**：向 `exclusive_rule_config` 表插入测试规则，调用 `refresh_rules_cache()`，确认路由判定使用 DB 规则

**Files:**
- 运行时验证：`framework/agents/exclusive_rules.py`、`exclusive_rule_config` 表

**实施步骤:**

1. **插入测试规则 + refresh + 验证判定使用 DB 规则**：

```bash
python -c "
from framework.api.app import create_app
from framework.models.user import db
from framework.models import ExclusiveRuleConfig
from framework.agents.exclusive_rules import from_database, _get_active_rules, refresh_rules_cache, EXCLUSIVE_RULES

app = create_app('default')
with app.app_context():
    db.session.query(ExclusiveRuleConfig).delete()
    db.session.commit()
    refresh_rules_cache()
    # 初始：回退硬编码
    assert _get_active_rules() == EXCLUSIVE_RULES
    # 插入 1 条 DB 规则
    row = ExclusiveRuleConfig(
        rule_name='e2e-test',
        rule_pair=['model-2', 'model-3'],
        discriminator='业务任务',
        condition='现状评价',
        target='model-3',
        dimension_conditions={},
        enabled=True,
    )
    db.session.add(row)
    db.session.commit()
    refresh_rules_cache()
    rules = _get_active_rules()
    assert len(rules) == 1
    assert rules[0].target == 'model-3'
    print('DB rule loaded:', rules[0].target)
    # 清理
    db.session.query(ExclusiveRuleConfig).delete()
    db.session.commit()
    refresh_rules_cache()
    assert _get_active_rules() == EXCLUSIVE_RULES
    print('cleanup ok, fallback to hardcoded')
"
```
Expected: `DB rule loaded: model-3` + `cleanup ok, fallback to hardcoded`

2. **无需提交**。

---

### Task 7.5：验证混淆矩阵落库

- [ ] **任务 7.5 完成**：运行 `python scripts/run_routing_regression.py`，确认 `model_evaluation_metrics` 表有记录

**Files:**
- 运行时验证：`scripts/run_routing_regression.py`、`model_evaluation_metrics` 表

**实施步骤:**

1. **清理 `model_evaluation_metrics` 表 + 运行回归脚本 + 验证落库**：

```bash
python -c "
from framework.api.app import create_app
from framework.models.user import db
from framework.models import ModelEvaluationMetrics
app = create_app('default')
with app.app_context():
    db.session.query(ModelEvaluationMetrics).delete()
    db.session.commit()
print('cleared model_evaluation_metrics')
"
python scripts/run_routing_regression.py --output logs/confusion_matrix_e2e.json
python -c "
from framework.api.app import create_app
from framework.models.user import db
from framework.models import ModelEvaluationMetrics
app = create_app('default')
with app.app_context():
    rows = db.session.query(ModelEvaluationMetrics).all()
    pairs = sorted({r.model_pair for r in rows})
    assert pairs == ['model-1-vs-model-5', 'model-2-vs-model-3'], pairs
    for r in rows:
        assert r.evaluation_mode == 'keyword'
    print(f'DB rows: {len(rows)}, pairs: {pairs}')
"
```
Expected: 第二条命令输出混淆矩阵统计；第三条命令输出 `DB rows: 2, pairs: ['model-1-vs-model-5', 'model-2-vs-model-3']`

2. **无需提交**（端到端验证无文件变更）。

---

## Self-Review

**1. Spec coverage**（Design Doc §3 + §4 全覆盖校验）：

- §3.1.1 `write_routing_log_to_db` → Task 2.1 ✓
- §3.1.2 `write_routing_log` 双写 → Task 2.2 ✓
- §3.1.3 try/except 边界 → Task 2.3 ✓
- §3.2.1 字段调整（duration_ms→total_duration_ms / relevance / five_dim_context / logged_at）→ Task 3.4 / 3.1 / 3.2 / 3.3 ✓
- §3.2.2 字段重命名影响范围（observe.py 2 处 + test:69 1 处）→ Task 3.4 + Task 6.4 ✓
- §3.2.3 five_dim_context 4 字段子集决策 → Task 3.2 已落实（仅 scale/data_type/business_task/expected_output）✓
- §3.3.1 `from_database()` → Task 4.1 ✓
- §3.3.2 `_get_active_rules()` → Task 4.3 ✓
- §3.3.3 `refresh_rules_cache()` → Task 4.3（与 `_get_active_rules` 同 commit，避免拆分过细）✓
- §3.3.4 `apply_exclusive_rules` + `observe._matched_rules` 修改 → Task 4.4 + 4.5 ✓
- §3.4.1 `write_metrics_to_db` → Task 5.1 ✓
- §3.4.2 `main()` 调用 → Task 5.2 ✓
- §3.5.1 `test_routing_log_db.py` 3 用例 → Task 6.1 ✓
- §3.5.2 `test_exclusive_rules_db.py` 5 用例 → Task 6.2 ✓
- §3.5.3 `test_regression_metrics_db.py` 2 用例 → Task 6.3 ✓
- §3.5.4 测试隔离 fixture → Task 6.1 / 6.2 / 6.3 已实现 `pg_app` fixture ✓
- §3.5.5 PG 不可用跳过机制 → Task 6.1 conftest 更新 ✓
- §3.5.6 现有测试更新（test:69）→ Task 6.4 ✓
- §4 端到端验证 5 步 → Task 7.1 / 7.2 / 7.3 / 7.4 / 7.5 ✓

**2. Placeholder scan**：本计划无 TBD / TODO / "implement later" / "add appropriate error handling" 等占位符；每个 step 都有完整代码或具体命令与期望输出。

**3. Type consistency**：
- `write_routing_log_to_db(entry: Dict[str, Any]) -> None`：Task 2.1 定义 → Task 2.2 调用 ✓
- `_db_rules_cache: Optional[Tuple[ExclusiveRule, ...]] = None`：Task 4.1 声明 → Task 4.3 操作 ✓
- `from_database() -> Tuple[ExclusiveRule, ...]`：Task 4.1 定义 → Task 4.3 调用 ✓
- `_get_active_rules() -> Tuple[ExclusiveRule, ...]`：Task 4.3 定义 → Task 4.4 / 4.5 调用 ✓
- `refresh_rules_cache() -> None`：Task 4.3 定义 → Task 6.2 / 7.4 调用 ✓
- `write_metrics_to_db(matrix: dict, evaluation_mode: str) -> None`：Task 5.1 定义 → Task 5.2 调用 ✓
- `entry["total_duration_ms"]` / `entry["relevance"]` / `entry["five_dim_context"]` / `entry["logged_at"]`：Task 3.x 赋值 → Task 2.1 `write_routing_log_to_db` 通过 `entry.get(...)` 落库 ✓
- `RoutingDecisionLog` / `ModelEvaluationMetrics` / `ExclusiveRuleConfig`：Task 1.x 已就绪，Task 2.1 / 5.1 / 4.1 消费 ✓
- `PG_AVAILABLE`：Task 6.1 conftest 定义 → Task 6.1 / 6.2 / 6.3 通过 `pytestmark = pytest.mark.skipif(not PG_AVAILABLE, ...)` 消费 ✓

---

## 任务总数

- 任务 2.x：3 个（2.1, 2.2, 2.3）
- 任务 3.x：4 个（3.1, 3.2, 3.3, 3.4）
- 任务 4.x：5 个（4.1, 4.2, 4.3, 4.4, 4.5）
- 任务 5.x：3 个（5.1, 5.2, 5.3）
- 任务 6.x：4 个（6.1, 6.2, 6.3, 6.4）
- 任务 7.x：5 个（7.1, 7.2, 7.3, 7.4, 7.5）

**任务总数：24 个**（任务 1.x 已通过 `2026-08-16-add-thematic-model-orm` 变更完成，本计划不覆盖）
