---
change: add-observability-api-endpoints
design-doc: docs/superpowers/specs/2026-08-15-observability-api-design.md
base-ref: 71b37ab68805701187b6ca336d5f5b49b70b4905
---

# 观测 API 端点与 trace_id 贯穿 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增观测 API blueprint（追溯链 + 看板指标两个查询端点），让 chat 接口（流式与非流式）响应返回与本地路由日志一致的 `trace_id`，并完成观测模块包级导出完整化，供前端端到端追溯一次路由/调用。

**Architecture:** `MultiAgentState` 新增 `trace_id: Optional[str]`，`identify_question_node` 在调用 `observe_routing` 前生成 `uuid.uuid4().hex` 传入（`observe_routing` 已支持 `trace_id` 关键字参数且保持 4 元组签名不变，零改动），并写入 state；`MultiAgentOrchestrator.run` 在返回的 dict 外层附加 `trace_id`，`run_stream` 在 `done` 数据中附加。新增 `framework/api/routes/observability.py` 定义 `observability_bp`（`@jwt_required`），在 `app.py` 注册为 `/api/v1/observability`；`GET /trace/<trace_id>` 复用 `traceability.trace_result`，`GET /dashboard` 复用 `dashboard.compute_log_metrics` 并读取 `confusion_matrix*.json`（含 `.llm.json` 变体），缺失兜底默认值。观测模块 `__init__.py` 导出 `routing_log/metrics/dashboard/traceability/observe`，API 层统一走包级导入。

**Tech Stack:** Python 3.10+、Flask + Blueprint、flask_jwt_extended、LangGraph、pytest。

## Global Constraints

- `observe_routing` 保持 4 元组签名 `(question_type, relevance, final_type, routing_status)` 不变（Design Doc 决策 D1 方案 A；备选 B 改 5 元组、备选 C API 层生成 trace_id 均不采用）。
- `trace_id` 统一为 `uuid.uuid4().hex`（32 位小写十六进制），与本地路由日志 `entry["trace_id"]` 完全一致。
- 端点沿用现有 `@jwt_required` 鉴权约定，不引入新鉴权机制（无 JWT → 401）。
- 不改变观测模块内部落盘格式与算法（`routing_log` / `metrics` / `traceability` 保持不变），不新增依赖。
- 看板矩阵读取与 `dashboard.main` 的 `logs/` 目录约定一致（`confusion_matrix.json` 及 `*.llm.json` 变体），缺失时兜底空矩阵；日志目录沿用 `routing_log._LOG_DIR`（默认 `logs`）。
- API 层统一 `from framework.observability import ...` 包级导入。
- 测试一律 monkeypatch：不发起真实 LLM/网络调用；日志/矩阵目录用 `monkeypatch.setattr(routing_log, "_LOG_DIR", tmp)` 隔离，避免全局日志状态泄漏与仓库内 `logs/` 污染。

## File Structure

| 文件 | 责任 | 操作 |
|------|------|------|
| `framework/agents/state.py` | `MultiAgentState` 新增 `trace_id: Optional[str]` | Modify |
| `framework/agents/nodes.py` | `identify_question_node` 生成并透传 `trace_id` 写入 state | Modify |
| `framework/agents/orchestrator.py` | `run` 结果 dict 附加 `trace_id`；`run_stream` done 数据附加 `trace_id` | Modify |
| `framework/observability/__init__.py` | 包级导出 `routing_log/metrics/dashboard/traceability/observe` | Modify |
| `framework/api/routes/observability.py` | `observability_bp`：`GET /trace/<trace_id>`、`GET /dashboard`，均 `@jwt_required` | Create |
| `framework/api/app.py` | 注册 `observability_bp` 为 `/api/v1/observability` | Modify |
| `framework/api/routes/chat.py` | `/` 与 `/stream` 的 `response_data` 新增 `trace_id` | Modify |
| `tests/test_observability_api.py` | 追溯命中/未命中、看板指标、看板缺失、鉴权 401 | Create |
| `tests/test_nodes_passthrough.py` | 节点/编排层/chat 响应的 trace_id 透传断言 | Modify |
| `tests/test_routing_observability.py` | 包导出 + 节点写入 trace_id 断言 | Modify |

