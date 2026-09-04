"""framework.observability：本地路由可观测性（日志/指标/追溯/看板）。

复用 framework/upload/audit_logger.py 的 JSON 行式落盘范式，纯 Python 实现，无新增依赖。
与 LangSmith 远端 trace 并行覆盖，共享同一 trace_id。
"""
from . import routing_log
from . import metrics
from . import dashboard
from . import traceability
from . import observe
from . import analysis_context_metrics

__all__ = [
    "routing_log", "metrics", "dashboard", "traceability", "observe",
    "analysis_context_metrics",
]
