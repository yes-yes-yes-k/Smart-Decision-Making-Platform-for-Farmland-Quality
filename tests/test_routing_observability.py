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


class TestObserveLogFailureIsolation:
    """观测日志写入失败不得泄漏到路由主流程（I1/M3）。"""

    def test_success_log_write_failure_does_not_break_routing(self, monkeypatch):
        import framework.observability.observe as _observe
        from framework.agents import routing as _routing
        real = _routing.EMBEDDING_AVAILABLE
        try:
            _routing.EMBEDDING_AVAILABLE = False  # 确定性关键词路径
            def _boom(*a, **k):
                raise OSError("disk full")
            monkeypatch.setattr(_observe, "write_routing_log", _boom)
            # 成功路径：日志写入失败不应改变路由结果，也不应抛异常
            qtype, rel, final_type, status = _observe.observe_routing(
                "我的田耕地质量等级是多少", {"scale": "地块"},
            )
            assert final_type == 5
            assert status == "normal"
            assert qtype is not None
        finally:
            _routing.EMBEDDING_AVAILABLE = real

    def test_failure_log_write_failure_preserves_original_error(self, monkeypatch):
        import framework.observability.observe as _observe
        def _boom_route(*a, **k):
            raise RuntimeError("route-boom")
        def _boom_log(*a, **k):
            raise OSError("disk full")
        # 路由异常 + 日志写入异常同时发生：必须抛出原始路由异常，而非日志异常
        monkeypatch.setattr(_observe, "apply_exclusive_rules", _boom_route)
        monkeypatch.setattr(_observe, "write_routing_log", _boom_log)
        with pytest.raises(RuntimeError, match="route-boom"):
            _observe.observe_routing("我的田耕地质量等级是多少", {"scale": "地块"})


class TestConfusionMetricsLengthCheck:
    def test_mismatched_length_raises_value_error(self):
        from framework.observability.metrics import confusion_metrics
        with pytest.raises(ValueError):
            confusion_metrics(["a", "b"], ["a"], "a")


class TestRoutingLogReadRobustness:
    def test_bad_line_skipped_without_interrupting_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "routing_calls_ok.jsonl")
            with open(good, "w", encoding="utf-8") as f:
                f.write('{"trace_id": "a"}\n')
                f.write('this is not valid json\n')
                f.write('{"trace_id": "b"}\n')
            entries = read_routing_logs(tmp)
            assert [e["trace_id"] for e in entries] == ["a", "b"]