---

## Task 1: 观测模块包导出完整化

**Files:**
- Modify: `framework/observability/__init__.py`
- Test: `tests/test_routing_observability.py`（末尾追加导出测试）

**Interfaces:**
- Consumes: 无
- Produces: `framework.observability` 包可直接导入 `routing_log`、`metrics`、`dashboard`、`traceability`、`observe` 五个子模块（后续 API 层统一包级导入的前提）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_routing_observability.py` 末尾追加：

```python
class TestPackageExports:
    """观测模块包级导出完整化：API 层统一 from framework.observability import ..."""

    def test_all_submodules_exported(self):
        from framework.observability import (
            routing_log, metrics, dashboard, traceability, observe,
        )
        assert callable(routing_log.write_routing_log)
        assert callable(metrics.confusion_metrics)
        assert callable(dashboard.compute_log_metrics)
        assert callable(traceability.trace_result)
        assert callable(observe.observe_routing)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_routing_observability.py::TestPackageExports -v`
Expected: FAIL with `ImportError: cannot import name 'metrics' from 'framework.observability'`

- [ ] **Step 3: 实现包级导出**

将 `framework/observability/__init__.py` 整体替换为：

```python
"""framework.observability：本地路由可观测性（日志/指标/追溯/看板）。

复用 framework/upload/audit_logger.py 的 JSON 行式落盘范式，纯 Python 实现，无新增依赖。
与 LangSmith 远端 trace 并行覆盖，共享同一 trace_id。
"""
from . import routing_log
from . import metrics
from . import dashboard
from . import traceability
from . import observe

__all__ = ["routing_log", "metrics", "dashboard", "traceability", "observe"]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_routing_observability.py::TestPackageExports -v`
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add framework/observability/__init__.py tests/test_routing_observability.py
git commit -m "feat(observability): 包级导出 routing_log/metrics/dashboard/traceability/observe"
```

---

## Task 2: trace_id 贯穿 state 层（state + identify_question_node）

**Files:**
- Modify: `framework/agents/state.py`（`MultiAgentState` 末尾追加字段）
- Modify: `framework/agents/nodes.py`（顶部 `import uuid`；`identify_question_node` 生成并透传 trace_id）
- Test: `tests/test_routing_observability.py`（`TestNodeInjection` 追加 trace_id 断言）
- Test: `tests/test_nodes_passthrough.py`（追加节点级 trace_id 测试）

**Interfaces:**
- Consumes: `observe_routing(question, context, *, trace_id=..., ...)`（`trace_id` 关键字参数已存在，无需改 observe.py）
- Produces: `identify_question_node` 返回的 state 新增 `trace_id: str`（32 位 uuid hex），与本次路由日志 `entry["trace_id"]` 一致；`MultiAgentState` 新增 `trace_id: Optional[str]` 字段

- [ ] **Step 1: 追加失败测试**

在 `tests/test_routing_observability.py` 的 `TestNodeInjection.test_identify_question_node_preserves_return_and_logs` 中，现有断言（`result["question_type"] == 2`、`entry["question_type"] == 2`）之后追加：

```python
                assert result["trace_id"]
                assert isinstance(result["trace_id"], str)
                assert len(result["trace_id"]) == 32  # uuid4().hex
                assert entry["trace_id"] == result["trace_id"]
```

在 `tests/test_nodes_passthrough.py` 末尾追加：

```python
def test_identify_question_node_writes_trace_id(monkeypatch):
    """identify_question_node 应生成 trace_id 写入 state，且与观测日志一致。"""
    import tempfile
    import os
    import json
    from framework.agents import routing as _routing
    from framework.agents.nodes import identify_question_node
    from framework.observability.routing_log import set_log_path

    real = _routing.EMBEDDING_AVAILABLE
    try:
        _routing.EMBEDDING_AVAILABLE = False  # 确定性关键词路径
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            state = {"request": {"question": "我的田耕地质量等级是多少"}}
            result = identify_question_node(state)
            assert result["trace_id"]
            assert len(result["trace_id"]) == 32
            with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                entry = json.loads(f.readline())
            assert entry["trace_id"] == result["trace_id"]
    finally:
        _routing.EMBEDDING_AVAILABLE = real
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_routing_observability.py::TestNodeInjection tests/test_nodes_passthrough.py::test_identify_question_node_writes_trace_id -v`
Expected: FAIL with `KeyError: 'trace_id'`（state 尚不含该字段）

