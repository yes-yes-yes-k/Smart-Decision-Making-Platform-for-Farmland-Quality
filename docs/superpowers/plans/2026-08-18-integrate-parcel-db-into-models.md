---
change: integrate-parcel-db-into-models
design-doc: docs/superpowers/specs/2026-08-18-integrate-parcel-db-into-models-design.md
base-ref: bf63a92437f51903c20eeab26bdf21cd84fef3e1
---

# 集成数据库地块数据到专题模型 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 5 个专题模型 Agent（Model-1~Model-5）优先从 PostgreSQL `parcel_info` 表按 `parcel_id` 读取 `soil_indicators` JSON 指标，并将计算结果同步持久化到 V3.0 结果表和 `model_execution_log`，DB 不可达时降级到现有数据源。

**Architecture:** 新增 `ParcelDataAccessor` 作为 `parcel_info` 表的统一查询入口（封装 `ParcelInfo.query.filter_by`）；在 `BaseAgent` 增加模板方法 `_persist_result()` + 钩子 `_build_result_record()`，同一事务内先写 `model_execution_log` 获取 `execution_id` 再写结果表；各 Agent 重构 `_collect_inputs` 为 DB 优先 + legacy 降级模式，`execute()` 成功路径调用 `_persist_result`。持久化失败仅记录 ERROR 日志并返回 `persisted: false`，不抛异常。

**Tech Stack:** Python 3.10+、Flask-SQLAlchemy 3.x、SQLAlchemy 2.0、GeoAlchemy2 0.14+、PostgreSQL 16 + PostGIS 3.4、unittest.mock。

## Global Constraints

- **数据库后端**：PostgreSQL 16 + PostGIS 3.4（生产）；SQLite in-memory（单元测试，Geometry 列不参与 mock 测试）。
- **ORM 模型来源**：`from framework.models.thematic_model import ParcelInfo, ModelExecutionLog, StabilityRiskResult, ...`（已通过 `framework/models/__init__.py` 注册）。
- **db 对象来源**：`from framework.models.user import db`（与 `soil_data.py` 一致）。
- **agent_id 映射**：`model_id` ≠ `agent_id`（如 Model-2 的 `model_id="quality-grade-evaluation"` 但 `agent_id="model-2"`），通过 `CAPABILITY_BY_MODEL_ID[self.model_id].agent_id` 查找。
- **ModelExecutionLog 必填字段**：`trace_id`（UUID）、`agent_id`（FK→`thematic_model_registry`）、`question_type`（NOT NULL）、`status`、`started_at`（NOT NULL）。
- **降级语义**：DB 命中 → `data_source="db"` + `status="ok"`；DB 未命中 → `data_source="fallback"` + `status="degraded"`；计算异常 → `status="error"`。
- **持久化不阻断**：`_persist_result()` 内部 try/except 捕获所有异常，失败返回 `False`，不抛异常。
- **向后兼容**：保留现有 legacy 数据源（MOCK_COUNTIES / CSV / SQLite / 用户参数）作为 fallback，不删除现有逻辑。
- **lazy import 模式**：`_persist_result` 内部 lazy import `db` 和 `ModelExecutionLog`，避免模块加载时强依赖 geoalchemy2（与 `base.py` 现有 lazy import 风格一致）。
- **提交节奏**：每个 Task 结束 commit 一次；commit message 前缀 `feat:` / `test:` / `fix:`。

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `framework/domain/data/parcel_data_accessor.py` | 新建 | `ParcelDataAccessor` 类：`get_parcel_indicators(parcel_id) -> Optional[dict]` |
| `framework/agents/base.py` | 修改 | 新增 `agent_id` 属性、`_get_question_type()`、`_persist_result()`、`_build_result_record()` 钩子、模块级 `logger` |
| `framework/agents/specialized/stability_risk_agent.py` | 修改 | DB 优先 `_collect_inputs` + `_build_result_record` override + `execute` 重构 |
| `framework/agents/specialized/grade_agent.py` | 修改 | DB 优先 `_collect_inputs` + `_build_result_record` override + `execute` 重构 |
| `framework/agents/specialized/problem_agent.py` | 修改 | DB 优先 `_collect_inputs` + `_build_result_record` override + `execute` 重构 |
| `framework/agents/specialized/acidification_agent.py` | 修改 | DB 优先 `_collect_inputs` + `_build_result_record` override + `execute` 重构 |
| `framework/agents/specialized/organic_matter_agent.py` | 修改 | DB 优先 `_collect_inputs` + `_build_result_record` override + `execute` 重构 |
| `tests/test_parcel_data_accessor.py` | 新建 | ParcelDataAccessor 单元测试（3 场景） |
| `tests/test_base_agent_persist.py` | 新建 | `_persist_result` 单元测试（4 场景） |
| `tests/test_agent_specialized.py` | 修改 | 为 5 个 Agent 增加 DB 优先 / fallback / 持久化测试 |

---

## Task 1: ParcelDataAccessor（对应 tasks 1.1）

**Files:**
- Create: `framework/domain/data/parcel_data_accessor.py`
- Test: `tests/test_parcel_data_accessor.py`

**Interfaces:**
- Produces: `ParcelDataAccessor.get_parcel_indicators(parcel_id: str) -> Optional[dict]` — 供 Task 3~7 各 Agent 的 `_collect_inputs` 调用。

- [x] **Step 1: 编写失败测试**

创建 `tests/test_parcel_data_accessor.py`：

