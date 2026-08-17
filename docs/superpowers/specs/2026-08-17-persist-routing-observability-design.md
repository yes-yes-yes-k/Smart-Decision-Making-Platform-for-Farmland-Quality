---
comet_change: persist-routing-observability
role: technical-design
canonical_spec: openspec
---

# Design Doc: 路由可观测性数据库持久化

## 1. 背景

### 1.1 问题

当前路由可观测性体系依赖文件存储：

1. **路由日志**：`framework/observability/routing_log.py` 的 `write_routing_log(entry)` 追加 JSON 行到 `logs/routing_calls_YYYYMMDD.jsonl`
2. **排他规则**：`framework/agents/exclusive_rules.py` 的 `EXCLUSIVE_RULES` 硬编码为 Python 元组（8 条规则）
3. **混淆矩阵**：`scripts/run_routing_regression.py` 输出 JSON 文件到 `logs/confusion_matrix.json`

文件存储无法支持结构化查询、跨时间维度聚合分析、动态配置管理和多实例并发写入。

### 1.2 目标

- 路由日志双写：JSONL 文件 + `routing_decision_log` 表，DB 失败回退 JSONL
- 排他规则动态加载：从 `exclusive_rule_config` 表加载，DB 不可用回退硬编码
- 混淆矩阵评估结果落库 `model_evaluation_metrics` 表
- entry 结构与 `routing_decision_log` 表字段对齐

### 1.3 非目标

- 不修改路由判定逻辑（`identify_question_type`、`apply_exclusive_rules` 的匹配算法不变）
- 不删除 JSONL 文件存储（作为降级备份保留）
- 不迁移历史 JSONL 数据到 DB
- 不修改 `routing-exclusive-rules` spec（五维路由特征判定逻辑不变）

## 2. 现状与已完成

### 2.1 数据库基础设施现状

design.md 提到"开发环境使用 SQLite，生产环境支持 MySQL"——**此描述已过时**。项目已通过 `2026-08-15-migrate-to-postgresql-postgis` 变更迁移到 PostgreSQL 16 + PostGIS 3.4：

