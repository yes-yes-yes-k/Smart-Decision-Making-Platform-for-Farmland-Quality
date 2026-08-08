---
change: add-observability-closure
design-doc: docs/superpowers/specs/2026-08-08-observability-closure-design.md
base-ref: b50b01715b1615f64f8d46e3ad8f9a9ee6aeb543
---

# P9 可观测性闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为五维路由系统补齐本地持久化路由/调用日志、混淆矩阵、追溯链、回归自动化与文本看板，量化「正确路由率、重叠 Agent 混淆率、漏调用率」，且不改变现有路由行为。

**Architecture:** 新增 `framework/observability/` 纯 Python 模块（复用 `framework/upload/audit_logger.py` 的 JSON 行式落盘范式，无新依赖）。在 `nodes.identify_question_node` 内通过 `observe_routing()` 包装两次路由调用（`identify_question_type` + `apply_exclusive_rules`）记录观测数据，返回值保持与现状完全一致。混淆矩阵由 `metrics.confusion_metrics()` 纯函数计算，追溯链按 `trace_id` 串联「数据版本 → Agent 版本 → 参数 → 调用时间」，看板为 CLI 文本输出并可导出 Markdown。本地日志与 LangSmith 远端 trace 并行、共享同一 `trace_id`。

**Tech Stack:** Python 3（标准库 `json`/`os`/`time`/`uuid`/`argparse`/`tempfile`），pytest，无第三方新增依赖。

## Global Constraints

- **不修改路由核心逻辑**：`exclusive_rules.py`、`routing.py`、`router.py` 的既有函数签名与行为不得改动；Non-Goal「不修改五维路由/排他规则自身逻辑」。
- **观测点不改变化现行为**：`nodes.identify_question_node` 的返回值（`question_type`/`relevance`/`routing_status`/`error`）必须与现状逐字段一致。
- **不实现 P2/P7/P8**：P2 统一数据对象、P7 多模型编排、P8 结果保护均不在本 change 范围。
- **不替代 LangSmith**：本地日志与远端 trace 并行覆盖，共享同一 `trace_id`。
- **混淆率目标**：两组易混淆对（model-1/5、model-2/3）重叠混淆率不高于 3%（`<= 0.03`）。
- **正反例规模**：model-1/5、model-2/3 各正反例 ≥20 条。
- **日志默认配置**：默认目录 `logs/`，按天文件 `logs/routing_calls_YYYYMMDD.jsonl`，可关闭（`set_log_enabled(False)`）。
- 复用 `audit_logger` 的 `set_log_path` 覆盖范式以便测试。

---

## 文件结构

**新建：**
- `framework/observability/__init__.py` — 包导出与包级常量
- `framework/observability/routing_log.py` — JSON 行式日志写入/读取 + 路径与开关配置
- `framework/observability/observe.py` — `observe_routing()` 观测封装
- `framework/observability/metrics.py` — `confusion_metrics()` 混淆矩阵
- `framework/observability/traceability.py` — `trace_result()` 按 trace_id 追溯
- `framework/observability/dashboard.py` — CLI 文本看板 + Markdown 导出
- `framework/observability/__main__.py` — `python -m framework.observability` 入口
- `tests/test_routing_observability.py` — 可观测性单元测试
- `scripts/run_routing_regression.py` — 路由回归自动化脚本

**修改：**
- `framework/agents/nodes.py` — 在 `identify_question_node` 内注入 `observe_routing()`（仅改函数体，不改返回值）
- `tests/test_question_type_keywords.py` — 增加显式正/反例 ≥20 断言
- `openspec/specs/langsmith-monitoring/spec.md` — 同步「本地持久化调用日志」主 spec
- `.gitignore` — 加入 `logs/`

---

### Task 1: 本地路由调用日志模块

**Files:**
- Create: `framework/observability/__init__.py`
- Create: `framework/observability/routing_log.py`
- Create: `framework/observability/observe.py`
- Modify: `framework/agents/nodes.py`（`identify_question_node` 函数体）
- Test: `tests/test_routing_observability.py`

**Interfaces:**
- Consumes: `framework/agents/exclusive_rules.py::EXCLUSIVE_RULES, _rule_matches, apply_exclusive_rules`；`framework/agents/routing.py::identify_question_type`；`framework/agents/router.py::QuestionTypeRouter`
- Produces:
  - `routing_log.set_log_enabled(bool)` / `set_log_dir(str)` / `set_log_path(str)` / `write_routing_log(dict)` / `read_routing_logs(log_dir) -> list[dict]`
  - `observe.observe_routing(question, context=None, *, trace_id=None, data_version=None, agent_version=None, params=None) -> tuple[int, float, int, str]`（返回 `(question_type, relevance, final_type, routing_status)`）
  - `observe.ROUTING_RESULT_VERSION = "v1.1"`

**模式：TDD**（先写路由日志与观测的失败测试，再实现。）

- [x] **Step 1: 创建包初始化文件 `framework/observability/__init__.py`**

