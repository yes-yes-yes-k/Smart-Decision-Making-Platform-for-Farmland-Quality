---
comet_change: integrate-parcel-db-into-models
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-18-integrate-parcel-db-into-models
status: final
---

# Design Doc: 集成数据库地块数据到专题模型

## 1. 概述

本设计文档细化如何让 5 个专题模型 Agent（Model-1 到 Model-5）优先从 PostgreSQL `parcel_info` 表读取地块指标进行计算，并将结果同步持久化到 V3.0 结果表和 `model_execution_log`。

详见 OpenSpec 产物：
- `openspec/changes/integrate-parcel-db-into-models/proposal.md` — 问题背景与目标
- `openspec/changes/integrate-parcel-db-into-models/specs/professional-model-agents/spec.md` — 能力规格
- `openspec/changes/integrate-parcel-db-into-models/design.md` — 高层架构决策
- `openspec/changes/integrate-parcel-db-into-models/tasks.md` — 任务清单

## 2. ParcelDataAccessor

### 2.1 位置与接口

文件：`framework/domain/data/parcel_data_accessor.py`

```python
class ParcelDataAccessor:
    """从 parcel_info 表查询地块指标的统一入口。"""

    def get_parcel_indicators(self, parcel_id: str) -> Optional[dict]:
        """按 parcel_id 查询 soil_indicators JSON 字段。

        Returns:
            dict: soil_indicators 内容（如 {"soil_ph": 5.5, "organic_matter": 2.1, ...}）
            None: parcel_id 不存在或 DB 异常
        """
```

### 2.2 实现细节

- 查询 `ParcelInfo.query.filter_by(parcel_id=parcel_id).first()`
- 返回 `parcel_info.soil_indicators`（JSON 字段，Python 自动解析为 dict）
- DB 异常（SQLAlchemyError）时记录 WARNING 日志并返回 None
- 无缓存（KISS 原则，后续如需可加）

### 2.3 使用方式

```python
# 在 Agent 的 _collect_inputs 中
accessor = ParcelDataAccessor()
indicators = accessor.get_parcel_indicators(parcel_id)
if indicators is not None:
    # 使用 DB 指标
    data_source = "db"
else:
    # 降级到 legacy
    data_source = "fallback"
```

## 3. BaseAgent._persist_result()

### 3.1 模板方法模式

`BaseAgent` 增加两个方法：

```python
def _persist_result(self, agent_id: str, parcel_id: Optional[str],
                    inputs: dict, outputs: dict, status: str) -> bool:
    """同步持久化执行日志和结果表。

    Args:
        agent_id: Agent 标识（如 "model-1"）
        parcel_id: 地块 ID（Model-5 县级分析时为 None）
        inputs: 输入快照
        outputs: 输出快照
        status: "ok" | "degraded" | "error"

    Returns:
        True: 持久化成功
        False: 持久化失败（已记录 ERROR 日志，不抛异常）
    """

def _build_result_record(self, execution_id: int, outputs: dict) -> Optional[db.Model]:
    """构建结果表 ORM 实例。子类 override 返回对应结果表记录。

    Args:
        execution_id: model_execution_log.id
        outputs: 模型输出

    Returns:
        ORM 实例（如 StabilityRiskResult(...)）或 None（无结果表时）
    """
    return None  # 默认：无结果表
```

### 3.2 事务管理

```python
def _persist_result(self, agent_id, parcel_id, inputs, outputs, status):
    try:
        with db.session.begin():
            # 1. 写 execution_log
            log = ModelExecutionLog(
                agent_id=agent_id,
                parcel_id=parcel_id,
                status=status,
                input_snapshot=inputs,
                output_snapshot=outputs,
                started_at=...,
                completed_at=datetime.now(timezone.utc),
            )
            db.session.add(log)
            db.session.flush()  # 获取 log.id

            # 2. 子类构建结果表记录
            result_record = self._build_result_record(log.id, outputs)
            if result_record is not None:
                db.session.add(result_record)

        return True
    except Exception as e:
        logger.error(f"Persist failed for {agent_id}: {e}")
        return False
```

### 3.3 错误处理

- `_persist_result()` 内部 try/except 捕获所有异常
- 失败时记录 ERROR 日志，返回 False
- **不抛异常**，不影响返回给用户的计算结果
- 调用方根据返回值设置 `persisted: true/false` 标识

## 4. Agent _collect_inputs 改造模式

### 4.1 统一改造模式

每个 Agent 的 `_collect_inputs` 重构为：

```python
def _collect_inputs(self, context: dict) -> dict:
    parcel_id = context.get("parcel_id")

    # DB 优先
    if parcel_id:
        accessor = ParcelDataAccessor()
        indicators = accessor.get_parcel_indicators(str(parcel_id))
        if indicators is not None:
            inputs = self._map_indicators_to_inputs(indicators)
            inputs["data_source"] = "db"
            return inputs

    # 降级到 legacy
    logger.warning(f"Parcel {parcel_id} not in DB, falling back to legacy source")
    inputs = self._collect_inputs_from_legacy(context)
    inputs["data_source"] = "fallback"
    return inputs

def _collect_inputs_from_legacy(self, context: dict) -> dict:
    """原有 _collect_inputs 逻辑，重命名保留。"""
    # ... 各 Agent 的现有实现 ...
```