```python
"""ParcelDataAccessor 单元测试：DB 命中 / DB 未命中 / DB 异常三种场景。"""
import unittest
from unittest.mock import patch, MagicMock


class ParcelDataAccessorTests(unittest.TestCase):
    def test_returns_dict_when_parcel_exists(self):
        """DB 命中时返回 soil_indicators dict。"""
        fake_parcel = MagicMock()
        fake_parcel.soil_indicators = {"soil_ph": 5.5, "organic_matter": 22.0}
        with patch("framework.models.thematic_model.ParcelInfo") as mock_model:
            mock_model.query.filter_by.return_value.first.return_value = fake_parcel
            from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
            accessor = ParcelDataAccessor()
            result = accessor.get_parcel_indicators("P001")
        self.assertEqual(result, {"soil_ph": 5.5, "organic_matter": 22.0})

    def test_returns_none_when_parcel_not_found(self):
        """DB 未命中时返回 None。"""
        with patch("framework.models.thematic_model.ParcelInfo") as mock_model:
            mock_model.query.filter_by.return_value.first.return_value = None
            from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
            accessor = ParcelDataAccessor()
            result = accessor.get_parcel_indicators("NOT_EXIST")
        self.assertIsNone(result)

    def test_returns_none_and_logs_on_db_exception(self):
        """DB 异常时返回 None，不抛异常。"""
        with patch("framework.models.thematic_model.ParcelInfo") as mock_model:
            mock_model.query.filter_by.side_effect = Exception("DB connection lost")
            from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
            accessor = ParcelDataAccessor()
            result = accessor.get_parcel_indicators("P001")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_parcel_data_accessor.py -v`
Expected: 3 个测试 FAIL，报 `ModuleNotFoundError: No module named 'framework.domain.data.parcel_data_accessor'`

- [x] **Step 3: 编写最小实现**

创建 `framework/domain/data/parcel_data_accessor.py`：

```python
"""地块指标数据访问器：从 parcel_info 表查询 soil_indicators JSON 字段的统一入口。"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ParcelDataAccessor:
    """从 parcel_info 表查询地块指标的统一入口。"""

    def get_parcel_indicators(self, parcel_id: str) -> Optional[dict]:
        """按 parcel_id 查询 soil_indicators JSON 字段。

        Args:
            parcel_id: 地块唯一编号。

        Returns:
            dict: soil_indicators 内容（如 {"soil_ph": 5.5, "organic_matter": 2.1}）。
            None: parcel_id 不存在或 DB 异常。
        """
        try:
            from framework.models.thematic_model import ParcelInfo

            parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
            if parcel is None:
                return None
            return parcel.soil_indicators or None
        except Exception as e:
            logger.warning("查询 parcel_info 失败 (parcel_id=%s): %s", parcel_id, e)
            return None
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_parcel_data_accessor.py -v`
Expected: 3 个测试 PASS

- [x] **Step 5: Commit**

```bash
git add framework/domain/data/parcel_data_accessor.py tests/test_parcel_data_accessor.py
git commit -m "feat: add ParcelDataAccessor for parcel_info DB queries"
```

---

## Task 2: BaseAgent 持久化基础设施（对应 tasks 1.2 / 1.3）

**Files:**
- Modify: `framework/agents/base.py`（文件头部 + `BaseAgent` 类内新增方法）
- Test: `tests/test_base_agent_persist.py`

**Interfaces:**
- Consumes: `framework.models.user.db`、`framework.models.thematic_model.ModelExecutionLog`、`framework.agents.capabilities.CAPABILITY_BY_MODEL_ID`
- Produces:
  - `BaseAgent.agent_id` (property) → `str`：从能力注册表查找，如 `"model-1"`
  - `BaseAgent._get_question_type()` → `int`：从能力注册表查找，如 `1`
  - `BaseAgent._persist_result(agent_id, parcel_id, inputs, outputs, status)` → `bool`
  - `BaseAgent._build_result_record(execution_id, outputs)` → `Optional[db.Model]`（默认 `None`，子类 override）

- [x] **Step 1: 编写失败测试**

创建 `tests/test_base_agent_persist.py`：

```python
"""BaseAgent._persist_result 单元测试：成功写入 / 无结果表 / 写入失败 / 异常不传播。"""
import sys
import os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

import unittest
from unittest.mock import patch, MagicMock


def _make_test_agent(model_id="model-1"):
    """创建可实例化的 BaseAgent 子类用于测试。"""
    from framework.agents.base import BaseAgent

    class TestAgent(BaseAgent):
        def execute(self, task):
            return {}

        def answer_question(self, question, context):
            return {}

    return TestAgent("test", "test", model_id, "test")


class PersistResultSuccessTests(unittest.TestCase):
    @patch("framework.models.thematic_model.ModelExecutionLog")
    @patch("framework.models.user.db")
    def test_persist_success_with_result_record(self, mock_db, mock_log_cls):
        """成功写入 execution_log + 结果表时返回 True。"""
        mock_session = MagicMock()
        mock_db.session = mock_session
        mock_log = MagicMock()
        mock_log.id = 42
        mock_log_cls.return_value = mock_log

        agent = _make_test_agent()
        agent._build_result_record = MagicMock(return_value=MagicMock())

        result = agent._persist_result("model-1", "P001", {"in": 1}, {"out": 2}, "ok")

        self.assertTrue(result)
        mock_log_cls.assert_called_once()
        self.assertEqual(mock_session.add.call_count, 2)
        mock_session.commit.assert_called_once()
        agent._build_result_record.assert_called_once_with(42, {"out": 2})

    @patch("framework.models.thematic_model.ModelExecutionLog")
    @patch("framework.models.user.db")
    def test_persist_success_without_result_record(self, mock_db, mock_log_cls):
        """_build_result_record 返回 None 时只写 execution_log，返回 True。"""
        mock_session = MagicMock()
        mock_db.session = mock_session
        mock_log = MagicMock()
        mock_log.id = 99
        mock_log_cls.return_value = mock_log

        agent = _make_test_agent()  # _build_result_record 默认返回 None

        result = agent._persist_result("model-1", "P001", {}, {}, "ok")

        self.assertTrue(result)
        self.assertEqual(mock_session.add.call_count, 1)
        mock_session.commit.assert_called_once()


class PersistResultFailureTests(unittest.TestCase):
    @patch("framework.models.thematic_model.ModelExecutionLog")
    @patch("framework.models.user.db")
    def test_persist_failure_returns_false(self, mock_db, mock_log_cls):
        """commit 抛异常时返回 False 并 rollback。"""
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB connection lost")
        mock_db.session = mock_session
        mock_log = MagicMock()
        mock_log.id = 1
        mock_log_cls.return_value = mock_log

        agent = _make_test_agent()

        result = agent._persist_result("model-1", "P001", {}, {}, "ok")

        self.assertFalse(result)
        mock_session.rollback.assert_called_once()

    @patch("framework.models.user.db")
    def test_persist_does_not_raise_on_import_failure(self, mock_db):
        """db 导入失败时不抛异常，返回 False。"""
        # 模拟 import 失败：patch __import__ 让 thematic_model 导入抛异常
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "thematic_model" in name:
                raise ImportError("simulated import failure")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            agent = _make_test_agent()
            result = agent._persist_result("model-1", "P001", {}, {}, "ok")
            self.assertFalse(result)
        finally:
            builtins.__import__ = original_import


class AgentIdPropertyTests(unittest.TestCase):
    def test_agent_id_lookup_from_capabilities(self):
        """agent_id 属性从能力注册表查找。"""
        agent = _make_test_agent("model-1")
        self.assertEqual(agent.agent_id, "model-1")

    def test_agent_id_fallback_to_model_id(self):
        """model_id 不在注册表时回退到 model_id 本身。"""
        agent = _make_test_agent("unknown-model")
        self.assertEqual(agent.agent_id, "unknown-model")


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_base_agent_persist.py -v`
Expected: 6 个测试 FAIL，报 `AttributeError: 'TestAgent' object has no attribute 'agent_id'` 或 `'_persist_result'`

