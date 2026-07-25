"""测试 BaseAgent 抽象基类与 MockDataLoader 工具"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.base import BaseAgent
from framework.agents.mock_data import MockDataLoader


def test_baseagent_cannot_instantiate():
    """BaseAgent 是抽象类，不能直接实例化"""
    try:
        BaseAgent("x", "y", "model-0", "test")
        raise AssertionError("应抛出 TypeError")
    except TypeError:
        pass
    print("✓ BaseAgent 抽象类阻止直接实例化")


def test_baseagent_subclass_must_implement_methods():
    """子类必须实现 execute 和 answer_question"""

    class IncompleteAgent(BaseAgent):
        def execute(self, task):
            return {"status": "ok", "result": {}, "metadata": {"simulated": True}}

    try:
        IncompleteAgent("x", "y", "model-0", "test")
        raise AssertionError("应抛出 TypeError 因 answer_question 未实现")
    except TypeError:
        pass
    print("✓ 子类未实现全部抽象方法时抛出 TypeError")


def test_baseagent_complete_subclass():
    """完整子类可正常构造并访问属性"""

    class DummyAgent(BaseAgent):
        def execute(self, task):
            return {"status": "ok", "result": task, "metadata": {"simulated": True}}

        def answer_question(self, question, context):
            return {"answer": "ok", "evidence": [], "confidence": 0.5, "simulated": True}

    agent = DummyAgent("dummy", "测试", "model-0", "test")
    assert agent.name == "dummy"
    assert agent.description == "测试"
    assert agent.model_id == "model-0"
    assert agent.domain == "test"
    assert agent.dependencies == []
    ex = agent.execute({"foo": 1})
    assert ex["status"] == "ok"
    assert ex["metadata"]["simulated"] is True
    aq = agent.answer_question("问题", {})
    assert aq["simulated"] is True
    print("✓ BaseAgent 完整子类构造与方法调用正常")


def test_mock_data_merge_defaults():
    defaults = {"ph": 5.5, "cec": 8.5}
    merged = MockDataLoader.merge_defaults({"ph": 4.2}, defaults)
    assert merged["ph"] == 4.2
    assert merged["cec"] == 8.5
    print("✓ MockDataLoader.merge_defaults 优先使用输入值")


def test_mock_data_mark_simulated():
    payload = {"answer": "x"}
    out = MockDataLoader.mark_simulated(payload)
    assert out["simulated"] is True
    assert out["answer"] == "x"
    # 不应修改原对象
    assert "simulated" not in payload
    print("✓ MockDataLoader.mark_simulated 添加标记且不污染原对象")


def test_mock_data_apply_threshold():
    rules = [
        (lambda v: v < 4.5, "强酸性"),
        (lambda v: 4.5 <= v < 5.5, "酸性"),
        (lambda v: 5.5 <= v < 6.5, "弱酸性"),
        (lambda v: v >= 6.5, "正常"),
    ]
    assert MockDataLoader.apply_threshold(4.2, rules) == "强酸性"
    assert MockDataLoader.apply_threshold(5.0, rules) == "酸性"
    assert MockDataLoader.apply_threshold(6.0, rules) == "弱酸性"
    assert MockDataLoader.apply_threshold(7.0, rules) == "正常"
    print("✓ MockDataLoader.apply_threshold 按顺序匹配规则")


if __name__ == "__main__":
    test_baseagent_cannot_instantiate()
    test_baseagent_subclass_must_implement_methods()
    test_baseagent_complete_subclass()
    test_mock_data_merge_defaults()
    test_mock_data_mark_simulated()
    test_mock_data_apply_threshold()
    print("\n所有 BaseAgent、MockDataLoader 测试通过！")
