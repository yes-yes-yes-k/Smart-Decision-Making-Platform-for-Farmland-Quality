"""测试耕地领域关键词路由。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.rag.category_router import route_category


def test_route_acidification():
    assert route_category("我的田酸化严重吗") == "acidification"


def test_route_organic_matter():
    assert route_category("如何提升有机质") == "organic_matter"


def test_route_grade():
    assert route_category("这块地质量等级是多少") == "grade"


def test_route_problem():
    assert route_category("耕地有什么障碍因素") == "problem"


def test_route_stability():
    assert route_category("等级稳定性如何") == "stability"


def test_route_unknown_returns_none():
    assert route_category("今天天气怎么样") is None
    assert route_category("") is None
    assert route_category(None) is None