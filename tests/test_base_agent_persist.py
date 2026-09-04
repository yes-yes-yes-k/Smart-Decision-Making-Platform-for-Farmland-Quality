"""BaseAgent._persist_result 单元测试：成功写入 / 无结果表 / 写入失败 / 异常不传播。"""
import sys
import os
import types
import unittest
from unittest.mock import patch, MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

# 测试环境可能未安装 geoalchemy2，这里在导入 thematic_model 之前先 stub
# 一个 Geometry 类（返回 MagicMock 实例），避免 SQLAlchemy Column 在类定义
# 阶段调用 Geometry(...) 时因缺少 `_set_parent_with_dispatch` 而失败。
if "geoalchemy2" not in sys.modules:
    _geo_stub = types.ModuleType("geoalchemy2")

    class _Geometry:
        """stub：返回 MagicMock，满足 SQLAlchemy Column 初始化所需协议。"""

        def __new__(cls, *args, **kwargs):
            return MagicMock()

    _geo_stub.Geometry = _Geometry
    sys.modules["geoalchemy2"] = _geo_stub

import framework.models.thematic_model  # noqa: F401  确保模块加载以便 patch 解析属性


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
        persisted = agent._build_result_record.call_args.args[1]
        self.assertEqual(persisted["out"], 2)
        self.assertEqual(persisted["model_version"], "unknown")
        self.assertEqual(persisted["actual_inputs"], {"in": 1})

    @patch("framework.models.thematic_model.ModelExecutionLog")
    @patch("framework.models.user.db")
    def test_persist_reuses_request_trace_and_canonical_context(self, mock_db, mock_log_cls):
        mock_db.session = MagicMock()
        mock_log_cls.return_value = MagicMock(id=7)
        agent = _make_test_agent("acidification-remediation")
        execution_context = {
            "trace_id": "trace-1", "user_id": 7, "conversation_id": 12,
            "analysis_context": {
                "mode": "spatial", "version": 3,
                "object": {"type": "parcel", "id": "P001", "area_code": "440281"},
            },
        }
        self.assertTrue(agent._persist_result(
            "model-4", "P001", {"SJD": 5.1},
            {"model_version": "acid-v2", "data_as_of": "2024"}, "ok",
            execution_context=execution_context,
        ))
        values = mock_log_cls.call_args.kwargs
        self.assertEqual(values["trace_id"], "trace-1")
        self.assertEqual(values["user_id"], 7)
        self.assertEqual(values["conversation_id"], 12)
        self.assertEqual(values["analysis_object_type"], "parcel")
        self.assertEqual(values["analysis_object_id"], "P001")
        self.assertEqual(values["context_version"], 3)
        self.assertEqual(values["model_version"], "acid-v2")

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
        """agent_id 属性从能力注册表查找：真实 model_id 映射到对应 agent_id。"""
        agent = _make_test_agent("stability-risk-evaluation")
        self.assertEqual(agent.agent_id, "model-1")

    def test_agent_id_fallback_to_model_id(self):
        """model_id 不在注册表时回退到 model_id 本身。"""
        agent = _make_test_agent("unknown-model")
        self.assertEqual(agent.agent_id, "unknown-model")


if __name__ == "__main__":
    unittest.main()
