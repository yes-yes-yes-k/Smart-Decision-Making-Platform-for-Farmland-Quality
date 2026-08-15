"""测试知识性问题检测：识别「什么是X」「X是什么意思」等模式，路由到 RAG 而非专业模型。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Task 7.1: _is_knowledge_question 单元测试
# ---------------------------------------------------------------------------

def test_knowledge_start_pattern_什么是():
    """开头匹配「什么是X」→ True"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("什么是土壤酸化") is True
    assert _is_knowledge_question("什么是有机质") is True


def test_knowledge_start_pattern_何为():
    """开头匹配「何为X」→ True"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("何为耕地质量等级") is True


def test_knowledge_start_pattern_解释():
    """开头匹配「解释X」→ True"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("解释土壤酸化") is True
    assert _is_knowledge_question("解释耕地质量等级评价") is True


def test_knowledge_contain_pattern_是什么意思():
    """包含匹配「X是什么意思」→ True"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("耕地质量等级是什么意思") is True
    assert _is_knowledge_question("土壤酸化是什么意思") is True


def test_knowledge_contain_pattern_什么意思():
    """包含匹配「X什么意思」→ True（不含「是」也算知识性）"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("综合指数什么意思") is True


def test_knowledge_contain_pattern_定义():
    """包含匹配「X定义」→ True"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("土壤酸化定义") is True
    assert _is_knowledge_question("耕地质量等级定义是什么") is True


def test_knowledge_contain_pattern_概念():
    """包含匹配「X概念」→ True"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("耕地质量概念") is True


def test_knowledge_contain_pattern_含义():
    """包含匹配「X含义」→ True"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("综合指数含义") is True


def test_diagnostic_question_质量等级_是多少():
    """具体诊断问题「我的田耕地质量等级是多少」→ False（不是知识性）"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("我的田耕地质量等级是多少") is False


def test_diagnostic_question_酸化严重吗():
    """具体诊断问题「我的田酸化严重吗」→ False"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("我的田酸化严重吗") is False


def test_diagnostic_question_稳定吗():
    """具体诊断问题「全省耕地质量整体稳定吗」→ False"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("全省耕地质量整体稳定吗") is False


def test_diagnostic_question_肥力怎么样():
    """具体诊断问题「我的田肥力怎么样」→ False"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("我的田肥力怎么样") is False


def test_diagnostic_question_施肥量():
    """具体诊断问题「有机肥每亩施用量多少」→ False"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("有机肥每亩施用量多少") is False


def test_knowledge_empty_string():
    """空字符串 → False"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question("") is False


def test_knowledge_none_input():
    """None 输入 → False（防御性）"""
    from framework.agents.nodes import _is_knowledge_question
    assert _is_knowledge_question(None) is False


# ---------------------------------------------------------------------------
# Task 7.4: identify_question_type 集成测试
# ---------------------------------------------------------------------------

def test_identify_什么是土壤酸化_returns_type0():
    """「什么是土壤酸化」应返回 type 0（走 RAG），而非 type 2"""
    from framework.agents.nodes import identify_question_type
    qt, _ = identify_question_type("什么是土壤酸化")
    assert qt == 0, f"知识性问题「什么是土壤酸化」期望 type 0，实际 type {qt}"


def test_identify_耕地质量等级是什么意思_returns_type0():
    """「耕地质量等级是什么意思」应返回 type 0，而非 type 5"""
    from framework.agents.nodes import identify_question_type
    qt, _ = identify_question_type("耕地质量等级是什么意思")
    assert qt == 0, f"知识性问题期望 type 0，实际 type {qt}"


def test_identify_解释有机质_returns_type0():
    """「解释土壤有机质」应返回 type 0，而非 type 4"""
    from framework.agents.nodes import identify_question_type
    qt, _ = identify_question_type("解释土壤有机质")
    assert qt == 0, f"知识性问题期望 type 0，实际 type {qt}"


def test_diagnostic_我的田质量等级_仍返回_type2():
    """「我的田耕地质量等级是多少」应返回 type 2（质量等级）。

    question_type 编号对齐后：type=2 → 质量等级 → model-5
    """
    from framework.agents.nodes import identify_question_type
    qt, _ = identify_question_type("我的田耕地质量等级是多少")
    assert qt == 2, f"诊断性问题期望 type 2，实际 type {qt}"


def test_diagnostic_我的田酸化严重吗_仍返回_type4():
    """「我的田酸化严重吗」应返回 type 4（酸化改良）。

    question_type 编号对齐后：type=4 → 酸化改良 → model-2
    """
    from framework.agents.nodes import identify_question_type
    qt, _ = identify_question_type("我的田酸化严重吗")
    assert qt == 4, f"诊断性问题期望 type 4，实际 type {qt}"


def test_knowledge_question_relevance_is_high():
    """知识性问题返回的 relevance 应为高值（1.0），确保走 RAG 而非被低相关性过滤"""
    from framework.agents.nodes import identify_question_type
    _, rel = identify_question_type("什么是土壤酸化")
    assert rel >= 0.7, f"知识性问题 relevance 应 >= 0.7，实际 {rel}"


if __name__ == "__main__":
    test_knowledge_start_pattern_什么是()
    test_knowledge_start_pattern_何为()
    test_knowledge_start_pattern_解释()
    test_knowledge_contain_pattern_是什么意思()
    test_knowledge_contain_pattern_什么意思()
    test_knowledge_contain_pattern_定义()
    test_knowledge_contain_pattern_概念()
    test_knowledge_contain_pattern_含义()
    test_diagnostic_question_质量等级_是多少()
    test_diagnostic_question_酸化严重吗()
    test_diagnostic_question_稳定吗()
    test_diagnostic_question_肥力怎么样()
    test_diagnostic_question_施肥量()
    test_knowledge_empty_string()
    test_knowledge_none_input()
    test_identify_什么是土壤酸化_returns_type0()
    test_identify_耕地质量等级是什么意思_returns_type0()
    test_identify_解释有机质_returns_type0()
    test_diagnostic_我的田质量等级_仍返回_type5()
    test_diagnostic_我的田酸化严重吗_仍返回_type2()
    test_knowledge_question_relevance_is_high()
    print("\n全部知识性问题检测测试通过！")