- [ ] **Step 3: 修改 state.py 与 nodes.py**

`framework/agents/state.py` 末尾追加字段：

```python
    routing_status: Optional[str]
    trace_id: Optional[str]
```

`framework/agents/nodes.py` 顶部（`from __future__ import annotations` 之后）新增 `import uuid`，并将 `identify_question_node` 替换为：

```python
def identify_question_node(state: MultiAgentState) -> MultiAgentState:
    from framework.observability.observe import observe_routing

    question = state["request"].get("question", "")
    context = _extract_five_dim_context(state)
    trace_id = uuid.uuid4().hex
    question_type, relevance, final_type, routing_status = observe_routing(
        question, context, trace_id=trace_id
    )
    return {
        **state,
        "trace_id": trace_id,
        "question_type": final_type,
        "relevance": relevance,
        "routing_status": routing_status,
        "error": None,
    }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_routing_observability.py::TestNodeInjection tests/test_nodes_passthrough.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add framework/agents/state.py framework/agents/nodes.py tests/test_routing_observability.py tests/test_nodes_passthrough.py
git commit -m "feat(agents): state 新增 trace_id，identify_question_node 生成并透传"
```

---

## Task 3: 编排层透传 trace_id（run / run_stream）

**Files:**
- Modify: `framework/agents/orchestrator.py`（`run` 结果 dict 附加 `trace_id`；`run_stream` 的 done 数据附加 `trace_id`；两处 `initial_state` 补 `"trace_id": None`）
- Test: `tests/test_nodes_passthrough.py`（追加 orchestrator 层 trace_id 测试）

**Interfaces:**
- Consumes: Task 2 的 `identify_question_node` 写入 state 的 `trace_id`
- Produces:
  - `MultiAgentOrchestrator.run(request, conversation_history) -> Dict`：返回 dict 恒含 `trace_id`（成功路径为 `{**result["model_results"], "trace_id": ...}`）
  - `MultiAgentOrchestrator.run_stream` 的 `done` 事件 `data` 含 `trace_id`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_nodes_passthrough.py` 末尾追加：

```python
def test_orchestrator_run_attaches_trace_id():
    """orchestrator.run 返回的 dict 应附加 state 中的 trace_id。"""
    from framework.agents.orchestrator import MultiAgentOrchestrator

    class FakeApp:
        def invoke(self, initial_state):
            return {
                "status": "completed",
                "model_results": {"status": "ok", "answer": "ok", "question_type": 2, "sources": []},
                "trace_id": "tid-1",
            }

    orch = MultiAgentOrchestrator()
    orch._app = FakeApp()  # 绕过真实图编译
    result = orch.run({"question": "q"})
    assert result["trace_id"] == "tid-1"
    assert result["answer"] == "ok"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_nodes_passthrough.py::test_orchestrator_run_attaches_trace_id -v`
Expected: FAIL with `KeyError: 'trace_id'`

- [ ] **Step 3: 修改 orchestrator.py**

`run` 方法：`initial_state` 中 `"routing_status": "normal",` 之后追加 `"trace_id": None,`；并将 `invoke` 后的返回逻辑替换为：

```python
        result = self._app.invoke(initial_state)
        trace_id = result.get("trace_id")

        if result["status"] == "completed":
            return {**result["model_results"], "trace_id": trace_id}
        else:
            return {
                "status": "error",
                "error": {
                    "code": "PROCESS_FAILED",
                    "message": result.get("error", "流程执行失败"),
                },
                "trace_id": trace_id,
            }
