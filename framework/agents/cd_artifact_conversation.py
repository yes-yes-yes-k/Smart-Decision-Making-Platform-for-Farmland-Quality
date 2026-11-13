"""Use the last validated Cd query for explicit attachment follow-ups."""
import re

from flask import current_app

from framework.api.services import cd_chat_artifacts


CHART = re.compile(
    r"(?:请)?(?:把刚才的?(?:数据|结果))?(?:画成图|画图|画地图|生成(?:分布图|地图|直方图))"
    r"(?P<raster>并导出(?:GeoTIFF|栅格))?(?:[，, ]*(?:并)?使用(?P<method>最近邻|线性|三次)插值)?[。！!]?",
    re.I,
)
EXPORT = re.compile(r"(?:请)?(?:下载刚才的?(?:数据|结果)|导出(?:刚才的?(?:数据|结果)|CSV))[。！!]?", re.I)
METHODS = {"最近邻":"nearest", "线性":"linear", "三次":"cubic"}
MESSAGES = {
    "no_data": "该查询范围没有可用的 Cd 数据。",
    "no_data_in_template": "有效点均不在制图模板的覆盖范围内。",
    "too_many_rows": "CSV 导出最多支持 10 万行，请缩小查询范围。",
    "unsupported_flux_chart_option": "通量图支持地图和直方图。插值与 GeoTIFF 适用于预测图。",
    "choose_single_year": "请先查询要制图的单一年度。",
    "artifact_not_found": "当前查询的会话记录已不可用，请重新查询。",
    "template_not_found": "当前缺少 Cd 制图模板。",
    "missing_render_dependency": "当前缺少 Cd 制图依赖。",
    "grid_too_large": "当前制图模板超过栅格大小上限。",
}


def answer_attachment(request, question):
    context = request.get("_cd_artifact_context")
    if context is None:
        return None
    chart = CHART.fullmatch(question.strip())
    export = EXPORT.fullmatch(question.strip()) is not None
    if not chart and not export:
        return None
    scope = context.get("scope")
    if not scope:
        return {"status":"ok","answer":"请先查询要制图或导出的 Cd 数据。"}
    obj = (request.get("analysis_context") or {}).get("object") or {}
    if ((obj.get("type") == "parcel" and str(obj.get("id")) != str(scope.get("parcel_id")))
        or (obj.get("type") in ("province","city","county","township") and
            (obj.get("type"),str(obj.get("id"))) != (scope.get("region_type"),str(scope.get("region_id"))))):
        return {"status":"ok","answer":"当前分析对象已切换，请先查询该对象的 Cd 数据。"}
    try:
        payload = cd_chat_artifacts.generate(
            request["user_id"], request["conversation_id"], context["revision"], scope,
            export=export, raster=bool(chart and chart["raster"]),
            interpolation=METHODS.get(chart["method"]) if chart else None,
        )
    except (ImportError, OSError, ValueError) as exc:
        reason = getattr(exc, "code", None) or str(exc)
        if isinstance(exc, ImportError):
            reason = "missing_render_dependency"
        answer = MESSAGES.get(reason, "Cd 附件暂时无法生成，请稍后重试。")
        return {"status":"ok","answer":answer,
                "model_results":{"models":{"cd_conversation":{"status":"artifact_failed","reason":
                    reason if reason in MESSAGES or reason == "missing_render_dependency" else "generation_failed"}}}}
    except Exception:
        current_app.logger.exception("Cd attachment generation failed")
        return {"status":"ok","answer":"Cd 附件暂时无法生成，请稍后重试。",
                "model_results":{"models":{"cd_conversation":{"status":"artifact_failed","reason":"generation_failed"}}}}
    answer = "CSV 已生成，可在附件中下载。" if export else "Cd 地图和直方图已生成。"
    if payload["metadata"].get("truncated"):
        answer += " 地图按点数上限截断，详情见附件元信息。"
    return {"status":"ok","answer":answer,"model_results":{"models":{"cd_conversation":payload}}}