- [framework/config.py](file:///d:/17417/Documents/agent_culti_demo/framework/config.py) 默认 `SQLALCHEMY_DATABASE_URI = postgresql+psycopg2://...`
- `SQLiteConfig` 仅供测试套件临时数据库使用
- [init_db.py](file:///d:/17417/Documents/agent_culti_demo/init_db.py) 已支持 PostGIS 扩展初始化 + V3.0 视图脚本（v_model_execution_summary / v_parcel_stability_spatial / v_confusion_matrix_latest）

### 2.2 任务 1.x 已完成的实现

design.md 任务 1.1-1.5 已通过 `2026-08-16-add-thematic-model-orm` 变更完成：

- [framework/models/thematic_model.py](file:///d:/17417/Documents/agent_culti_demo/framework/models/thematic_model.py) L368-444 已定义 `RoutingDecisionLog`、`ModelEvaluationMetrics`、`ExclusiveRuleConfig` 三个 ORM 模型，字段与 design.md 任务 1.1-1.3 描述完全一致：
  - `RoutingDecisionLog`（routing_decision_log 表）：trace_id, question, question_type, relevance, routing_status, router_method, candidate_agents(JSON), hit_exclusive_rules(JSON), llm_reason, llm_duration_ms, total_duration_ms, degradation, five_dim_context(JSON), data_version, agent_version, result_version, failure_reason, logged_at
  - `ModelEvaluationMetrics`（model_evaluation_metrics 表）：model_pair, positive_label, tp, fp, fn, tn, total, accuracy, confusion_rate, evaluation_mode, sample_count, evaluated_at
  - `ExclusiveRuleConfig`（exclusive_rule_config 表）：rule_name, rule_pair(JSON), discriminator, condition, target, dimension_conditions(JSON), enabled, created_at, updated_at
- [framework/models/__init__.py](file:///d:/17417/Documents/agent_culti_demo/framework/models/__init__.py) 已注册三个模型
- [init_db.py](file:///d:/17417/Documents/agent_culti_demo/init_db.py) 已通过 `db.create_all()` 自动创建新表

本 Design Doc 跳过任务 1.x 的实施，聚焦任务 2.x-7.x。

## 3. 详细设计

### 3.1 路由日志 DB 双写层（任务 2.x）

**文件**：`framework/observability/routing_log.py`

#### 3.1.1 新增 `write_routing_log_to_db(entry)`

```python
def write_routing_log_to_db(entry: Dict[str, Any]) -> None:
    """将 entry 写入 routing_decision_log 表。
    
    字段映射：
    - entry["question_type"] → RoutingDecisionLog.question_type
    - entry["relevance"] → RoutingDecisionLog.relevance
    - entry["routing_status"] → RoutingDecisionLog.routing_status
    - entry["router_method"] → RoutingDecisionLog.router_method
    - entry["candidate_agents"] → RoutingDecisionLog.candidate_agents (JSON list)
    - entry["hit_exclusive_rules"] → RoutingDecisionLog.hit_exclusive_rules (JSON list)
    - entry["llm_reason"] → RoutingDecisionLog.llm_reason
    - entry["llm_duration_ms"] → RoutingDecisionLog.llm_duration_ms
    - entry["total_duration_ms"] → RoutingDecisionLog.total_duration_ms
    - entry["degradation"] → RoutingDecisionLog.degradation
    - entry["five_dim_context"] → RoutingDecisionLog.five_dim_context (JSON dict)
    - entry["data_version"] → RoutingDecisionLog.data_version
    - entry["agent_version"] → RoutingDecisionLog.agent_version
    - entry["result_version"] → RoutingDecisionLog.result_version
    - entry["failure_reason"] → RoutingDecisionLog.failure_reason
    - entry["logged_at"] → RoutingDecisionLog.logged_at
    - entry["trace_id"] → RoutingDecisionLog.trace_id
    - entry["question"] → RoutingDecisionLog.question
    
    抛出所有异常由调用方 try/except 隔离。
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

#### 3.1.2 修改 `write_routing_log(entry)` 实现双写

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

#### 3.1.3 try/except 边界

- `write_routing_log_to_db` 内部异常（SQLAlchemy IntegrityError、OperationalError、字段缺失等）抛出
- `write_routing_log` 用 try/except 隔离 DB 写入异常，仅 warnings.warn，不传播
- `observe.py` 的 `_safe_write_log` 已有外层 try/except 兜底，DB 异常不会影响路由主流程

### 3.2 observe.py entry 字段对齐（任务 3.x）

**文件**：`framework/observability/observe.py`

#### 3.2.1 字段调整

| 字段 | 当前 | 调整后 | 来源 |
|------|------|--------|------|
| `duration_ms` | `entry["duration_ms"] = ...` | `entry["total_duration_ms"] = ...`（完全重命名，不保留别名） | time.perf_counter() 差值 |
| `relevance` | 缺失 | `entry["relevance"] = relevance`（已从 identify_question_type 返回值获得） | observe_routing 局部变量 |
| `five_dim_context` | 缺失 | `entry["five_dim_context"] = {k: context.get(k) for k in ("scale", "data_type", "business_task", "expected_output")}` | observe_routing context 参数 |
| `logged_at` | 缺失 | `entry["logged_at"] = datetime.now(timezone.utc)` | datetime 模块 |

#### 3.2.2 字段重命名影响范围

已核实（grep "duration_ms" 全仓）：`entry["duration_ms"]` 仅在 `observe.py` L94 和 L100 写入，`tests/test_routing_observability.py:69` 断言使用。`ModelExecutionLog.duration_ms` 是独立字段（执行耗时，与路由总耗时不冲突），`_last_llm_duration_ms` 是 routing.py 模块级变量（LLM 耗时，不冲突）。完全重命名仅影响：
- `framework/observability/observe.py`：2 处赋值
- `tests/test_routing_observability.py:69`：1 处断言

#### 3.2.3 five_dim_context 字段范围

`_extract_five_dim_context` 在 [framework/agents/nodes.py:98](file:///d:/17417/Documents/agent_culti_demo/framework/agents/nodes.py#L98) 返回 6 字段（scale/data_type/business_task/expected_output + parcel_id/parcel_code）。但 `RoutingDecisionLog.five_dim_context` 注释为 `五维上下文 {scale, data_type, business_task, expected_output}`（4 字段）。

**决策**：entry["five_dim_context"] 只保存 4 个五维字段，地块标识（parcel_id/parcel_code）不入此字段，避免与 model_execution_log 的 parcel_id 重复存储。

### 3.3 排他规则动态加载（任务 4.x）

**文件**：`framework/agents/exclusive_rules.py`

#### 3.3.1 新增 `from_database()`

```python
_db_rules_cache: Optional[Tuple[ExclusiveRule, ...]] = None

def from_database() -> Tuple[ExclusiveRule, ...]:
    """从 exclusive_rule_config 表加载 enabled=true 的规则。
    
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

#### 3.3.2 `_get_active_rules()` 统一入口

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
```

#### 3.3.3 `refresh_rules_cache()` 手动刷新 API

```python
def refresh_rules_cache() -> None:
    """手动刷新 DB 规则缓存。供运维/测试调用，运行时不自动刷新。
    
    场景：运维通过 DB 修改 exclusive_rule_config 表后，调用此函数使新规则生效。
    """
    global _db_rules_cache
    _db_rules_cache = None  # 清空缓存，下次 _get_active_rules() 重新加载
```

#### 3.3.4 `apply_exclusive_rules` 与 `observe._matched_rules` 修改

- `apply_exclusive_rules`：将 `for rule in EXCLUSIVE_RULES` 改为 `for rule in _get_active_rules()`
- `observe._matched_rules`：将 `[r.target for r in EXCLUSIVE_RULES if ...]` 改为 `[r.target for r in _get_active_rules() if ...]`

### 3.4 混淆矩阵落库（任务 5.x）

**文件**：`scripts/run_routing_regression.py`

#### 3.4.1 新增 `write_metrics_to_db(matrix, evaluation_mode)`

```python
def write_metrics_to_db(matrix: dict, evaluation_mode: str) -> None:
    """批量写入 model_evaluation_metrics 表。
    
    matrix 格式：{pair_label: {tp, fp, fn, tn, total, accuracy, confusion_rate}}
    每对插入一条记录，positive_label 来自 PAIR_POSITIVE 映射。
    
    DB 写入失败时保留 JSON 文件输出并告警，不改退出码。
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

#### 3.4.2 `main()` 调用

在 `main()` 写入 JSON 文件后调用 `write_metrics_to_db(matrix, evaluation_mode="keyword")`。`evaluation_mode` 固定为 `"keyword"`（回归脚本仅用关键词路由）。

### 3.5 测试（任务 6.x）

**测试数据库**：PostgreSQL 测试库（`create_app('default')` + 本地 PG 实例）

#### 3.5.1 `tests/test_routing_log_db.py`

- `test_double_write_normal`：执行 observe_routing，验证 JSONL 和 routing_decision_log 表均有记录，trace_id 一致
- `test_db_failure_fallback_jsonl`：mock db.session.commit 抛异常，验证 JSONL 仍写入，warnings.warn 触发
- `test_entry_field_alignment`：验证 entry 包含 total_duration_ms、relevance、five_dim_context、logged_at 四个新字段

#### 3.5.2 `tests/test_exclusive_rules_db.py`

- `test_from_database_loads`：插入测试规则到 exclusive_rule_config 表，验证 from_database() 返回正确规则
- `test_db_unavailable_fallback`：mock db.session 抛异常，验证 _get_active_rules() 回退 EXCLUSIVE_RULES
- `test_db_empty_fallback`：表为空时回退硬编码
- `test_db_rules_match_hardcoded`：构造 DB 规则等价于硬编码规则，验证判定结果一致
- `test_refresh_rules_cache`：调用 refresh_rules_cache() 后，新插入的规则立即可见

#### 3.5.3 `tests/test_regression_metrics_db.py`

- `test_metrics_written_to_db`：运行 run_routing_regression.main()，验证 model_evaluation_metrics 表有 2 条记录（model-1-vs-model-5 / model-2-vs-model-3）
- `test_db_failure_keeps_json`：mock db.session.commit 失败，验证 JSON 文件仍输出，退出码不变

#### 3.5.4 测试隔离

每个测试用例 setup 时清理对应表：

```python
@pytest.fixture(autouse=True)
def clean_db_tables():
    from framework.models import db, RoutingDecisionLog, ModelEvaluationMetrics, ExclusiveRuleConfig
    db.session.query(RoutingDecisionLog).delete()
    db.session.query(ModelEvaluationMetrics).delete()
    db.session.query(ExclusiveRuleConfig).delete()
    db.session.commit()
    yield
```

#### 3.5.5 PG 不可用跳过机制

[tests/conftest.py](file:///d:/17417/Documents/agent_culti_demo/tests/conftest.py) 增加 `try_pg_connection()` fixture，PG 不可用时三个新测试文件用 `@pytest.mark.skipif(not PG_AVAILABLE)` 跳过。

#### 3.5.6 现有测试更新

[test_routing_observability.py:69](file:///d:/17417/Documents/agent_culti_demo/tests/test_routing_observability.py#L69) 断言 `"duration_ms"` 改为 `"total_duration_ms"`。

## 4. 端到端验证（任务 7.x）

1. 运行 `python init_db.py` 创建三张新表（已通过任务 1.x 自动完成）
2. 验证路由日志双写：执行一次 observe_routing，确认 JSONL 和 routing_decision_log 表均有记录
3. 验证 DB 写入失败降级：mock DB 异常，确认 JSONL 写入正常且告警输出
4. 验证排他规则动态加载：向 exclusive_rule_config 表插入测试规则，调用 refresh_rules_cache()，确认路由判定使用 DB 规则
5. 验证混淆矩阵落库：运行 `python scripts/run_routing_regression.py`，确认 model_evaluation_metrics 表有记录

## 5. Risks / Trade-offs

- **DB 写入延迟影响路由主流程**：`_safe_write_log` 已用 try/except 隔离，DB 写入异常不传播；当前同步写入可接受，未来可考虑异步写入
- **双写数据一致性**：DB 和 JSONL 可能出现短时不一致（DB 成功但 JSONL 失败，或反之）。以 DB 为主存储，JSONL 为降级备份，不一致时以 DB 为准
- **排他规则缓存运行时不刷新**：用户决策不引入后台线程，运行时配置变更需手动调用 refresh_rules_cache()。如果未来需要自动刷新，可演进为 TTL 懒加载或后台定时任务
- **测试依赖本地 PG**：用户决策使用 PostgreSQL 测试库，CI 需配置 PG 服务；conftest.py 增加跳过机制避免无 PG 环境失败
- **five_dim_context 字段语义**：4 字段而非 6 字段，地块标识不入此字段。如未来需要查询地块维度，可改用 model_execution_log.parcel_id
