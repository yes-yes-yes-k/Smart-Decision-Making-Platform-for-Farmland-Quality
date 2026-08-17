"""路由日志 DB 双写测试（PostgreSQL 测试库）。

覆盖三条路径：
1. 双写正常路径（DB 写入成功 + JSONL 写入成功）
2. DB 失败回退 JSONL（commit 抛异常不传播，JSONL 仍写入，触发告警）
3. entry 字段与 RoutingDecisionLog 列一一对应

PG 不可用时整个文件跳过（conftest.PG_AVAILABLE 控制）。
"""
import sys
import os
import json
import warnings
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import PG_AVAILABLE

pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL 测试库不可用")

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models import RoutingDecisionLog  # noqa: E402
from framework.observability import routing_log  # noqa: E402


@pytest.fixture
def pg_app():
    """真实 PG 测试库 app context，前后清理 routing_decision_log 表。"""
    app = create_app("default")
    with app.app_context():
        db.session.query(RoutingDecisionLog).delete()
        db.session.commit()
        yield app
        db.session.query(RoutingDecisionLog).delete()
        db.session.commit()


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    """用 tmp_path 隔离 JSONL 路径（monkeypatch 自动恢复原 override）。"""
    path = tmp_path / "routing_calls_test.jsonl"
    monkeypatch.setattr(routing_log, "_LOG_PATH_OVERRIDE", str(path))
    yield str(path)


def _make_entry(trace_id: str) -> dict:
    """构造与 RoutingDecisionLog 全列对齐的完整 entry。"""
    return {
        "trace_id": trace_id,
        "question": "我的田耕地质量等级是多少",
        "question_type": 2,
        "relevance": 0.87,
        "routing_status": "normal",
        "router_method": "keyword",
        "candidate_agents": ["model-2", "model-5"],
        "hit_exclusive_rules": ["rule-quality-grade"],
        "llm_reason": "关键词命中耕地质量等级",
        "llm_duration_ms": 12.5,
        "total_duration_ms": 34.2,
        "degradation": None,
        "five_dim_context": {
            "scale": "地块",
            "data_type": "评价结果",
            "business_task": "质量等级评价",
            "expected_output": "评价结果",
        },
        "data_version": "v2024.1",
        "agent_version": "model-2@1.0",
        "result_version": "v1.2",
        "failure_reason": None,
        "logged_at": datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc),
    }


class TestRoutingLogDb:
    def test_double_write_normal(self, pg_app, jsonl_path):
        """双写正常路径：write_routing_log 后 DB 与 JSONL 均有记录，trace_id 一致。"""
        trace_id = "db-test-001"
        routing_log.write_routing_log(_make_entry(trace_id))

        # JSONL 有记录
        with open(jsonl_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["trace_id"] == trace_id

        # DB 有记录
        rows = db.session.query(RoutingDecisionLog).filter_by(trace_id=trace_id).all()
        assert len(rows) == 1
        assert rows[0].question_type == 2
        assert rows[0].routing_status == "normal"

    def test_db_failure_fallback_jsonl(self, pg_app, jsonl_path, monkeypatch):
        """DB 失败回退：commit 抛异常时告警不抛出，JSONL 仍写入，DB 无记录。"""
        def _boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(db.session, "commit", _boom)

        trace_id = "db-fail-002"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # 不应抛出：DB 异常被 write_routing_log 隔离
            routing_log.write_routing_log(_make_entry(trace_id))
        assert any("DB 写入失败" in str(w.message) for w in caught)

        # JSONL 仍写入（降级备份）
        with open(jsonl_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["trace_id"] == trace_id

        # DB 无记录（commit 失败；rollback 清理 pending 状态后再查）
        db.session.rollback()
        rows = db.session.query(RoutingDecisionLog).filter_by(trace_id=trace_id).all()
        assert len(rows) == 0

    def test_entry_field_alignment(self, pg_app):
        """entry 字段对齐：write_routing_log_to_db 落库后逐列验证字段值。"""
        entry = _make_entry("db-align-003")
        routing_log.write_routing_log_to_db(entry)

        row = db.session.query(RoutingDecisionLog).filter_by(trace_id="db-align-003").one()
        assert row.trace_id == entry["trace_id"]
        assert row.question == entry["question"]
        assert row.question_type == entry["question_type"]
        assert row.relevance == entry["relevance"]
        assert row.routing_status == entry["routing_status"]
        assert row.router_method == entry["router_method"]
        assert row.candidate_agents == entry["candidate_agents"]
        assert row.hit_exclusive_rules == entry["hit_exclusive_rules"]
        assert row.llm_reason == entry["llm_reason"]
        assert row.llm_duration_ms == entry["llm_duration_ms"]
        assert row.total_duration_ms == entry["total_duration_ms"]
        assert row.degradation is None
        assert row.five_dim_context == entry["five_dim_context"]
        assert row.data_version == entry["data_version"]
        assert row.agent_version == entry["agent_version"]
        assert row.result_version == entry["result_version"]
        assert row.failure_reason is None
        assert row.logged_at == entry["logged_at"]
