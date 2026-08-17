"""Pytest 全局配置：统一注入项目根目录和 src/ 到 sys.path。

避免不同测试文件合并跑时，因 sys.path 顺序差异导致 framework.agents.specialized
在加载阶段触发 ai_culti_demo 导入失败，进而把 STABILITY_MODEL_AVAILABLE /
FARMland_DIAGNOSIS_AVAILABLE 等模块级常量冻结为 False（model_unavailable）。
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


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
