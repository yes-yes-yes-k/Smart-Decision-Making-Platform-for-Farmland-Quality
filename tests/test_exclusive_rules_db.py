"""排他规则动态加载测试（PostgreSQL 测试库）。

覆盖五条路径：
1. from_database() 加载 enabled 规则并转换为 ExclusiveRule 元组
2. DB 不可用（session 抛异常）回退硬编码 EXCLUSIVE_RULES
3. DB 为空回退硬编码 EXCLUSIVE_RULES
4. DB 规则与硬编码规则判定一致（同输入同输出）
5. refresh_rules_cache() 使新插入的规则立即可见

PG 不可用时整个文件跳过（conftest.PG_AVAILABLE 控制）。
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import PG_AVAILABLE

pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL 测试库不可用")

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models import ExclusiveRuleConfig  # noqa: E402
from framework.agents.exclusive_rules import (  # noqa: E402
    from_database, _get_active_rules, refresh_rules_cache,
    EXCLUSIVE_RULES, apply_exclusive_rules,
)


@pytest.fixture
def pg_app():
    """真实 PG 测试库 app context，前后清空 exclusive_rule_config 表并重置缓存。"""
    app = create_app("default")
    with app.app_context():
        db.session.query(ExclusiveRuleConfig).delete()
        db.session.commit()
        # 重置缓存，确保每个测试从干净状态开始
        refresh_rules_cache()
        yield app
        db.session.query(ExclusiveRuleConfig).delete()
        db.session.commit()
        refresh_rules_cache()


def _insert_rule(rule_name, pair, discriminator, target, condition=None,
                 dimension_conditions=None):
    """插入一条 enabled 测试规则。"""
    row = ExclusiveRuleConfig(
        rule_name=rule_name,
        rule_pair=list(pair),
        discriminator=discriminator,
        condition=condition,
        target=target,
        dimension_conditions=dimension_conditions or {},
        enabled=True,
    )
    db.session.add(row)
    db.session.commit()


class TestExclusiveRulesDb:
    def test_from_database_loads(self, pg_app):
        """插入测试规则，验证 from_database() 返回正确规则。"""
        _insert_rule("test-rule-1", frozenset({"model-2", "model-3"}),
                     "业务任务", "model-3", condition="现状评价")
        refresh_rules_cache()
        rules = from_database()
        assert len(rules) == 1
        r = rules[0]
        assert r.target == "model-3"
        assert "model-2" in r.pair and "model-3" in r.pair
        assert r.condition == "现状评价"

    def test_db_unavailable_fallback(self, pg_app, monkeypatch):
        """mock db.session.query 抛异常，验证 _get_active_rules() 回退 EXCLUSIVE_RULES。"""
        def _boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(db.session, "query", _boom)
        refresh_rules_cache()  # 清空缓存，强制下次重新加载
        rules = _get_active_rules()
        assert rules == EXCLUSIVE_RULES
        assert len(rules) == len(EXCLUSIVE_RULES)

    def test_db_empty_fallback(self, pg_app):
        """表为空时回退硬编码 EXCLUSIVE_RULES。"""
        # pg_app fixture 已 delete all
        refresh_rules_cache()
        rules = _get_active_rules()
        assert rules == EXCLUSIVE_RULES

    def test_db_rules_match_hardcoded_judgment(self, pg_app):
        """构造 DB 规则等价于硬编码规则，验证 apply_exclusive_rules 判定结果一致。"""
        # 把硬编码规则全部插入 DB
        for idx, r in enumerate(EXCLUSIVE_RULES):
            _insert_rule(
                f"hardcoded-{idx}",
                list(r.pair),
                r.discriminator,
                r.target,
                condition=r.condition,
                dimension_conditions=r.dimension_conditions,
            )
        refresh_rules_cache()

        # 对一组正反例验证 DB 路径判定
        test_cases = [
            ("我的田耕地质量等级是多少", {"scale": "地块"}, 2),  # → model-2
            ("我的田耕地障碍诊断如何", {"scale": "地块",
                                      "business_task": "障碍诊断",
                                      "expected_output": "诊断报告"}, 3),  # → model-3
        ]
        db_results = {}
        for question, context, expected_qtype in test_cases:
            final_type, status = apply_exclusive_rules(question, expected_qtype, context)
            assert status == "normal"
            assert final_type == expected_qtype
            db_results[question] = (final_type, status)

        # 删除 DB 规则切回硬编码路径，验证同输入同输出
        db.session.query(ExclusiveRuleConfig).delete()
        db.session.commit()
        refresh_rules_cache()
        for question, context, expected_qtype in test_cases:
            hardcoded_result = apply_exclusive_rules(question, expected_qtype, context)
            assert hardcoded_result == db_results[question]

    def test_refresh_rules_cache(self, pg_app):
        """调用 refresh_rules_cache() 后，新插入的规则立即可见。"""
        # 初始：DB 为空，回退硬编码
        refresh_rules_cache()
        assert _get_active_rules() == EXCLUSIVE_RULES
        # 插入一条新规则
        _insert_rule("refresh-test", frozenset({"model-2", "model-3"}),
                     "业务任务", "model-3", condition="现状评价")
        # 缓存未刷新：仍返回硬编码（空缓存非 None，不会重新加载）
        assert _get_active_rules() == EXCLUSIVE_RULES
        # 调用 refresh_rules_cache() 强制重新加载
        refresh_rules_cache()
        rules = _get_active_rules()
        assert len(rules) == 1
        assert rules[0].target == "model-3"