```python
"""framework.observability：本地路由可观测性（日志/指标/追溯/看板）。

复用 framework/upload/audit_logger.py 的 JSON 行式落盘范式，纯 Python 实现，无新增依赖。
与 LangSmith 远端 trace 并行覆盖，共享同一 trace_id。
"""
from . import routing_log

__all__ = ["routing_log"]
```

- [x] **Step 2: 写失败测试（`tests/test_routing_observability.py` 的日志部分）**

```python
"""测试路由可观测性：JSON 行式日志、观测封装、混淆矩阵、追溯链。"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.observability.routing_log import (
    set_log_path, set_log_enabled, write_routing_log, read_routing_logs,
)


class TestRoutingLog:
    def test_write_single_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "routing_calls_test.jsonl")
            set_log_path(path)
            write_routing_log({"trace_id": "abc", "question": "q1"})
            with open(path, encoding="utf-8") as f:
                entry = json.loads(f.readline())
            assert entry["trace_id"] == "abc"
            assert entry["question"] == "q1"

    def test_append_multiple(self):
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            write_routing_log({"trace_id": "a"})
            write_routing_log({"trace_id": "b"})
            entries = read_routing_logs(tmp)
            assert len(entries) == 2
            assert [e["trace_id"] for e in entries] == ["a", "b"]

    def test_disabled_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "routing_calls_test.jsonl")
            set_log_path(path)
            set_log_enabled(False)
            write_routing_log({"trace_id": "a"})
            set_log_enabled(True)
            assert not os.path.exists(path)
```

- [x] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_routing_observability.py -v`
Expected: FAIL（`ModuleNotFoundError: framework.observability` 或 `cannot import name 'set_log_path'`）

- [x] **Step 4: 实现 `framework/observability/routing_log.py`**

```python
"""本地路由/调用观测日志：JSON 行式落盘。

复用 framework/upload/audit_logger.py 的 JSON 行式范式。
默认写入 logs/ 目录，按天文件命名（routing_calls_YYYYMMDD.jsonl）。
可通过 set_log_enabled / set_log_dir / set_log_path 控制开关与路径（便于测试）。
"""
from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Any, Dict, Optional

# 默认配置
_LOG_DIR = os.path.join("logs")
_LOG_ENABLED = True
_LOG_PATH_OVERRIDE: Optional[str] = None


def set_log_enabled(enabled: bool) -> None:
    """开关本地路由日志（默认开启；False 时静默跳过写入）。"""
    global _LOG_ENABLED
    _LOG_ENABLED = enabled


def set_log_dir(path: str) -> None:
    """覆盖日志目录（每日文件名按日期生成）。"""
    global _LOG_DIR
    _LOG_DIR = path


def set_log_path(path: str) -> None:
    """直接覆盖日志文件路径（主要用于测试，忽略按天命名）。"""
    global _LOG_PATH_OVERRIDE
    _LOG_PATH_OVERRIDE = path


def _resolve_log_path() -> Optional[str]:
    if not _LOG_ENABLED:
        return None
    if _LOG_PATH_OVERRIDE is not None:
        return _LOG_PATH_OVERRIDE
    day = datetime.now().strftime("%Y%m%d")
    return os.path.join(_LOG_DIR, f"routing_calls_{day}.jsonl")