```

`run_stream` 方法：`initial_state` 中 `"relevance": None,` 之后追加 `"trace_id": None,`；`done` 事件 `data` 字典末尾追加：

```python
                "data": {
                    "answer": full_answer,
                    "sources": sources,
                    "model_results": done_model_results,
                    "question_type": question_type,
                    "question": question,
                    "trace_id": state.get("trace_id"),
                },
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_nodes_passthrough.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add framework/agents/orchestrator.py tests/test_nodes_passthrough.py
git commit -m "feat(orchestrator): run 结果与 run_stream done 数据附加 trace_id"
```

---

## Task 4: 追溯链 API 端点（observability_bp + trace + 注册）

**Files:**
- Create: `framework/api/routes/observability.py`（blueprint + `GET /trace/<trace_id>`）
- Modify: `framework/api/app.py`（import + 注册 `/api/v1/observability`）
- Test: `tests/test_observability_api.py`（新建：fixture + 追溯命中/未命中 + 鉴权 401）

**Interfaces:**
- Consumes: `framework.observability.traceability.trace_result(trace_id, log_dir=None)`（返回追溯 dict 或 None）
- Produces:
  - `observability_bp`（Blueprint `'observability'`），app.py 注册 url_prefix `/api/v1/observability`
  - `GET /api/v1/observability/trace/<trace_id>`：命中 → `{"status":"ok","data":{...}}` 200；未命中 → `{"status":"error","message":"trace 不存在"}` 404；无 JWT → 401

- [ ] **Step 1: 新建测试文件并写失败测试**

新建 `tests/test_observability_api.py`：

```python
"""测试观测 API：追溯链命中/未命中、看板指标、看板缺失、鉴权 401。"""
import sys
import os
import json
import datetime
import shutil
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.app import create_app
from framework.models.user import db, User
from framework.config import SQLiteConfig
from werkzeug.security import generate_password_hash


@pytest.fixture
def client():
    """创建测试客户端：SQLite 临时 DB + admin 用户。"""
    tmp_db_dir = tempfile.mkdtemp(prefix="test_observability_")
    tmp_db_path = os.path.join(tmp_db_dir, "test.db")

    original_db_uri = SQLiteConfig.SQLALCHEMY_DATABASE_URI
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_db_path}'

    app = create_app('sqlite')
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            nickname='管理员',
            role='admin',
            status=1,
        )
        db.session.add(admin)
        db.session.commit()

    client = app.test_client()
    client._app = app

    yield client

    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


def _login(client, username='admin', password='admin123'):
    """登录获取 JWT token。"""
    resp = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
    return resp.get_json()['data']['token']


def _write_log_entry(log_dir, tid, **overrides):
    """直接写一条按天命名的路由日志到 log_dir（不依赖全局日志状态）。"""
    day = datetime.datetime.now().strftime("%Y%m%d")
    path = os.path.join(str(log_dir), f"routing_calls_{day}.jsonl")
    entry = {
        "trace_id": tid,
        "timestamp": "2026-08-15 10:00:00",
        "data_version": "v1",
        "agent_version": "m2",
        "params": {},
    }
    entry.update(overrides)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


