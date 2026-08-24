"""Pytest 全局配置：统一注入项目根目录和 src/ 到 sys.path。

避免不同测试文件合并跑时，因 sys.path 顺序差异导致 framework.agents.specialized
在加载阶段触发 ai_culti_demo 导入失败，进而把 STABILITY_MODEL_AVAILABLE /
FARMland_DIAGNOSIS_AVAILABLE 等模块级常量冻结为 False（model_unavailable）。
"""
import os
import sys
import types

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


# geoalchemy2 DDL-safe 全局 stub：测试环境未安装 geoalchemy2 时，
# 用 String 类型实例代替 Geometry，既满足 SQLAlchemy Column 初始化所需
# 的 `_set_parent_with_dispatch` 协议，又能保证 db.create_all() 渲染 DDL
# 时 __str__ 返回真实字符串（MagicMock 会触发 TypeError）。
if "geoalchemy2" not in sys.modules:
    from sqlalchemy import String

    _geo_stub = types.ModuleType("geoalchemy2")

    class _Geometry:
        """DDL-safe stub：返回 String 类型实例，避免污染后续测试的 DDL 渲染。"""

        def __new__(cls, *args, **kwargs):
            return String()

    _geo_stub.Geometry = _Geometry
    sys.modules["geoalchemy2"] = _geo_stub


# PostgreSQL 测试库可用性探测：供 routing_log_db / exclusive_rules_db / regression_metrics_db 跳过
def _probe_pg_available() -> bool:
    try:
        from framework.api.app import create_app
        from framework.models.user import db
        app = create_app("default")
        with app.app_context():
            db.session.execute(__import__("sqlalchemy").text("SELECT 1"))
            return True
    except Exception:
        return False


PG_AVAILABLE = _probe_pg_available()


@pytest.fixture(autouse=True)
def _disable_function_calling_for_tests():
    """测试套件默认关闭 function calling，走关键词路由 fallback，保证确定性。

    FC 路径会调用真实 LLM（非确定性、慢、依赖网络与 API key）。FC 的组件级行为
    （Tool schema / wrapper / ToolCallingLoop / 降级分支）在 test_specialized_tools.py
    中以 mock llm 独立覆盖；端到端 FC 集成由 scripts/verify_dialogue.py 等脚本验证。

    需要 FC=True 的单测可在用例体内通过
    `monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", True)` 覆盖。
    """
    from framework.config import Config

    saved = getattr(Config, "FUNCTION_CALLING_ENABLED", True)
    Config.FUNCTION_CALLING_ENABLED = False
    try:
        yield
    finally:
        Config.FUNCTION_CALLING_ENABLED = saved