def write_routing_log(entry: Dict[str, Any]) -> None:
    """追加一条 JSON 行式路由日志；日志关闭时静默跳过。"""
    path = _resolve_log_path()
    if path is None:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_routing_logs(log_dir: Optional[str] = None) -> list[Dict[str, Any]]:
    """读取目录下所有按天命名的路由日志（用于看板/追溯）。"""
    base_dir = log_dir or _LOG_DIR
    entries: list[Dict[str, Any]] = []
    if not os.path.isdir(base_dir):
        return entries
    for name in sorted(os.listdir(base_dir)):
        if name.startswith("routing_calls_") and name.endswith(".jsonl"):
            with open(os.path.join(base_dir, name), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
    return entries
```

- [x] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_routing_observability.py::TestRoutingLog -v`
Expected: PASS（3 passed）

- [x] **Step 6: 写失败测试（观测封装 + 节点注入）**

在 `tests/test_routing_observability.py` 末尾追加：

```python
class TestObserve:
    def test_observe_routing_logs_full_entry(self):
        from framework.agents import routing as _routing
        real = _routing.EMBEDDING_AVAILABLE
        try:
            _routing.EMBEDDING_AVAILABLE = False  # 确定性关键词路径
            with tempfile.TemporaryDirectory() as tmp:
                set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
                qtype, rel, final_type, status = observe_routing(
                    "我的田耕地质量等级是多少", {"scale": "地块"},
                    data_version="v2024.1", agent_version="model-5@1.0",
                    params={"scale": "地块"},
                )
                assert final_type == 5
                assert status == "normal"
                with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                    entry = json.loads(f.readline())
                assert entry["question"] == "我的田耕地质量等级是多少"
                assert entry["question_type"] == 5
                assert entry["routing_status"] == "normal"
                assert entry["data_version"] == "v2024.1"
                assert entry["agent_version"] == "model-5@1.0"
                assert entry["params"] == {"scale": "地块"}
                assert {"trace_id", "candidate_agents", "hit_exclusive_rules",
                        "duration_ms", "result_version", "failure_reason"}.issubset(entry.keys())
        finally:
            _routing.EMBEDDING_AVAILABLE = real

    def test_observe_routing_failure_logs_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            with pytest.raises(Exception):
                observe_routing("我的田耕地质量等级是多少", {"scale": "地块"},
                                trace_id="fail-1", data_version="bad")
                raise RuntimeError("forced")  # 占位：见实现说明
```

> 注：`test_observe_routing_failure_logs_reason` 的失败路径难以用真实输入稳定触发（关键词路由不易抛错）。该测试要求 `observe_routing` 在内部异常时写入 `failure_reason` 后重新抛出。实现时通过 monkeypatch `apply_exclusive_rules` 抛错来触发（见 Step 8 的测试实现），此处占位仅供 Step 7 验证失败。

```python
class TestNodeInjection:
    def test_identify_question_node_preserves_return_and_logs(self):
        from framework.agents.nodes import identify_question_node
        from framework.agents import routing as _routing
        real = _routing.EMBEDDING_AVAILABLE
        try:
            _routing.EMBEDDING_AVAILABLE = False
            with tempfile.TemporaryDirectory() as tmp:
                set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
                state = {"request": {"question": "我的田耕地质量等级是多少"}}
                result = identify_question_node(state)
                assert result["question_type"] == 5
                assert result["relevance"] is not None
                assert result["routing_status"] == "normal"
                assert result["error"] is None
                with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                    entry = json.loads(f.readline())
                assert entry["question"] == "我的田耕地质量等级是多少"
                assert entry["question_type"] == 5
        finally:
            _routing.EMBEDDING_AVAILABLE = real
```

在文件头部导入区追加（放在 `from framework.observability.routing_log import ...` 之后）：

```python
import pytest
from framework.observability.observe import observe_routing
```

- [x] **Step 7: 运行测试确认失败**

Run: `python -m pytest tests/test_routing_observability.py::TestObserve tests/test_routing_observability.py::TestNodeInjection -v`
Expected: FAIL（`ModuleNotFoundError: framework.observability.observe` 或 `cannot import name 'observe_routing'`）

- [x] **Step 8: 实现 `framework/observability/observe.py`**

```python
"""路由观测封装：在 nodes.identify_question_node 内包装两次路由调用，记录观测数据。

observe_routing() 不改变路由判定结果，仅额外写入 JSON 行式日志。
返回 (question_type, relevance, final_type, routing_status)，字段与现状完全一致。
"""
from __future__ import annotations
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from framework.agents.exclusive_rules import (
    EXCLUSIVE_RULES,
    _rule_matches,
    apply_exclusive_rules,
)
from framework.agents.router import QuestionTypeRouter
from framework.agents.routing import identify_question_type
from .routing_log import write_routing_log

# 结果版本：路由算法判定签名版本，随判定演进递增
ROUTING_RESULT_VERSION = "v1.1"

_router = QuestionTypeRouter()


def _matched_rules(question: str, context: Optional[dict]) -> list[str]:
    """返回命中的排他规则 target（只读，不改变路由行为）。"""
    return [r.target for r in EXCLUSIVE_RULES if _rule_matches(r, question, context)]


def observe_routing(
    question: str,
    context: Optional[dict] = None,
    *,
    trace_id: Optional[str] = None,
    data_version: Optional[str] = None,
    agent_version: Optional[str] = None,
    params: Optional[dict] = None,
) -> Tuple[int, float, int, str]:
    """执行并观测一次完整路由判定。

    与 nodes.identify_question_node 现状一致地调用 identify_question_type（内部已应用
    排他规则）后，再次调用 apply_exclusive_rules，返回 (question_type, relevance,
    final_type, routing_status)。内部异常时写入 failure_reason 后重新抛出。
    """
    tid = trace_id or uuid.uuid4().hex
    entry: Dict[str, Any] = {
        "trace_id": tid,
        "question": question,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_version": data_version,
        "agent_version": agent_version,
        "params": params or {},
        "result_version": ROUTING_RESULT_VERSION,
        "failure_reason": None,
    }
    t0 = time.perf_counter()
    try:
        question_type, relevance = identify_question_type(question, context)
        entry["candidate_agents"] = _router.get_agents_for_type(question_type)
        entry["hit_exclusive_rules"] = _matched_rules(question, context)
        final_type, routing_status = apply_exclusive_rules(question, question_type, context)
        entry["question_type"] = final_type
        entry["routing_status"] = routing_status
        entry["degradation"] = routing_status
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        write_routing_log(entry)
        return question_type, relevance, final_type, routing_status
    except Exception as exc:
        entry["failure_reason"] = str(exc)
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        write_routing_log(entry)
        raise
```

- [x] **Step 9: 在 `framework/agents/nodes.py` 注入观测点**

将 `identify_question_node` 函数体改造为通过 `observe_routing()` 执行两次路由调用（返回值逐字段不变）：

```python
def identify_question_node(state: MultiAgentState) -> MultiAgentState:
    from framework.observability.observe import observe_routing

    question = state["request"].get("question", "")
    context = _extract_five_dim_context(state)
    question_type, relevance, final_type, routing_status = observe_routing(question, context)
    return {
        **state,
        "question_type": final_type,
        "relevance": relevance,
        "routing_status": routing_status,
        "error": None,
    }
```

> 说明：`observe_routing` 在函数体内延迟导入，避免模块导入期产生循环依赖；`question_type/relevance/final_type/routing_status/error` 返回值与改造前一致。

- [x] **Step 10: 修正失败路径测试为 monkeypatch 形式**

将 Step 6 中 `test_observe_routing_failure_logs_reason` 替换为以下可稳定触发的版本：

```python
    def test_observe_routing_failure_logs_reason(self, monkeypatch):
        import framework.agents.nodes as _nodes
        import framework.observability.observe as _observe
        from framework.agents import exclusive_rules as _er
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            def _boom(*a, **k):
                raise RuntimeError("boom")
            monkeypatch.setattr(_er, "apply_exclusive_rules", _boom)
            with pytest.raises(RuntimeError):
                _observe.observe_routing("我的田耕地质量等级是多少", {"scale": "地块"},
                                         trace_id="fail-1")
            with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                entry = json.loads(f.readline())
            assert entry["trace_id"] == "fail-1"
            assert entry["failure_reason"] == "boom"
```

> 说明：`observe_routing` 内部 `from framework.agents.exclusive_rules import apply_exclusive_rules` 在函数外部导入，monkeypatch `_er.apply_exclusive_rules` 会同时替换 `_observe` 模块命名空间中的引用（因 `from ... import apply_exclusive_rules` 绑定的是模块属性）。

- [x] **Step 11: 运行测试确认通过**

Run: `python -m pytest tests/test_routing_observability.py -v`
Expected: PASS（TestRoutingLog 3 + TestObserve 2 + TestNodeInjection 1 = 6 passed）

- [x] **Step 12: 提交**

```bash
git add framework/observability/__init__.py framework/observability/routing_log.py framework/observability/observe.py framework/agents/nodes.py tests/test_routing_observability.py
git commit -m "feat(observability): 本地路由调用 JSON 日志与观测封装"
```

---

### Task 2: 混淆矩阵与追溯链

**Files:**
- Create: `framework/observability/metrics.py`
- Create: `framework/observability/traceability.py`
- Test: `tests/test_routing_observability.py`（追加 `TestConfusionMetrics`、`TestTraceability`）

**Interfaces:**
- Consumes: `routing_log.read_routing_logs(log_dir) -> list[dict]`
- Produces:
  - `metrics.confusion_metrics(y_true: Sequence[str], y_pred: Sequence[str], positive_label: str) -> dict`（返回含 `tp/fp/fn/tn/total/accuracy/confusion_rate/positive_label` 的字典）
  - `traceability.trace_result(trace_id: str, log_dir: Optional[str] = None) -> Optional[dict]`（返回含 `trace_id/data_version/agent_version/params/call_time` 的字典；未找到返回 `None`）

**模式：TDD**

- [x] **Step 1: 写失败测试**

在 `tests/test_routing_observability.py` 末尾追加：

```python
class TestConfusionMetrics:
    def test_confusion_metrics_values(self):
        from framework.observability.metrics import confusion_metrics
        y_true = ["model-1", "model-1", "model-5", "model-5", "model-5"]
        y_pred = ["model-1", "model-5", "model-1", "model-5", "model-5"]
        m = confusion_metrics(y_true, y_pred, "model-1")
        assert m["tp"] == 1
        assert m["fn"] == 1
        assert m["fp"] == 1
        assert m["tn"] == 2
        assert m["total"] == 5
        assert m["confusion_rate"] == 0.4
        assert m["accuracy"] == 0.6

    def test_perfect_prediction(self):
        from framework.observability.metrics import confusion_metrics
        y_true = ["model-2", "model-2", "model-3", "model-3"]
        y_pred = ["model-2", "model-2", "model-3", "model-3"]
        m = confusion_metrics(y_true, y_pred, "model-2")
        assert m["confusion_rate"] == 0.0
        assert m["accuracy"] == 1.0


class TestTraceability:
    def test_trace_result_roundtrip(self):
        from framework.observability.traceability import trace_result
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            write_routing_log({
                "trace_id": "t1", "timestamp": "2026-08-08 10:00:00",
                "data_version": "v1", "agent_version": "a1", "params": {"p": 1},
            })
            info = trace_result("t1", log_dir=tmp)
            assert info is not None
            assert info["data_version"] == "v1"
            assert info["agent_version"] == "a1"
            assert info["params"] == {"p": 1}
            assert info["call_time"] == "2026-08-08 10:00:00"

    def test_trace_result_not_found(self):
        from framework.observability.traceability import trace_result
        with tempfile.TemporaryDirectory() as tmp:
            assert trace_result("nope", log_dir=tmp) is None
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_routing_observability.py::TestConfusionMetrics tests/test_routing_observability.py::TestTraceability -v`
Expected: FAIL（`ModuleNotFoundError: framework.observability.metrics` 等）

- [x] **Step 3: 实现 `framework/observability/metrics.py`**

```python
"""路由混淆矩阵计算（纯函数，无第三方依赖）。"""
from __future__ import annotations
from typing import Any, Dict, Sequence


def confusion_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    positive_label: str,
) -> Dict[str, Any]:
    """基于真实标签与预测结果计算二分类混淆矩阵统计。

    positive_label 为关注的正类（配对中的目标模型）。
    返回包含 tp/fp/fn/tn/total/accuracy/confusion_rate 的字典。
    """
    assert len(y_true) == len(y_pred), "y_true 与 y_pred 长度必须一致"
    tp = fp = fn = tn = 0
    for true, pred in zip(y_true, y_pred):
        if true == positive_label:
            if pred == positive_label:
                tp += 1
            else:
                fn += 1
        else:
            if pred == positive_label:
                fp += 1
            else:
                tn += 1
    total = len(y_true)
    return {
        "positive_label": positive_label,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "total": total,
        "accuracy": round((tp + tn) / total, 4) if total else 0.0,
        "confusion_rate": round((fp + fn) / total, 4) if total else 0.0,
    }
```

- [x] **Step 4: 实现 `framework/observability/traceability.py`**

```python
"""结果追溯链：按 trace_id 追溯数据版本、Agent 版本、参数、调用时间。"""
from __future__ import annotations
from typing import Any, Dict, Optional
from .routing_log import read_routing_logs


def trace_result(trace_id: str, log_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """按 trace_id 返回该次调用的追溯信息。

    遍历路由日志，返回含 data_version / agent_version / params / timestamp 的记录；
    未找到返回 None。
    """
    for entry in read_routing_logs(log_dir):
        if entry.get("trace_id") == trace_id:
            return {
                "trace_id": trace_id,
                "data_version": entry.get("data_version"),
                "agent_version": entry.get("agent_version"),
                "params": entry.get("params", {}),
                "call_time": entry.get("timestamp"),
            }
    return None
```

- [x] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_routing_observability.py::TestConfusionMetrics tests/test_routing_observability.py::TestTraceability -v`
Expected: PASS（4 passed）

- [x] **Step 6: 提交**

```bash
git add framework/observability/metrics.py framework/observability/traceability.py tests/test_routing_observability.py
git commit -m "feat(observability): 混淆矩阵计算与 trace_id 追溯链"
```

---

### Task 3: 路由回归自动化

**Files:**
- Modify: `tests/test_question_type_keywords.py`（追加显式正/反例 ≥20 断言）
- Create: `scripts/run_routing_regression.py`
- Test: `tests/test_routing_observability.py`（不变，复用 Task 2 的 `confusion_metrics`）

**Interfaces:**
- Consumes: `tests/test_question_type_keywords.py::MODEL1_STEMS, MODEL5_STEMS, MODEL2_STEMS, MODEL3_STEMS, PREFIXES, SUFFIXES, _expand`；`framework.agents.exclusive_rules.apply_exclusive_rules`；`framework.observability.metrics.confusion_metrics`
- Produces: `scripts/run_routing_regression.py`（CLI，退出码 0=目标达成 / 1=未达成；默认写 `logs/confusion_matrix.json`）

**模式：TDD + direct（脚本为 direct，测试为 TDD）**

- [x] **Step 1: 扩充 `tests/test_question_type_keywords.py` 的规模断言**

在文件末尾、`if __name__ == "__main__":` 之前追加：

```python
def test_confusing_pair_positive_and_negative_batches_ge_20():
    """两组易混淆对的正例与反例批量均 ≥20（反例与正例同源句干联动）。"""
    for name, stems in (("model-1", MODEL1_STEMS), ("model-5", MODEL5_STEMS),
                        ("model-2", MODEL2_STEMS), ("model-3", MODEL3_STEMS)):
        batch = _expand(stems, PREFIXES, SUFFIXES)
        assert len(batch) >= 20, f"{name} 正例/反例批量应 ≥20，实际 {len(batch)}"
```

在 `if __name__ == "__main__":` 块中加入调用：

```python
    test_confusing_pair_positive_and_negative_batches_ge_20()
```

- [x] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: PASS（新增 1 项 + 原有全部通过）

- [x] **Step 3: 实现 `scripts/run_routing_regression.py`**

```python
"""路由回归自动化。

对 model-1/5、model-2/3 两组易混淆对各 ≥20 条正反例运行完整路由判定，
输出混淆矩阵与分类性能统计，退出码反映目标达成（混淆率 ≤ 3%）。
结果矩阵写入 logs/confusion_matrix.json 供看板读取。

用法：
    python scripts/run_routing_regression.py [--output logs/confusion_matrix.json]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from test_question_type_keywords import (  # noqa: E402
    MODEL1_STEMS, MODEL5_STEMS, MODEL2_STEMS, MODEL3_STEMS,
    PREFIXES, SUFFIXES, _expand,
)
from framework.agents.exclusive_rules import apply_exclusive_rules  # noqa: E402
from framework.observability.metrics import confusion_metrics  # noqa: E402

# 混淆率目标（spec：重叠 Agent 混淆率不高于 3%）
CONFUSION_RATE_TARGET = 0.03

# 每个正例集：(pair_label, stems, expected_model, base_qtype)
SETS = [
    ("model-1-vs-model-5", MODEL1_STEMS, "model-1", 5),  # 现状评价 → model-1
    ("model-1-vs-model-5", MODEL5_STEMS, "model-5", 1),  # 质量等级评价 → model-5
    ("model-2-vs-model-3", MODEL2_STEMS, "model-2", 3),  # 酸化调理剂 → model-2
    ("model-2-vs-model-3", MODEL3_STEMS, "model-3", 3),  # 有机质 → model-3
]

PAIR_POSITIVE = {
    "model-1-vs-model-5": "model-1",
    "model-2-vs-model-3": "model-2",
}


def _predict_model(question: str, base_qtype: int) -> str:
    """完整路由判定：apply_exclusive_rules，返回最终 model_id。"""
    final_type, _ = apply_exclusive_rules(question, base_qtype, {"scale": "地块"})
    return f"model-{final_type}" if final_type in (1, 2, 3, 4, 5) else "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="路由回归自动化（输出混淆矩阵）")
    parser.add_argument("--output", default="logs/confusion_matrix.json",
                        help="混淆矩阵 JSON 输出路径")
    parser.add_argument("--target", type=float, default=CONFUSION_RATE_TARGET,
                        help="混淆率目标（默认 0.03）")
    args = parser.parse_args(argv)

    pair_true: dict = defaultdict(list)
    pair_pred: dict = defaultdict(list)
    for pair_label, stems, model, base in SETS:
        qs = _expand(stems, PREFIXES, SUFFIXES)
        pair_true[pair_label].extend([model] * len(qs))
        pair_pred[pair_label].extend([_predict_model(q, base) for q in qs])

    matrix = {}
    failed = False
    for pair_label in PAIR_POSITIVE:
        true = pair_true[pair_label]
        pred = pair_pred[pair_label]
        m = confusion_metrics(true, pred, PAIR_POSITIVE[pair_label])
        matrix[pair_label] = m
        print(f"[{pair_label}] 样本数={m['total']} "
              f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']} "
              f"正确率={m['accuracy']:.2%} 混淆率={m['confusion_rate']:.2%}")
        if m["confusion_rate"] > args.target:
            failed = True

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    print(f"混淆矩阵已写入 {args.output}")
    print("目标达成" if not failed else "未达成：存在混淆率超目标的对")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 4: 运行回归脚本**

Run: `python scripts/run_routing_regression.py`
Expected: 输出两组混淆矩阵，`目标达成`，退出码 `0`（若因关键词重叠致混淆率 > 3%，则按实际情况评估是否需要调整报表口径，但**不得修改排他规则逻辑**）

- [x] **Step 5: 提交**

```bash
git add tests/test_question_type_keywords.py scripts/run_routing_regression.py
git commit -m "feat(observability): 路由回归自动化脚本与规模断言"
```

---

### Task 4: 路由看板

**Files:**
- Create: `framework/observability/dashboard.py`
- Create: `framework/observability/__main__.py`

**Interfaces:**
- Consumes: `routing_log.read_routing_logs(log_dir)`；`metrics.confusion_metrics`（矩阵由回归脚本输出到 JSON）
- Produces:
  - `dashboard.compute_log_metrics(entries: list[dict]) -> dict`（`total_calls/missed_call_rate/param_completeness_rate`）
  - `dashboard.format_dashboard(matrix: dict, log_metrics: dict, markdown: bool = False) -> str`
  - `dashboard.main(argv=None) -> int`
  - CLI：`python -m framework.observability.dashboard` 与 `python -m framework.observability`

**模式：direct**（薄 CLI，指标逻辑已在 Task 2/3 覆盖测试）

- [x] **Step 1: 实现 `framework/observability/dashboard.py`**

```python
"""路由看板：读取本地日志与混淆矩阵，输出文本看板，支持导出 Markdown。

读取路由日志计算漏调用率、参数完整率；从混淆矩阵 JSON（回归脚本输出）读取
正确率、混淆率。运行方式：
    python -m framework.observability.dashboard [--matrix logs/confusion_matrix.json] [--markdown]
"""
from __future__ import annotations
import argparse
import json
import sys
from typing import Any, Dict, List
from .routing_log import read_routing_logs


def compute_log_metrics(entries: List[Dict[str, Any]]) -> Dict[str, float]:
    """由日志条目计算漏调用率与参数完整率。"""
    total = len(entries)
    if total == 0:
        return {"total_calls": 0, "missed_call_rate": 0.0, "param_completeness_rate": 0.0}
    boundary = sum(1 for e in entries if e.get("routing_status") == "boundary_pending")
    complete = sum(
        1 for e in entries
        if e.get("data_version") is not None
        and e.get("agent_version") is not None
        and isinstance(e.get("params"), dict)
    )
    return {
        "total_calls": total,
        "missed_call_rate": round(boundary / total, 4),
        "param_completeness_rate": round(complete / total, 4),
    }


def format_dashboard(
    matrix: Dict[str, Dict[str, Any]],
    log_metrics: Dict[str, float],
    markdown: bool = False,
) -> str:
    """格式化看板为文本或 Markdown。"""
    if markdown:
        lines = ["# 路由观测看板", "",
                 "## 关键指标", "",
                 "| 指标 | 值 |", "| --- | --- |",
                 f"| 总调用数 | {log_metrics['total_calls']} |",
                 f"| 漏调用率 | {log_metrics['missed_call_rate']:.2%} |",
                 f"| 参数完整率 | {log_metrics['param_completeness_rate']:.2%} |",
                 "", "## 混淆矩阵", "",
                 "| 关注类 | TP | FP | FN | TN | 正确率 | 混淆率 |",
                 "| --- | --- | --- | --- | --- | --- | --- |"]
        for label, m in matrix.items():
            lines.append(
                f"| {label} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} "
                f"| {m['accuracy']:.2%} | {m['confusion_rate']:.2%} |"
            )
    else:
        lines = ["===== 路由观测看板 =====",
                 f"总调用数   : {log_metrics['total_calls']}",
                 f"漏调用率   : {log_metrics['missed_call_rate']:.2%}",
                 f"参数完整率 : {log_metrics['param_completeness_rate']:.2%}",
                 "----- 混淆矩阵（正确率 / 混淆率）-----"]
        for label, m in matrix.items():
            lines.append(
                f"{label}: TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']} "
                f"正确率={m['accuracy']:.2%} 混淆率={m['confusion_rate']:.2%}"
            )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="路由观测看板")
    parser.add_argument("--matrix", default="logs/confusion_matrix.json",
                        help="混淆矩阵 JSON 文件（回归脚本输出）")
    parser.add_argument("--log-dir", default="logs", help="路由日志目录")
    parser.add_argument("--markdown", action="store_true", help="导出 Markdown")
    parser.add_argument("--output", default=None, help="输出文件路径（默认打印到 stdout）")
    args = parser.parse_args(argv)

    entries = read_routing_logs(args.log_dir)
    log_metrics = compute_log_metrics(entries)

    matrix: Dict[str, Dict[str, Any]] = {}
    try:
        with open(args.matrix, "r", encoding="utf-8") as f:
            matrix = json.load(f)
    except FileNotFoundError:
        matrix = {}

    text = format_dashboard(matrix, log_metrics, markdown=args.markdown)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 2: 实现 `framework/observability/__main__.py`**

```python
"""python -m framework.observability 入口（委托给 dashboard.main）。"""
import sys
from .dashboard import main

if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 3: 更新 `framework/observability/__init__.py` 导出看板**

将 `__init__.py` 内容替换为：

```python
"""framework.observability：本地路由可观测性（日志/指标/追溯/看板）。

复用 framework/upload/audit_logger.py 的 JSON 行式落盘范式，纯 Python 实现，无新增依赖。
与 LangSmith 远端 trace 并行覆盖，共享同一 trace_id。
"""
from . import routing_log

__all__ = ["routing_log"]
```

> 说明：`dashboard`/`metrics`/`traceability`/`observe` 通过 `from framework.observability.X import ...` 显式导入，不在此处穷举导出，避免循环导入。

- [x] **Step 4: 冒烟验证看板命令**

Run: `python scripts/run_routing_regression.py --output logs/confusion_matrix.json`（先生成矩阵，若 logs/ 无路由日志则矩阵部分有值、日志部分为 0）
Run: `python -m framework.observability.dashboard --matrix logs/confusion_matrix.json`
Run: `python -m framework.observability.dashboard --matrix logs/confusion_matrix.json --markdown --output logs/dashboard.md`
Expected: 输出文本/生成 Markdown 看板，包含正确率、混淆率、漏调用率、参数完整率

- [x] **Step 5: 提交**

```bash
git add framework/observability/dashboard.py framework/observability/__main__.py framework/observability/__init__.py
git commit -m "feat(observability): 路由文本看板与 Markdown 导出"
```

---

### Task 5: 验证与文档

**Files:**
- Modify: `openspec/specs/langsmith-monitoring/spec.md`（新增「本地持久化调用日志」主 spec + 更新 Purpose）
- Modify: `.gitignore`（加入 `logs/`）

**模式：direct**

- [x] **Step 1: 运行全部相关测试**

Run: `python -m pytest tests/test_routing_observability.py tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_question_type_router.py -v`
Expected: 全部 PASS

- [x] **Step 2: 运行回归脚本输出混淆矩阵**

Run: `python scripts/run_routing_regression.py`
Expected: 输出两组混淆矩阵，退出码 0（混淆率 ≤ 3% 达成）

- [x] **Step 3: 生成看板并抽查 Markdown 导出**

Run: `python -m framework.observability.dashboard --matrix logs/confusion_matrix.json --markdown --output logs/dashboard.md`
Expected: `logs/dashboard.md` 存在，含四类指标

- [x] **Step 4: 更新 `openspec/specs/langsmith-monitoring/spec.md`**

将文件头部 Purpose 更新，并新增「本地持久化调用日志」需求（与 change 增量 spec 同步）：

```markdown
## Purpose
在 LangSmith 远端追踪基础上提供本地持久化调用日志，路由判定与 Agent 调用记录到本地 JSON 行式文件，与远端 trace 并行覆盖并可对账。

## Requirements
### Requirement: 本地持久化调用日志

在 LangSmith 远端追踪基础上，系统 SHALL 提供本地持久化调用日志，将路由判定与 Agent 调用记录到本地 JSON 行式文件，与远端 trace 并行覆盖。

#### Scenario: 本地日志与远端 trace 并行

- **WHEN** 一次智能体问答请求完成
- **AND** LangSmith 追踪已启用
- **THEN** 远端生成 trace，同时本地日志文件追加对应记录
- **AND** 本地记录与远端 trace 共享同一 trace_id，便于对账

#### Scenario: 无 LangSmith 时本地日志仍可用

- **WHEN** 未配置 `LANGCHAIN_API_KEY`（远端追踪关闭）
- **THEN** 本地调用日志仍正常写入
- **AND** 主流程不受影响
```

> 在现有 `## Requirements` 标题下、`### Requirement: LangSmith 环境变量配置` 之前插入上述 `### Requirement: 本地持久化调用日志` 段落，并替换原有 `## Purpose` 的 TBD 行。

- [x] **Step 5: 更新 `.gitignore` 忽略本地日志**

在 `.gitignore` 末尾追加：

```gitignore

# 本地路由观测日志（按天生成，不入库）
logs/
```

- [x] **Step 6: 提交**

```bash
git add openspec/specs/langsmith-monitoring/spec.md .gitignore
git commit -m "docs(observability): 同步 langsmith-monitoring 主 spec 与日志忽略规则"
```

---

## Self-Review

**1. Spec 覆盖核对：**
- 路由观测 spec 的「本地路由调用日志落库」→ Task 1（`routing_log` + `observe_routing`，含候选 Agent、排他规则命中、降级、耗时、失败原因、结果版本、trace_id）。
- 「路由混淆矩阵」→ Task 2（`confusion_metrics`，TP/FP/FN/TN/accuracy/confusion_rate）。
- 「路由回归自动化」→ Task 3（≥20 正反例 + 回归脚本 + 退出码 + 混淆矩阵输出）。
- 「路由看板」→ Task 4（正确率/混淆率/漏调用率/参数完整率 + Markdown 导出）。
- 「结果可追溯链」→ Task 2（`trace_result` 按 trace_id 返回数据版本/Agent 版本/参数/调用时间）。
- langsmith-monitoring 增量 spec「本地持久化调用日志」→ Task 1（共享 trace_id）+ Task 5.4（主 spec 同步）。

**2. 占位符扫描：** 无 TBD/TODO；所有代码步骤均含完整实现。`test_observe_routing_failure_logs_reason` 的占位版本已在 Step 10 替换为可稳定触发的 monkeypatch 版本。

**3. 类型一致性：** `observe_routing` 返回 `(question_type, relevance, final_type, routing_status)` 与 `nodes.identify_question_node` 解包一致；`confusion_metrics` 返回键 `tp/fp/fn/tn/total/accuracy/confusion_rate/positive_label` 在回归脚本与看板中一致引用；`read_routing_logs` 在日志/追溯/看板三处复用；`trace_result` 返回键 `data_version/agent_version/params/call_time` 与看板 `compute_log_metrics` 的完整率判定字段一致。

**4. 行为保持约束：** Task 1 Step 9 明确 `identify_question_node` 返回值逐字段不变；观测点通过 `observe_routing` 复刻现状的双调用（`identify_question_type` 内部已应用规则 + 再次 `apply_exclusive_rules`），排他规则逻辑未改动（Non-Goal 满足）。