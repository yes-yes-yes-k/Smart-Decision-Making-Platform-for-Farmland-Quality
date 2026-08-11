"""LLM 路由判定测试：覆盖开关、可用性、解析失败回退、越界回退、排他规则叠加。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def test_routing_mode_default_is_llm(monkeypatch):
    """默认 ROUTING_MODE 为 llm。"""
    monkeypatch.delenv("ROUTING_MODE", raising=False)
    # 强制重新读取 Config（类属性在模块加载时已绑定，故用直接断言默认值）
    from framework.config import Config
    assert Config.ROUTING_MODE == "llm"


def test_routing_mode_reads_env(monkeypatch):
    """ROUTING_MODE 环境变量覆盖默认值。

    Config.ROUTING_MODE 在类定义时绑定，故通过重新加载 config 模块验证。
    """
    import importlib
    monkeypatch.setenv("ROUTING_MODE", "keyword")
    import framework.config as _cfg
    importlib.reload(_cfg)
    assert _cfg.Config.ROUTING_MODE == "keyword"
    # 还原
    monkeypatch.delenv("ROUTING_MODE", raising=False)
    importlib.reload(_cfg)