class TestTraceEndpoint:
    def test_trace_hit_returns_200(self, client, tmp_path, monkeypatch):
        from framework.observability import routing_log
        monkeypatch.setattr(routing_log, "_LOG_DIR", str(tmp_path))
        _write_log_entry(tmp_path, "trace-abc")
        token = _login(client)
        resp = client.get(
            "/api/v1/observability/trace/trace-abc",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["trace_id"] == "trace-abc"
        assert data["data_version"] == "v1"
        assert data["call_time"] == "2026-08-15 10:00:00"

    def test_trace_miss_returns_404(self, client, tmp_path, monkeypatch):
        from framework.observability import routing_log
        monkeypatch.setattr(routing_log, "_LOG_DIR", str(tmp_path))
        token = _login(client)
        resp = client.get(
            "/api/v1/observability/trace/not-exist",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_no_jwt_returns_401(self, client):
        resp = client.get("/api/v1/observability/trace/any")
        assert resp.status_code == 401
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_observability_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'framework.api.routes.observability'`（或 404 路由不存在）

- [ ] **Step 3: 新建 observability.py 与注册 blueprint**

新建 `framework/api/routes/observability.py`：

```python
"""观测 API：追溯链与看板指标查询端点（均需 JWT 鉴权）。

- GET /api/v1/observability/trace/<trace_id> → 追溯信息（命中 200，未命中 404）
- GET /api/v1/observability/dashboard → 看板结构化 JSON 指标（Task 5 补充）
"""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from framework.observability.traceability import trace_result

observability_bp = Blueprint('observability', __name__)


@observability_bp.route('/trace/<trace_id>', methods=['GET'])
@jwt_required()
def get_trace(trace_id):
    """按 trace_id 返回追溯信息；未命中返回 404。"""
    info = trace_result(trace_id)
    if info is None:
        return jsonify({"status": "error", "message": "trace 不存在"}), 404
    return jsonify({"status": "ok", "data": info})
```

修改 `framework/api/app.py`：

1. 在 `from framework.api.routes.data_import import data_import_bp` 之后追加：

```python
from framework.api.routes.observability import observability_bp
```

2. 在 `app.register_blueprint(data_import_bp, url_prefix='/api/v1/data')` 之后追加：

```python
    app.register_blueprint(observability_bp, url_prefix='/api/v1/observability')
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_observability_api.py -v`
Expected: 3 passed（命中/未命中/401）

- [ ] **Step 5: 提交**

```bash
git add framework/api/routes/observability.py framework/api/app.py tests/test_observability_api.py
git commit -m "feat(api): 新增 observability_bp 与追溯链端点 GET /trace/<trace_id>"
```

---

## Task 5: 看板 API 端点（GET /dashboard）

**Files:**
- Modify: `framework/api/routes/observability.py`（新增 `GET /dashboard`，补齐 `json/os/routing_log/compute_log_metrics` 导入）
- Test: `tests/test_observability_api.py`（追加看板指标与缺失兜底测试）

**Interfaces:**
- Consumes:
  - `framework.observability.routing_log._LOG_DIR`（日志/矩阵目录，测试经 monkeypatch 隔离）
  - `framework.observability.dashboard.compute_log_metrics(entries) -> {"total_calls","missed_call_rate","param_completeness_rate"}`
- Produces: `GET /api/v1/observability/dashboard` → `{"status":"ok","data":{"log_metrics":{...},"confusion_matrices":{"confusion_matrix.json":{...},"confusion_matrix.llm.json":{...}}}}`；文件缺失 → `confusion_matrices` 为空 dict，`log_metrics` 为全 0 默认值；无 JWT → 401

- [ ] **Step 1: 追加失败测试**

在 `tests/test_observability_api.py` 末尾追加：

```python
class TestDashboardEndpoint:
    def test_dashboard_returns_metrics_and_matrices(self, client, tmp_path, monkeypatch):
        from framework.observability import routing_log
        monkeypatch.setattr(routing_log, "_LOG_DIR", str(tmp_path))
        # 两条日志：一条 boundary_pending → missed_call_rate = 0.5
        _write_log_entry(tmp_path, "a", routing_status="normal")
        _write_log_entry(tmp_path, "b", routing_status="boundary_pending")
        # 混淆矩阵文件（含 .llm.json 变体）
        with open(os.path.join(str(tmp_path), "confusion_matrix.json"), "w", encoding="utf-8") as f:
            json.dump({"model-2-vs-model-3": {"tp": 1, "fp": 0, "fn": 0, "tn": 3, "accuracy": 1.0, "confusion_rate": 0.0}}, f)
        with open(os.path.join(str(tmp_path), "confusion_matrix.llm.json"), "w", encoding="utf-8") as f:
            json.dump({}, f)

        token = _login(client)
        resp = client.get("/api/v1/observability/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["log_metrics"]["total_calls"] == 2
        assert data["log_metrics"]["missed_call_rate"] == 0.5
        assert data["log_metrics"]["param_completeness_rate"] == 1.0
        assert "confusion_matrix.json" in data["confusion_matrices"]
        assert "confusion_matrix.llm.json" in data["confusion_matrices"]

    def test_dashboard_missing_data_returns_defaults(self, client, tmp_path, monkeypatch):
        from framework.observability import routing_log
        monkeypatch.setattr(routing_log, "_LOG_DIR", str(tmp_path))
        token = _login(client)
        resp = client.get("/api/v1/observability/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["log_metrics"] == {"total_calls": 0, "missed_call_rate": 0.0, "param_completeness_rate": 0.0}
        assert data["confusion_matrices"] == {}
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_observability_api.py::TestDashboardEndpoint -v`
Expected: FAIL with `404 NOT FOUND`（dashboard 路由未实现）

- [ ] **Step 3: 实现 dashboard 端点**

将 `framework/api/routes/observability.py` 整体替换为：

```python
"""观测 API：追溯链与看板指标查询端点（均需 JWT 鉴权）。

- GET /api/v1/observability/trace/<trace_id> → 追溯信息（命中 200，未命中 404）
- GET /api/v1/observability/dashboard → 看板结构化 JSON 指标
"""
import json
import os

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from framework.observability import routing_log
from framework.observability.dashboard import compute_log_metrics
from framework.observability.traceability import trace_result

observability_bp = Blueprint('observability', __name__)


@observability_bp.route('/trace/<trace_id>', methods=['GET'])
@jwt_required()
def get_trace(trace_id):
    """按 trace_id 返回追溯信息；未命中返回 404。"""
    info = trace_result(trace_id)
    if info is None:
        return jsonify({"status": "error", "message": "trace 不存在"}), 404
    return jsonify({"status": "ok", "data": info})


@observability_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    """读取本地路由日志与混淆矩阵，返回结构化指标 JSON。

    复用 dashboard.compute_log_metrics 避免指标逻辑漂移；混淆矩阵文件
    （confusion_matrix*.json，含 .llm.json 变体）缺失时兜底空矩阵。
    """
    log_dir = routing_log._LOG_DIR
    entries = routing_log.read_routing_logs(log_dir)
    log_metrics = compute_log_metrics(entries)

    matrices = {}
    if os.path.isdir(log_dir):
        for name in sorted(os.listdir(log_dir)):
            if name.startswith("confusion_matrix") and name.endswith(".json"):
                try:
                    with open(os.path.join(log_dir, name), "r", encoding="utf-8") as f:
                        matrices[name] = json.load(f)
                except (OSError, json.JSONDecodeError):
                    matrices[name] = {}

    return jsonify({
        "status": "ok",
        "data": {
            "log_metrics": log_metrics,
            "confusion_matrices": matrices,
        },
    })
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_observability_api.py -v`
Expected: 5 passed（Task 4 的 3 个 + 本任务 2 个）

- [ ] **Step 5: 提交**

```bash
git add framework/api/routes/observability.py tests/test_observability_api.py
git commit -m "feat(api): 新增看板端点 GET /dashboard 返回结构化指标 JSON"
```

---

## Task 6: chat 接口返回 trace_id（/ 与 /stream）

**Files:**
- Modify: `framework/api/routes/chat.py`（`/` 的 `response_data` 与 `/stream` done 的 `response_data` 各新增 `trace_id`）
- Test: `tests/test_nodes_passthrough.py`（追加 chat 响应 trace_id 断言：非流式 + 流式）

**Interfaces:**
- Consumes: Task 3 的 `orchestrator.run` 返回 dict 含 `trace_id`、`run_stream` done `data` 含 `trace_id`
- Produces: `/api/v1/chat/` 响应 `data.trace_id`；`/api/v1/chat/stream` done 事件 `data.trace_id`（与本地路由日志一致）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_nodes_passthrough.py` 末尾追加：

```python
def test_chat_response_contains_trace_id():
    """POST /api/v1/chat/ → response data 含 trace_id（取自 orchestrator.run 结果）。"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app("sqlite")
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    def fake_run(req, conversation_history=None):
        return {
            "answer": "ok",
            "question_type": 2,
            "model_results": {"data": {"question_type": 2, "agents_invoked": [], "summary": "", "details": {}, "recommendations": []}},
            "trace_id": "chat-trace-1",
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "我的田耕地质量等级是多少"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["trace_id"] == "chat-trace-1"


def test_chat_stream_done_contains_trace_id():
    """POST /api/v1/chat/stream → done 事件 data 含 trace_id。"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app("sqlite")
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    def fake_run_stream(req, conversation_history=None):
        yield {
            "type": "done",
            "data": {
                "answer": "ok",
                "sources": [],
                "model_results": {},
                "question_type": 2,
                "question": "q",
                "trace_id": "stream-trace-1",
            },
        }

    real_run_stream = multi_agent_orchestrator.run_stream
    multi_agent_orchestrator.run_stream = fake_run_stream
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/stream",
                json={"message": "我的田耕地质量等级是多少"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run_stream = real_run_stream

    assert resp.status_code == 200
    assert "stream-trace-1" in resp.get_data(as_text=True)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_nodes_passthrough.py::test_chat_response_contains_trace_id tests/test_nodes_passthrough.py::test_chat_stream_done_contains_trace_id -v`
Expected: FAIL（`response_data` 尚不含 `trace_id`）

- [ ] **Step 3: 修改 chat.py**

`framework/api/routes/chat.py` 的 `/` 端点 `response_data` 追加 `trace_id`：

```python
    response_data = {
        "answer": answer or multi_agent_summary,
        "sources": sources,
        "question_type": question_type,
        "model_results": model_results,
        "message_id": assistant_message.id,
        "routing_status": routing_status,
        "trace_id": result.get("trace_id"),
    }
```

`/stream` 端点 done 分支的 `response_data` 追加 `trace_id`：

```python
                    response_data = {
                        "answer": answer or multi_agent_summary,
                        "sources": sources,
                        "question_type": question_type,
                        "model_results": model_results,
                        "message_id": msg_id,
                        "trace_id": data_payload.get("trace_id"),
                    }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_nodes_passthrough.py -v`
Expected: 全部 passed（含既有 execute_models 透传与回归测试）

- [ ] **Step 5: 提交**

```bash
git add framework/api/routes/chat.py tests/test_nodes_passthrough.py
git commit -m "feat(api): chat / 与 /stream 响应新增 trace_id 字段"
```

---

## Task 7: 全量回归验证

**Files:**
- Verify: 全部改动文件

**Interfaces:**
- Consumes: Task 1-6 全部产出
- Produces: 全量测试通过，无回归

- [ ] **Step 1: 运行指定回归集**

Run: `python -m pytest tests/test_observability_api.py tests/test_routing_observability.py tests/test_nodes_passthrough.py -v`
Expected: 全部 passed

- [ ] **Step 2: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed（如有失败，多为既有测试对返回 dict 的断言需兼容新增的 `trace_id` 字段，按需以最小改动放宽断言）

- [ ] **Step 3: 手工端到端冒烟（可选）**

```bash
python -c "from framework.api.app import create_app; app = create_app(); print([str(r) for r in app.url_map.iter_rules() if 'observability' in str(r)])"
```
Expected: 输出含 `/api/v1/observability/dashboard` 与 `/api/v1/observability/trace/<trace_id>`

- [ ] **Step 4: 最终提交（如有回归修复）**

```bash
git add -A
git commit -m "chore: 观测 API 端点全量回归验证通过"
```

---

## 完成验证清单

- [ ] `framework/observability/__init__.py` 导出 5 个子模块（Task 1）
- [ ] `MultiAgentState.trace_id` + `identify_question_node` 写入 trace_id（Task 2）
- [ ] `orchestrator.run` / `run_stream` 透传 trace_id（Task 3）
- [ ] `GET /api/v1/observability/trace/<trace_id>` 命中 200 / 未命中 404 / 无 JWT 401（Task 4）
- [ ] `GET /api/v1/observability/dashboard` 返回 log_metrics + confusion_matrices，缺失兜底默认值（Task 5）
- [ ] chat `/` 与 `/stream` 响应含 `trace_id`，流式与非流式一致（Task 6）
- [ ] 全量 `pytest tests/` 通过（Task 7）