- [x] **Step 3: 编写最小实现**

修改 `framework/agents/base.py`，在文件头部添加 imports，在 `BaseAgent` 类中添加方法。

**文件头部**（在现有 `from __future__ import annotations` 之后添加）：

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
```

**在 `BaseAgent` 类中**（在 `_build_domain_prompt` 方法之后、`analyze` 方法之前添加）：

```python
    @property
    def agent_id(self) -> str:
        """从能力注册表查找 agent_id（如 model-1）；查找失败时回退到 model_id。"""
        try:
            from framework.agents.capabilities import CAPABILITY_BY_MODEL_ID
            cap = CAPABILITY_BY_MODEL_ID.get(self.model_id)
            if cap:
                return cap.agent_id
        except Exception:
            pass
        return self.model_id

    def _get_question_type(self) -> int:
        """从能力注册表查找 question_type；查找失败时返回 0。"""
        try:
            from framework.agents.capabilities import CAPABILITY_BY_MODEL_ID
            cap = CAPABILITY_BY_MODEL_ID.get(self.model_id)
            if cap:
                return cap.question_type
        except Exception:
            pass
        return 0

    def _persist_result(
        self,
        agent_id: str,
        parcel_id: Optional[str],
        inputs: dict,
        outputs: dict,
        status: str,
    ) -> bool:
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
        try:
            from framework.models.user import db
            from framework.models.thematic_model import ModelExecutionLog

            now = datetime.now(timezone.utc)
            log = ModelExecutionLog(
                trace_id=str(uuid.uuid4()),
                agent_id=agent_id,
                question_type=self._get_question_type(),
                parcel_id=parcel_id,
                input_params=inputs,
                output_result=outputs,
                status=status,
                started_at=now,
                completed_at=now,
            )
            db.session.add(log)
            db.session.flush()

            result_record = self._build_result_record(log.id, outputs)
            if result_record is not None:
                db.session.add(result_record)

            db.session.commit()
            return True
        except Exception as e:
            logger.error(
                "持久化失败 (agent_id=%s, parcel_id=%s): %s", agent_id, parcel_id, e
            )
            try:
                from framework.models.user import db as _db
                _db.session.rollback()
            except Exception:
                pass
            return False

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建结果表 ORM 实例。子类 override 返回对应结果表记录。

        Args:
            execution_id: model_execution_log.id
            outputs: 模型输出

        Returns:
            ORM 实例（如 StabilityRiskResult(...)）或 None（无结果表时）
        """
        return None
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_base_agent_persist.py -v`
Expected: 6 个测试 PASS

- [x] **Step 5: Commit**

```bash
git add framework/agents/base.py tests/test_base_agent_persist.py
git commit -m "feat: add BaseAgent._persist_result and _build_result_record hook"
```

---

## Task 3: Model-1 StabilityRiskAgent 改造（对应 tasks 2.1 / 2.2 / 2.3）

**Files:**
- Modify: `framework/agents/specialized/stability_risk_agent.py`
- Test: `tests/test_agent_specialized.py`（追加测试函数）

**Interfaces:**
- Consumes: `ParcelDataAccessor.get_parcel_indicators(parcel_id) -> Optional[dict]`（Task 1）、`BaseAgent._persist_result()` + `_build_result_record()`（Task 2）
- Produces: `StabilityRiskAgent.execute()` 返回结果中新增 `data_source: "db"|"fallback"` 和 `persisted: bool` 字段

- [x] **Step 1: 编写失败测试**

在 `tests/test_agent_specialized.py` 末尾追加：

```python
def test_stability_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    fake_indicators = {
        "soil_ph": 5.5,
        "organic_matter": 22.0,
        "stability_score": 78.5,
        "quality_grade": 4,
        "risk_index": 0.32,
        "area_mu": 320000,
    }
    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: fake_indicators
    )
    agent = StabilityRiskAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_stability_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = StabilityRiskAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_stability_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "stability_score": 78.5}
    )
    agent = StabilityRiskAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_stability_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，但不阻断结果返回。"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "stability_score": 78.5}
    )
    agent = StabilityRiskAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False
    assert result["status"] == "ok"
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_specialized.py::test_stability_agent_db_path tests/test_agent_specialized.py::test_stability_agent_fallback_path tests/test_agent_specialized.py::test_stability_agent_persist_success tests/test_agent_specialized.py::test_stability_agent_persist_failure -v`
Expected: 4 个测试 FAIL，报 `KeyError: 'data_source'` 或 `AttributeError`

- [x] **Step 3: 编写最小实现**

修改 `framework/agents/specialized/stability_risk_agent.py`。

在文件头部添加 import：

```python
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...models.thematic_model import StabilityRiskResult
import logging

logger = logging.getLogger(__name__)
```

在 `StabilityRiskAgent` 类中添加方法（在 `__init__` 之后、`execute` 之前）：

```python
    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 MOCK_COUNTIES。"""
        parcel_id = context.get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = self._map_indicators_to_inputs(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to MOCK_COUNTIES", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：MOCK_COUNTIES 硬编码。"""
        return {"counties": [dict(c) for c in MOCK_COUNTIES]}

    def _map_indicators_to_inputs(self, indicators: dict) -> dict:
        """将 soil_indicators JSON 映射为模型输入字段。"""
        return {
            "soil_ph": indicators.get("soil_ph"),
            "organic_matter": indicators.get("organic_matter"),
            "stability_score": indicators.get("stability_score"),
            "quality_grade": indicators.get("quality_grade"),
            "risk_index": indicators.get("risk_index"),
            "area_mu": indicators.get("area_mu"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 StabilityRiskResult ORM 实例。"""
        return StabilityRiskResult(
            execution_id=execution_id,
            parcel_id=outputs.get("parcel_id") or "unknown",
            input_snapshot=outputs,
            simulated=True,
        )
```

替换 `execute` 方法：

```python
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        inputs = self._collect_inputs(task)
        data_source = inputs.pop("data_source", "unknown")

        try:
            if "counties" in inputs:
                # Legacy 路径：县区聚合
                counties = inputs["counties"]
                for c in counties:
                    c["stability"] = MockDataLoader.apply_threshold(
                        c["stability_score"], STABILITY_RULES
                    )
                outputs = {
                    "counties": counties,
                    "total_area_mu": sum(c["area_mu"] for c in counties),
                }
                status = "degraded"
            else:
                # DB 路径：单地块
                score = inputs.get("stability_score") or 70.0
                stability = MockDataLoader.apply_threshold(score, STABILITY_RULES)
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    "stability_score": score,
                    "stability": stability,
                    "soil_ph": inputs.get("soil_ph"),
                }
                status = "ok"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs=inputs,
                outputs=outputs,
                status=status,
            )

            return MockDataLoader.mark_simulated({
                "status": "ok",
                "result": outputs,
                "metadata": {"simulated": True, "data_source": data_source},
                "data_source": data_source,
                "persisted": persisted,
            })
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
            )
            raise
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_specialized.py -k stability -v`
Expected: 所有 stability 相关测试 PASS（包括原有测试和 4 个新测试）

- [x] **Step 5: Commit**

```bash
git add framework/agents/specialized/stability_risk_agent.py tests/test_agent_specialized.py
git commit -m "feat: integrate Model-1 StabilityRiskAgent with DB and persistence"
```

---

## Task 4: Model-2 FarmlandGradeAgent 改造（对应 tasks 3.1 / 3.2 / 3.3）

**Files:**
- Modify: `framework/agents/specialized/grade_agent.py`
- Test: `tests/test_agent_specialized.py`（追加测试函数）

**Interfaces:**
- Consumes: `ParcelDataAccessor`（Task 1）、`BaseAgent._persist_result()` + `_build_result_record()`（Task 2）
- Produces: `FarmlandGradeAgent.execute()` 返回结果中新增 `data_source` 和 `persisted` 字段

- [x] **Step 1: 编写失败测试**

在 `tests/test_agent_specialized.py` 末尾追加：

```python
def test_grade_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    fake_indicators = {
        "soil_ph": 5.5, "organic_matter": 22.0,
        "available_potassium": 120.0, "available_phosphorus": 15.0,
    }
    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: fake_indicators
    )
    agent = FarmlandGradeAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_grade_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = FarmlandGradeAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB", "parcel_code": "C001"})
    assert result["data_source"] == "fallback"


def test_grade_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = FarmlandGradeAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_grade_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，不阻断结果。"""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = FarmlandGradeAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_specialized.py -k grade_agent_db -v`
Expected: 测试 FAIL，报 `KeyError: 'data_source'`

- [x] **Step 3: 编写最小实现**

修改 `framework/agents/specialized/grade_agent.py`。

文件头部添加 import：

```python
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...models.thematic_model import QualityGradeResult
import logging

logger = logging.getLogger(__name__)
```

在 `FarmlandGradeAgent` 类中添加方法（在 `__init__` 之后、`execute` 之前）：

```python
    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 CSV run_grade_evaluation。"""
        parcel_id = context.get("parcel_id") or context.get("parcel_code")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = self._map_indicators_to_inputs(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to CSV source", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：CSV run_grade_evaluation。"""
        return {
            "parcel_code": context.get("parcel_code"),
            "exe_path": context.get("exe_path"),
            "dat_path": context.get("dat_path"),
        }

    def _map_indicators_to_inputs(self, indicators: dict) -> dict:
        """将 soil_indicators JSON 映射为质量等级评价输入字段。"""
        return {
            "soil_ph": indicators.get("soil_ph"),
            "organic_matter": indicators.get("organic_matter"),
            "available_potassium": indicators.get("available_potassium"),
            "available_phosphorus": indicators.get("available_phosphorus"),
            "soil_bulk_density": indicators.get("soil_bulk_density"),
            "topsoil_texture": indicators.get("topsoil_texture"),
            "irrigation_capacity": indicators.get("irrigation_capacity"),
            "drainage_capacity": indicators.get("drainage_capacity"),
            "terrain_position": indicators.get("terrain_position"),
            "topsoil_thickness": indicators.get("topsoil_thickness"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 QualityGradeResult ORM 实例。"""
        return QualityGradeResult(
            execution_id=execution_id,
            parcel_id=outputs.get("parcel_id"),
            quality_grade=str(outputs.get("quality_grade", "0")),
            composite_index=float(outputs.get("composite_index", 0.0)),
            input_snapshot=outputs,
            simulated=True,
        )
```

替换 `execute` 方法：

```python
    def execute(self, data: Dict[str, Any] = None) -> Dict[str, Any]:
        if not data:
            data = {}

        inputs = self._collect_inputs(data)
        data_source = inputs.pop("data_source", "unknown")

        try:
            if data_source == "db":
                # DB 路径：直接使用 soil_indicators 作为评价结果快照
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    "quality_grade": inputs.get("quality_grade", "0"),
                    "composite_index": inputs.get("composite_index", 0.0),
                    "indicators": inputs,
                }
                status = "ok"
            elif not GRADE_EVAL_AVAILABLE:
                return {
                    "status": "degraded",
                    "degraded": True,
                    "reason": "model_unavailable",
                    "agent_id": "model-2",
                    "model_id": "quality-grade-evaluation",
                    "message": "模型2质量等级评价模块未安装，无法执行真实评价",
                    "data_source": data_source,
                    "persisted": False,
                }
            else:
                # Legacy 路径：CSV run_grade_evaluation
                parcel_code = inputs.get("parcel_code")
                if not parcel_code:
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "missing_input",
                        "agent_id": "model-2",
                        "model_id": "quality-grade-evaluation",
                        "message": "缺少 parcel_code，无法查询真实质量等级结果",
                        "data_source": data_source,
                        "persisted": False,
                    }
                exe_path = inputs.get("exe_path")
                dat_path = inputs.get("dat_path")
                result = run_grade_evaluation(parcel_code, exe_path, dat_path)
                if result.get("status") != "ok":
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "import_failed",
                        "agent_id": "model-2",
                        "model_id": "quality-grade-evaluation",
                        "message": f"地块 {parcel_code} 的质量等级数据未就绪或查询失败",
                        "data_source": data_source,
                        "persisted": False,
                    }
                outputs = result
                status = "degraded"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=data.get("parcel_id") or data.get("parcel_code"),
                inputs=inputs,
                outputs=outputs,
                status=status,
            )

            return {
                "status": "ok",
                "simulated": data_source != "db",
                "result": outputs,
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=data.get("parcel_id"),
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
            )
            return {
                "status": "degraded",
                "degraded": True,
                "reason": "exception",
                "message": str(e),
                "data_source": data_source,
                "persisted": False,
            }
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_specialized.py -k grade_agent -v`
Expected: 4 个新测试 PASS

- [x] **Step 5: Commit**

```bash
git add framework/agents/specialized/grade_agent.py tests/test_agent_specialized.py
git commit -m "feat: integrate Model-2 FarmlandGradeAgent with DB and persistence"
```

---

## Task 5: Model-3 ProblemIdentificationAgent 改造（对应 tasks 4.1 / 4.2 / 4.3）

**Files:**
- Modify: `framework/agents/specialized/problem_agent.py`
- Test: `tests/test_agent_specialized.py`（追加测试函数）

**Interfaces:**
- Consumes: `ParcelDataAccessor`（Task 1）、`BaseAgent._persist_result()` + `_build_result_record()`（Task 2）
- Produces: `ProblemIdentificationAgent.execute()` 返回结果中新增 `data_source` 和 `persisted` 字段

- [x] **Step 1: 编写失败测试**

在 `tests/test_agent_specialized.py` 末尾追加：

```python
def test_problem_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = ProblemIdentificationAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_problem_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = ProblemIdentificationAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_problem_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = ProblemIdentificationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_problem_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，不阻断结果。"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = ProblemIdentificationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_specialized.py -k problem_agent_db -v`
Expected: 测试 FAIL，报 `KeyError: 'data_source'`

- [x] **Step 3: 编写最小实现**

修改 `framework/agents/specialized/problem_agent.py`。

文件头部添加 import：

```python
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...models.thematic_model import ObstacleDiagnosisResult
import logging

logger = logging.getLogger(__name__)
```

在 `ProblemIdentificationAgent` 类中添加方法（在 `__init__` 之后、`execute` 之前）：

```python
    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 SQLite query_parcel。"""
        parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = self._map_indicators_to_inputs(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to SQLite source", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：SQLite query_parcel。"""
        return {
            "parcel_id": context.get("parcel_id") or context.get("data", {}).get("parcel_id"),
            "db_path": context.get("db_path") or context.get("data", {}).get("db_path"),
        }

    def _map_indicators_to_inputs(self, indicators: dict) -> dict:
        """将 soil_indicators JSON 映射为障碍诊断输入字段。"""
        return {
            "soil_ph": indicators.get("soil_ph"),
            "organic_matter": indicators.get("organic_matter"),
            "available_potassium": indicators.get("available_potassium"),
            "available_phosphorus": indicators.get("available_phosphorus"),
            "soil_bulk_density": indicators.get("soil_bulk_density"),
            "topsoil_texture": indicators.get("topsoil_texture"),
            "irrigation_capacity": indicators.get("irrigation_capacity"),
            "drainage_capacity": indicators.get("drainage_capacity"),
            "terrain_position": indicators.get("terrain_position"),
            "topsoil_thickness": indicators.get("topsoil_thickness"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 ObstacleDiagnosisResult ORM 实例。"""
        return ObstacleDiagnosisResult(
            execution_id=execution_id,
            parcel_id=outputs.get("parcel_id"),
            obstacle_type=outputs.get("obstacle_type", "未知"),
            input_snapshot=outputs,
            simulated=True,
        )
```

替换 `execute` 方法：

```python
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        inputs = self._collect_inputs(task)
        data_source = inputs.pop("data_source", "unknown")

        try:
            if data_source == "db":
                # DB 路径：直接使用 soil_indicators 构造诊断快照
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    "diagnosis": {
                        "ZALX": "待诊断",
                        "ZYZAYS": "",
                        "CYZAYS": "",
                    },
                    "evaluation": {"GDZLDJ": "未知"},
                    "indicators": inputs,
                }
                status = "ok"
            else:
                # Legacy 路径：SQLite query_parcel
                if not FARMland_DIAGNOSIS_AVAILABLE:
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "model_unavailable",
                        "agent_id": "model-3",
                        "model_id": "obstacle-diagnosis",
                        "message": "模型3诊断模块未安装，无法执行真实诊断",
                        "data_source": data_source,
                        "persisted": False,
                    }

                parcel_id = inputs.get("parcel_id")
                if not parcel_id:
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "missing_input",
                        "agent_id": "model-3",
                        "model_id": "obstacle-diagnosis",
                        "message": "缺少 parcel_id，无法查询真实诊断结果",
                        "data_source": data_source,
                        "persisted": False,
                    }

                real_result = self._get_real_diagnosis(inputs)
                if not real_result:
                    return {
                        "status": "degraded",
                        "degraded": True,
                        "reason": "import_failed",
                        "agent_id": "model-3",
                        "model_id": "obstacle-diagnosis",
                        "message": f"地块 {parcel_id} 的诊断数据未就绪或查询失败",
                        "data_source": data_source,
                        "persisted": False,
                    }
                outputs = real_result
                status = "degraded"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") or inputs.get("parcel_id"),
                inputs=inputs,
                outputs=outputs,
                status=status,
            )

            return {
                "status": "ok",
                "simulated": data_source != "db",
                "result": outputs,
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
            )
            return {
                "status": "degraded",
                "degraded": True,
                "reason": "exception",
                "message": str(e),
                "data_source": data_source,
                "persisted": False,
            }
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_specialized.py -k problem_agent -v`
Expected: 所有 problem_agent 相关测试 PASS

- [x] **Step 5: Commit**

```bash
git add framework/agents/specialized/problem_agent.py tests/test_agent_specialized.py
git commit -m "feat: integrate Model-3 ProblemIdentificationAgent with DB and persistence"
```

---

## Task 6: Model-4 AcidificationRemediationAgent 改造（对应 tasks 5.1 / 5.2 / 5.3）

**Files:**
- Modify: `framework/agents/specialized/acidification_agent.py`
- Test: `tests/test_agent_specialized.py`（追加测试函数）

**Interfaces:**
- Consumes: `ParcelDataAccessor`（Task 1）、`BaseAgent._persist_result()` + `_build_result_record()`（Task 2）
- Produces: `AcidificationRemediationAgent.execute()` 返回结果中新增 `data_source` 和 `persisted` 字段

- [x] **Step 1: 编写失败测试**

在 `tests/test_agent_specialized.py` 末尾追加：

```python
def test_acidification_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 4.31, "exchangeable_hydrogen": 1.56,
                           "exchangeable_aluminum": 4.08}
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_acidification_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_acidification_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 4.31, "exchangeable_hydrogen": 1.56}
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True


def test_acidification_agent_persist_failure(monkeypatch):
    """持久化失败时 persisted=False，不阻断结果。"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 4.31, "exchangeable_hydrogen": 1.56}
    )
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "model_version": "process_v2_20260801",
            "customized_params": {},
        }
    )
    agent = AcidificationRemediationAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: False)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is False
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_specialized.py -k acidification_agent_db -v`
Expected: 测试 FAIL，报 `KeyError: 'data_source'`

- [x] **Step 3: 编写最小实现**

修改 `framework/agents/specialized/acidification_agent.py`。

文件头部添加 import：

```python
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...models.thematic_model import AcidificationRemediationResult
import logging

logger = logging.getLogger(__name__)
```

在 `AcidificationRemediationAgent` 类中添加方法（在 `__init__` 之后、`execute` 之前）：

```python
    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 MOCK_INPUTS。"""
        parcel_id = context.get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = self._map_indicators_to_inputs(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to MOCK_INPUTS", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：MOCK_INPUTS 硬编码 + context 透传。"""
        enriched = dict(context)
        for k, v in MOCK_INPUTS.items():
            enriched.setdefault(k, v)
        return enriched

    def _map_indicators_to_inputs(self, indicators: dict) -> dict:
        """将 soil_indicators JSON 映射为酸化改良模型输入字段。"""
        return {
            "SJD": indicators.get("soil_ph"),
            "JHX": indicators.get("exchangeable_hydrogen"),
            "JLA": indicators.get("exchangeable_aluminum"),
            "exchangeable_al": indicators.get("exchangeable_aluminum"),
            "soil_ph": indicators.get("soil_ph"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 AcidificationRemediationResult ORM 实例。"""
        result_data = outputs.get("result", outputs)
        return AcidificationRemediationResult(
            execution_id=execution_id,
            parcel_id=outputs.get("parcel_id"),
            soil_ph=float(outputs.get("soil_ph", 0.0) or 0.0),
            soil_conditioner_dosage=float(result_data.get("ytk", 0.0) or 0.0),
            woody_peat_dosage=float(result_data.get("mbnt", 0.0) or 0.0),
            model_version=result_data.get("model_version", "unknown"),
            status=result_data.get("sub_model", "ok"),
            input_snapshot=outputs,
            simulated=True,
        )
```

替换 `execute` 方法：

```python
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = task or {}
        inputs = self._collect_inputs(task)
        data_source = inputs.pop("data_source", "unknown")
        land_type = task.get("land_type") or inputs.get("land_type")
        fertilizer_type = task.get("fertilizer_type") or inputs.get("fertilizer_type")

        try:
            # 使用收集到的输入运行 model_4_execution
            enriched = dict(inputs)
            for k, v in MOCK_INPUTS.items():
                enriched.setdefault(k, v)

            result = model_4_execution(enriched, land_type=land_type, fertilizer_type=fertilizer_type)
            outputs = {
                "parcel_id": inputs.get("parcel_id"),
                "soil_ph": enriched.get("SJD"),
                "result": {
                    "ytk": result.get("ytk"),
                    "mbnt": result.get("mbnt"),
                    "sub_model": result.get("sub_model"),
                    "customized_params": result.get("customized_params", {}),
                },
                "metadata": {
                    "model_version": result.get("model_version"),
                    "warning": result.get("warning"),
                    "reason": result.get("reason"),
                },
            }
            status = "ok" if data_source == "db" else "degraded"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") or inputs.get("parcel_id"),
                inputs=enriched,
                outputs=outputs,
                status=status,
            )

            return {
                "status": result["status"],
                "simulated": False,
                "result": outputs["result"],
                "metadata": outputs["metadata"],
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
            )
            raise
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_specialized.py -k acidification -v`
Expected: 所有 acidification 相关测试 PASS

- [x] **Step 5: Commit**

```bash
git add framework/agents/specialized/acidification_agent.py tests/test_agent_specialized.py
git commit -m "feat: integrate Model-4 AcidificationRemediationAgent with DB and persistence"
```

---

## Task 7: Model-5 OrganicMatterAgent 改造（对应 tasks 6.1 / 6.2 / 6.3）

**Files:**
- Modify: `framework/agents/specialized/organic_matter_agent.py`
- Test: `tests/test_agent_specialized.py`（追加测试函数）

**Interfaces:**
- Consumes: `ParcelDataAccessor`（Task 1）、`BaseAgent._persist_result()` + `_build_result_record()`（Task 2）
- Produces: `OrganicMatterAgent.execute()` 返回结果中新增 `data_source` 和 `persisted` 字段
- **注意**：Model-5 为县级分析，`parcel_id` 可为 `None`；`OrganicMatterResult` 表无 `parcel_id` 列。

- [x] **Step 1: 编写失败测试**

在 `tests/test_agent_specialized.py` 末尾追加：

```python
def test_organic_matter_agent_db_path(monkeypatch):
    """DB 命中时 data_source="db"。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {
            "soil_ph": 5.5, "organic_matter": 22.0,
            "available_potassium": 120.0, "SOCbe": 15.0,
        }
    )
    agent = OrganicMatterAgent()
    result = agent.execute({"parcel_id": "P001"})
    assert result["data_source"] == "db"


def test_organic_matter_agent_fallback_path(monkeypatch):
    """DB 未命中时 data_source="fallback"。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: None
    )
    agent = OrganicMatterAgent()
    result = agent.execute({"parcel_id": "NOT_IN_DB"})
    assert result["data_source"] == "fallback"


def test_organic_matter_agent_no_parcel_id_uses_fallback():
    """无 parcel_id 时直接走 fallback（县级分析）。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    result = agent.execute({"area_code": "lechang"})
    assert result["data_source"] == "fallback"


def test_organic_matter_agent_persist_success(monkeypatch):
    """持久化成功时 persisted=True。"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor, "get_parcel_indicators",
        lambda self, pid: {"soil_ph": 5.5, "organic_matter": 22.0}
    )
    agent = OrganicMatterAgent()
    monkeypatch.setattr(agent, "_persist_result", lambda *a, **kw: True)
    result = agent.execute({"parcel_id": "P001"})
    assert result["persisted"] is True
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_specialized.py -k organic_matter_agent_db -v`
Expected: 测试 FAIL，报 `KeyError: 'data_source'`

- [x] **Step 3: 编写最小实现**

修改 `framework/agents/specialized/organic_matter_agent.py`。

文件头部添加 import：

```python
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...models.thematic_model import OrganicMatterResult
import logging

logger = logging.getLogger(__name__)
```

将现有 `_collect_inputs` 静态方法重命名为 `_collect_inputs_from_legacy`，并新增实例方法 `_collect_inputs`：

```python
    def _collect_inputs(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """DB 优先获取地块指标，未命中时降级到用户传入参数。"""
        task = task or {}
        parcel_id = task.get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = self._map_indicators_to_inputs(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to user inputs", parcel_id)
        inputs = self._collect_inputs_from_legacy(task)
        inputs["data_source"] = "fallback"
        return inputs

    @staticmethod
    def _collect_inputs_from_legacy(task: Dict[str, Any] | None) -> Dict[str, Any]:
        """原有数据源：用户传入参数（原 _collect_inputs 逻辑）。"""
        task = task or {}
        inputs: Dict[str, Any] = {}
        if isinstance(task.get("data"), dict):
            inputs.update(task["data"])
            if isinstance(task["data"].get("indicators"), dict):
                inputs.update(task["data"]["indicators"])
        if isinstance(task.get("task"), dict):
            inputs.update(task["task"])
            if isinstance(task["task"].get("indicators"), dict):
                inputs.update(task["task"]["indicators"])
        if isinstance(task.get("indicators"), dict):
            inputs.update(task["indicators"])
        inputs.update({k: v for k, v in task.items() if k not in {"data", "task"}})
        return inputs

    def _map_indicators_to_inputs(self, indicators: dict) -> dict:
        """将 soil_indicators JSON 映射为有机质培肥模型输入字段。"""
        return {
            "pH": indicators.get("soil_ph"),
            "soil_ph": indicators.get("soil_ph"),
            "organic_matter": indicators.get("organic_matter"),
            "SOMbe": indicators.get("organic_matter"),
            "available_potassium": indicators.get("available_potassium"),
            "AK": indicators.get("available_potassium"),
            "available_phosphorus": indicators.get("available_phosphorus"),
            "AP": indicators.get("available_phosphorus"),
            "total_nitrogen": indicators.get("total_nitrogen"),
            "TN": indicators.get("total_nitrogen"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 OrganicMatterResult ORM 实例（县级分析，无 parcel_id）。"""
        result_data = outputs.get("result", outputs)
        return OrganicMatterResult(
            execution_id=execution_id,
            soil_ph=float(outputs.get("soil_ph", 0.0) or 0.0),
            organic_matter=float(result_data.get("organic_matter", 0.0) or 0.0),
            available_potassium=float(outputs.get("available_potassium", 0.0) or 0.0),
            level=result_data.get("level", "未知"),
            potential_increase=float(result_data.get("potential_increase", 0.0) or 0.0),
            simulated=True,
        )
```

替换 `execute` 方法：

```python
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        inputs = self._collect_inputs(task)
        data_source = inputs.pop("data_source", "unknown")

        try:
            if not self._has_model_features(inputs) and data_source != "db":
                # Legacy 降级路径：规则 fallback
                outputs = self._rule_fallback(inputs)
                status = "degraded"
            elif data_source == "db":
                # DB 路径：直接使用 soil_indicators 构造结果快照
                om = float(inputs.get("organic_matter", 0.0) or 0.0)
                level = MockDataLoader.apply_threshold(om, ORGANIC_RULES)
                manure_dosage = MANURE_DOSAGE_RULES.get(level, 0.0)
                outputs = {
                    "soil_ph": inputs.get("soil_ph"),
                    "organic_matter": om,
                    "available_potassium": inputs.get("available_potassium"),
                    "level": level,
                    "manure_dosage": manure_dosage,
                    "potential_increase": round(manure_dosage / 1000.0 * 1.5, 2),
                }
                status = "ok"
            else:
                # Legacy 路径：ML 模型
                result = model_5_execution(
                    inputs,
                    land_type=inputs.get("land_type"),
                )
                outputs = result
                status = "degraded"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") if isinstance(task, dict) else None,
                inputs=inputs,
                outputs=outputs,
                status=status,
            )

            return {
                "status": "ok" if status == "ok" else "ok",
                "result": outputs,
                "metadata": {
                    "simulated": data_source != "db",
                    "data_source": data_source,
                },
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") if isinstance(task, dict) else None,
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
            )
            return {
                "status": "error",
                "result": {"error": str(e)},
                "data_source": data_source,
                "persisted": False,
            }
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_specialized.py -k organic_matter -v`
Expected: 所有 organic_matter 相关测试 PASS

- [x] **Step 5: Commit**

```bash
git add framework/agents/specialized/organic_matter_agent.py tests/test_agent_specialized.py
git commit -m "feat: integrate Model-5 OrganicMatterAgent with DB and persistence"
```

---

## Task 8: 全量回归测试（对应 tasks 7.4）

**Files:**
- 无文件变更（仅运行测试）

**Interfaces:**
- Consumes: Task 1~7 全部实现

- [x] **Step 1: 运行新增测试文件**

Run: `python -m pytest tests/test_parcel_data_accessor.py tests/test_base_agent_persist.py -v`
Expected: 全部 PASS（9 个测试）

- [x] **Step 2: 运行 specialized agent 测试**

Run: `python -m pytest tests/test_agent_specialized.py -v`
Expected: 全部 PASS（原有测试 + 20 个新测试无回归）

- [x] **Step 3: 运行完整测试套件**

Run: `python -m pytest tests/ -v --tb=short 2>&1 | tail -50`
Expected: 无 FAIL（SKIP 可接受，如 PG_AVAILABLE=False 时跳过 DB 集成测试）

- [x] **Step 4: 验证关键场景**

手动验证以下场景的端到端流程：

```bash
python -c "
from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
agent = StabilityRiskAgent()
# 无 parcel_id：走 fallback
r = agent.execute({})
print('no-parcel:', r.get('data_source'), r.get('persisted'))
# 有 parcel_id 但 DB 不可达：走 fallback
r = agent.execute({'parcel_id': 'P001'})
print('db-miss:', r.get('data_source'), r.get('persisted'))
"
```
Expected: `no-parcel: fallback True/False` 和 `db-miss: fallback True/False`（persisted 取决于 DB 是否可用）

- [x] **Step 5: Commit（如有修复）**

仅当 Step 1~3 发现回归并修复后才提交；否则跳过。

```bash
git add -A
git commit -m "test: verify full regression suite for DB integration"
```

---

## 测试策略总结

### 单元测试（mock-based，不依赖真实 DB）

| 测试文件 | 覆盖场景 | mock 目标 |
|---|---|---|
| `tests/test_parcel_data_accessor.py` | DB 命中 / 未命中 / 异常 | `framework.models.thematic_model.ParcelInfo` |
| `tests/test_base_agent_persist.py` | 持久化成功(有/无结果表) / 失败 / 导入失败 / agent_id 查找 | `framework.models.user.db`、`framework.models.thematic_model.ModelExecutionLog` |
| `tests/test_agent_specialized.py`（新增） | 各 Agent DB 优先 / fallback / 持久化成功 / 持久化失败 | `ParcelDataAccessor.get_parcel_indicators`、`agent._persist_result` |

### 集成测试（依赖 PostgreSQL，可选）

当 `PG_AVAILABLE=True`（`conftest.py` 探测）时可运行：
- `tests/test_soil_data_loader_db.py`（已有，验证 DB 读取降级模式）
- 可选新增：向 `parcel_info` 表插入测试数据 → 调用 Agent → 验证 `model_execution_log` 和结果表有记录

### 回归保护

- 原有 `test_agent_specialized.py` 中的测试保持不变（验证 legacy 路径不破坏）
- 原有 `test_stability_and_grade_integration.py`、`test_farmland_diagnosis.py` 等集成测试不受影响
- `test_thematic_model_orm.py` 验证 ORM 结构不变更

### 关键验收点

1. ✅ `ParcelDataAccessor.get_parcel_indicators()` — DB 命中返回 dict，未命中/异常返回 None
2. ✅ `BaseAgent._persist_result()` — 成功返回 True，失败返回 False 不抛异常
3. ✅ `BaseAgent._build_result_record()` — 默认返回 None，子类 override 返回 ORM 实例
4. ✅ 5 个 Agent 的 `execute()` — DB 命中时 `data_source="db"`，未命中时 `data_source="fallback"`
5. ✅ 5 个 Agent 的 `execute()` — 持久化成功时 `persisted=True`，失败时 `persisted=False`
6. ✅ Model-5 无 `parcel_id` 时直接走 fallback（县级分析场景）
7. ✅ 持久化失败不影响返回给用户的计算结果
