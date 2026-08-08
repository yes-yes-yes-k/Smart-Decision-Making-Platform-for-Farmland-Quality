"""测试路由可观测性：JSON 行式日志、观测封装、混淆矩阵、追溯链。"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.observability.routing_log import (
    set_log_path, set_log_enabled, write_routing_log, read_routing_logs,
)
from framework.observability.observe import observe_routing


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

    def test_observe_routing_failure_logs_reason(self, monkeypatch):
        import framework.observability.observe as _observe
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            def _boom(*a, **k):
                raise RuntimeError("boom")
            # observe 模块顶层 `from exclusive_rules import apply_exclusive_rules`
            # 绑定了自身命名空间引用，故需 patch _observe.apply_exclusive_rules。
            monkeypatch.setattr(_observe, "apply_exclusive_rules", _boom)
            with pytest.raises(RuntimeError):
                _observe.observe_routing("我的田耕地质量等级是多少", {"scale": "地块"},
                                         trace_id="fail-1")
            with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                entry = json.loads(f.readline())
            assert entry["trace_id"] == "fail-1"
            assert entry["failure_reason"] == "boom"


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