### 4.2 各 Agent 的 _map_indicators_to_inputs

每个 Agent 需实现字段映射：

```python
def _map_indicators_to_inputs(self, indicators: dict) -> dict:
    """将 soil_indicators JSON 映射为模型输入字段。"""
    return {
        "soil_ph": indicators.get("soil_ph"),
        "organic_matter": indicators.get("organic_matter"),
        # ... 各模型所需字段 ...
    }
```

### 4.3 各 Agent 的 legacy 数据源

| Agent | Legacy 方法 | 数据源 |
|-------|------------|--------|
| Model-1 | `_collect_inputs_from_legacy` | MOCK_COUNTIES 硬编码 |
| Model-2 | `_collect_inputs_from_legacy` | CSV `run_grade_evaluation` |
| Model-3 | `_collect_inputs_from_legacy` | SQLite `query_parcel` |
| Model-4 | `_collect_inputs_from_legacy` | SQLite `_query_sjd_by_parcel_id` |
| Model-5 | `_collect_inputs_from_legacy` | 用户传入参数 |

## 5. Agent execute() 改造模式

```python
def execute(self, context: dict) -> dict:
    inputs = self._collect_inputs(context)
    data_source = inputs.pop("data_source", "unknown")

    try:
        outputs = self._run_model(inputs)  # 各 Agent 的现有计算逻辑
        status = "ok" if data_source == "db" else "degraded"
        persisted = self._persist_result(
            agent_id=self.agent_id,
            parcel_id=context.get("parcel_id"),
            inputs=inputs,
            outputs=outputs,
            status=status,
        )
        return {
            **outputs,
            "data_source": data_source,
            "persisted": persisted,
        }
    except Exception as e:
        self._persist_result(
            agent_id=self.agent_id,
            parcel_id=context.get("parcel_id"),
            inputs=inputs,
            outputs={"error": str(e)},
            status="error",
        )
        raise  # 或返回错误响应，取决于现有错误处理模式
```

## 6. 各 Agent 的 _build_result_record 实现

### Model-1 StabilityRiskAgent

```python
def _build_result_record(self, execution_id: int, outputs: dict) -> db.Model:
    return StabilityRiskResult(
        execution_id=execution_id,
        parcel_id=outputs.get("parcel_id"),
        stability_score=outputs.get("stability_score"),
        risk_level=outputs.get("risk_level"),
        # ... 其他字段 ...
    )
```

### Model-2 QualityGradeResult

```python
def _build_result_record(self, execution_id: int, outputs: dict) -> db.Model:
    return QualityGradeResult(
        execution_id=execution_id,
        parcel_id=outputs.get("parcel_id"),
        quality_grade=outputs.get("quality_grade"),
        comprehensive_index=outputs.get("comprehensive_index"),
        # ...
    )
```

### Model-3/4/5 类似

各 Agent 根据对应结果表的字段映射。

## 7. 测试策略

### 7.1 ParcelDataAccessor 单元测试

文件：`tests/test_parcel_data_accessor.py`

| 测试场景 | 方法 |
|---------|------|
| DB 命中 | mock `ParcelInfo.query`，验证返回 dict |
| DB 未命中 | mock 返回 None，验证返回 None |
| DB 异常 | mock 抛 SQLAlchemyError，验证返回 None + WARNING 日志 |

### 7.2 BaseAgent._persist_result() 单元测试

文件：`tests/test_base_agent_persist.py`

| 测试场景 | 方法 |
|---------|------|
| 成功写入 | mock db.session，验证 execution_log + 结果表被 add |
| 写入失败 | mock db.session 抛异常，验证返回 False + ERROR 日志 |
| 事务 rollback | 验证失败时整体 rollback |
| _build_result_record 返回 None | 验证只写 execution_log，不写结果表 |

### 7.3 Agent 集成测试

更新各 Agent 现有测试：

| 测试场景 | 方法 |
|---------|------|
| DB 优先路径 | mock ParcelDataAccessor 返回 dict，验证 data_source="db" |
| Fallback 降级 | mock ParcelDataAccessor 返回 None，验证 data_source="fallback" + WARNING |
| 持久化成功 | mock _persist_result 返回 True，验证 persisted=true |
| 持久化失败 | mock _persist_result 返回 False，验证 persisted=false |

## 8. 边界条件

- **parcel_id 为空**：Model-5 县级分析时 parcel_id 可为 None，跳过 DB 查询直接用 legacy
- **soil_indicators 缺字段**：`_map_indicators_to_inputs` 用 `.get()` 返回 None，模型内部处理缺失值
- **DB 连接断开**：ParcelDataAccessor 捕获异常返回 None，触发 fallback
- **结果表字段类型不匹配**：`_build_result_record` 中做类型转换（如 float()）
- **并发写入**：依赖 PostgreSQL 事务隔离，不做额外处理

## 9. 实现顺序

1. `ParcelDataAccessor`（无依赖，可独立测试）
2. `BaseAgent._persist_result()` + `_build_result_record()` 钩子
3. Model-1 改造（最简单，MOCK_COUNTIES 直接替换）
4. Model-2/3/4 改造（有 legacy SQLite/CSV 数据源）
5. Model-5 改造（县级分析，parcel_id 可为空）
6. 测试补全
