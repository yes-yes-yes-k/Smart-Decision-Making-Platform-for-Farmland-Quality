"""Chat adapter for the migrated cadmium services."""

import math
import json
import re
from contextvars import ContextVar
from typing import Literal

from langchain_core.tools import StructuredTool

from framework.function_calling.registry import tool_registry
from framework.domain.other_models.cd_parameter_contract import FIELD_DEFINITIONS


FLUX_COMPONENTS = ("灌溉水", "农业投入品", "大气沉降", "企业输入", "粮食移除", "秸秆移除", "渗漏", "径流")
ADMIN_LEVELS = ("province", "city", "county", "township")
CAPABILITIES = {
    'flux': {
        'status':'available', 'data_category':'annual_flux_and_independent_trial',
        'levels':(*ADMIN_LEVELS,'parcel'), 'time':'明确业务年度，未知年度单列；试算跨度一年',
        'operations':['flux','flux_results','flux_parameters','flux_predict','flux_compare'],
        'coverage':'查询受实际记录和归属映射限制；企业未知不填零；管理导入与业务重算不开放给对话',
        'unit':'分项g/ha/a，初始储量g/ha，末期浓度mg/kg需完整单位条件',
    },
    "soil": {
        "status": "available", "indicator": "cadmium", "data_category": "soil_snapshot",
        "levels": (*ADMIN_LEVELS, "parcel"), "time": "年度快照",
        "unit": "mg/kg", "coverage": "由有效地块、相交面积和快照记录决定",
    },
    "results": {
        "status": "available", "indicator": ("crop_cd", "effective_cd"), "data_category": "prediction",
        "levels_by_source": {"native": ADMIN_LEVELS, "ported": ("township",)},
        "time": "时期未知，不能按年筛选", "unit_status": "unverified",
        "coverage": "由预测记录和来源对应的区域映射决定",
    },
    "parameters": {
        "status": "partial", "data_category": "model_contract_and_parcel_parameters",
        "levels": ("parcel",), "time": "当前地块记录或指定年度快照",
        "reason": "模型定义可查，地块参数限已确认映射，行政区参数暂不可查",
    },
    "predict": {
        "status": "available", "data_category": "parameter_prediction",
        "levels": (), "time": "情景参数计算", "unit_status": "unverified",
        "required_input": "所选模型的完整输入字段",
    },
}
CD_INTENT = re.compile(r"镉|土壤污染物|重金属.*通量|(?<![a-z])(?:crop_cd|effective_cd|cd)(?![a-z])", re.I)
CD_FOLLOWUP = re.compile(r"重算|重新计算|补参|改成|改为|换成|上一组|(?:^|\s)[a-z_]+\s*[=:：]", re.I)
CD_SAVE = re.compile(
    r"(?:请(?:帮我)?)?(?:(?:保存|存档)(?:一下)?(?:这次|本次|当前|刚才的?)?"
    r"(?:(?:Cd|镉)\s*)?(?:试算(?:结果)?|计算结果|预测结果|结果)?"
    r"|(?:把|将)(?:这次|本次|当前|刚才的?)?(?:(?:Cd|镉)\s*)?"
    r"(?:试算(?:结果)?|计算结果|预测结果|结果)(?:保存|存档)(?:一下)?)[。！!\s]*",
    re.I,
)
_draft_context: ContextVar[dict | None] = ContextVar("cd_draft_context", default=None)
_default_accepted: ContextVar[bool] = ContextVar("cd_default_accepted", default=False)
CD_ACCEPT_DEFAULT = re.compile(r"(?:我)?(?:同意|确认|接受)(?:使用|采用)?(?:模型)?(?:训练集中位数|训练集默认值)[。！!]?")


def query_cd(
    operation: Literal["capabilities", "soil", "results", "parameters", "predict", "flux", "flux_parameters", "flux_predict", "flux_results", "flux_compare"],
    model_id: Literal["crop_cd", "effective_cd"] | None = None,
    year: int | None = None,
    region_name: str | None = None,
    parameters: dict[str, float] | None = None,
    parcel_id: str | None = None,
    region_id: str | None = None,
    region_type: str | None = None,
    parameter_units: dict[str, str] | None = None,
    source: Literal['all','native','ported','unknown'] | None = None,
    field: Literal['in_cd','out_cd','net_cd','end_cd'] | None = None,
    years: list[int] | None = None,
    all_regions: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """查询 Cd 能力、统计、模型参数或运行参数级预测。通量请求使用 flux。"""
    if operation.startswith('flux'):
        from .cd_flux_conversation import query
        payload = query(operation,_draft_context.get(),year=year,region_name=region_name,parameters=parameters,
                     parcel_id=parcel_id,region_id=region_id,region_type=region_type,parameter_units=parameter_units,
                     source=source,field=field,years=years,all_regions=all_regions,limit=limit,offset=offset)
        return json.loads(json.dumps(payload,default=str))
    if operation == 'capabilities':
        return {
            "status": "unavailable" if operation == "flux" else "ok",
            "operations": ["soil", "results", "parameters", "predict"],
            "capabilities": CAPABILITIES,
            "flux": dict.fromkeys(FLUX_COMPONENTS, "支持八项定义、年度查询及纯试算；实际值由数据覆盖决定"),
            "flux_operations": ['flux','flux_parameters','flux_predict','flux_results','flux_compare'],
        }
    if operation == "soil" and parcel_id:
        from framework.api.services.farmland_statistics import get_parcel_summary

        result = get_parcel_summary(parcel_id, year=year, metric_key="cadmium")
        return {**result, "status": "ok" if result["metric"]["value"] is not None else "no_data"}
    if operation in {"soil", "results"} and not region_id and region_name and not parcel_id:
        from framework.models import db
        from framework.models.thematic_model import SpatialRegionCatalog as Region

        candidates = db.session.query(
            Region.object_type, Region.object_id, Region.display_name, Region.parent_object_id,
        ).filter_by(enabled=True, display_name=region_name).limit(10).all()
        if len(candidates) != 1:
            return {"status": "needs_analysis_object", "candidates": [list(row) for row in candidates]}
        region_type, region_id, _, _ = candidates[0]
    if operation == "soil":
        from framework.api.services.farmland_statistics import aggregate_statistics

        if not region_id:
            return {"status": "needs_analysis_object"}
        result = aggregate_statistics({
            "scope": {"type": "administrative_region", "region_type": region_type, "region_id": region_id},
            "metrics": ["cadmium"], "year": year,
        })
        has_data = any(metric["table"]["validParcelCount"] for metric in result["metrics"])
        return {"statistics_method": "相交面积加权均值", "status": "ok" if has_data else "no_data", **result}
    if operation == "results":
        from framework.domain.other_models import heavy_metal_cd_spatial as spatial

        if year is not None:
            return {"status": "unsupported_year", "message": "预测记录时期未知。是否查看时期未知的数据？"}
        if not model_id or not region_id:
            return {"status": "needs_input", "message": "请指定区域以及作物或土壤有效态 Cd。"}
        sources = {}
        for source in ("native", "ported"):
            stats = spatial.region_statistics(model_id, region_type, region_id, source=source)
            if stats.get("ported_unavailable_for_region_type"):
                status = "unsupported_region_level"
            else:
                status = "ok" if stats.get("has_data") else "no_data"
            sources[source] = {**stats, "status": status}
        return {
            "statistics_method": "记录算术均值及中位数", "period": "未知",
            "sources": sources,
            "artifact_scope": {"category":"prediction","model_id":model_id,"source":"all",
                               "region_type":region_type,"region_id":region_id,"period":"未知"},
        }
    from framework.domain.other_models import heavy_metal_cd as models

    previous = _draft_context.get() or {}
    if operation == "predict":
        model_id = model_id or previous.get("model_id")
        if year is None:
            year = previous.get("year")
        region_name = region_name or previous.get("region_name")
    contracts = models.available_models()
    if not model_id:
        return {"status": "needs_model", "models": contracts}
    contract = next(item for item in contracts if item["model_id"] == model_id)
    fields = contract["input_fields"]
    if operation == "parameters":
        result = {
            "model": contract,
            "parameter_definitions": {
                field: {"label": FIELD_DEFINITIONS[field][0], "unit": FIELD_DEFINITIONS[field][1],
                        "unit_status": "documented" if FIELD_DEFINITIONS[field][1] else "unverified"}
                for field in fields
            },
            "applicability": "同一地块及时期的模型特征；地区汇总值不能直接替代地块特征",
        }
        if parcel_id:
            from framework.domain.other_models.heavy_metal_cd_db import build_inputs

            result["parcel_parameters"] = build_inputs(parcel_id, model_id, year=year)
        elif region_name or region_id:
            result.update(parameter_status="unsupported_region_level", missing_fields=fields)
        return result
    scope = {"parcel_id": parcel_id, "region_id": region_id, "region_type": region_type,
             "region_name": region_name, "year": year, "model_id": model_id}
    same_scope = all(previous.get(k) == v for k, v in scope.items())
    values = dict(previous.get("parameters", {})) if same_scope else {}
    units = dict(previous.get("parameter_units", {})) if same_scope else {}
    provenance = dict(previous.get("parameter_sources", {})) if same_scope else {}
    lookup_status = previous.get("parameter_lookup_status") if same_scope else None
    if parcel_id and not same_scope:
        from framework.domain.other_models.heavy_metal_cd_db import build_inputs

        lookup = build_inputs(parcel_id, model_id, year=year)
        lookup_status = lookup["status"]
        for field, value in lookup["data"].items():
            source = lookup["provenance"].get(field)
            metadata = source if isinstance(source, dict) else {"data_source": source}
            source_name = metadata.get("data_source", metadata.get("dataSource"))
            measured_year = metadata.get("measurement_year", metadata.get("measurementYear"))
            imputed = metadata.get("is_imputed", metadata.get("isImputed"))
            unit = FIELD_DEFINITIONS[field][1]
            if source_name != "measured" or imputed or (year and measured_year not in (None, year)):
                continue
            if unit is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            values[field] = float(value)
            units[field] = unit
            provenance[field] = {"source": source_name, "parcel_id": parcel_id, "year": year,
                                 "measurement_year": measured_year}
    elif (region_id or region_name) and not parcel_id:
        lookup_status = "unsupported_region_level"
    values.update(parameters or {})
    for field in parameters or {}:
        units.pop(field, None)
        provenance[field] = {"source": "user_provided"}
    units.update(parameter_units or {})
    values = {field: values[field] for field in contract["input_fields"]
              if field in values and math.isfinite(values[field])}
    units = {field: units[field] for field in values if field in units}
    provenance = {field: provenance.get(field, {"source": "user_provided"}) for field in values}
    draft = {**scope, "parameters": values, "parameter_units": units,
             "parameter_sources": provenance, "parameter_lookup_status": lookup_status}
    missing = [field for field in fields if field not in values]
    accepted_default = _default_accepted.get() and missing in (["solution"], ["cdsolution"])
    issues = {}
    for field, value in values.items():
        expected = FIELD_DEFINITIONS[field][1]
        if expected is None and units.get(field) != "model_native":
            issues[field] = "训练单位未核验，需要用户确认输入已采用模型原始标度"
        elif expected is not None and units.get(field) != expected:
            issues[field] = f"请确认使用模型输入单位 {expected}"
        elif (value < 0 and field not in {"solution", "cdsolution"}) or (expected == "%" and value > 100):
            issues[field] = "数值超出输入允许范围"
    if (missing and not accepted_default) or issues:
        return {"status": "needs_scenario_inputs", "missing_fields": missing,
                "input_issues": issues, "model": contract, "draft": draft, "parameter_lookup_status": lookup_status,
                "default_confirmation": "同意使用训练集中位数" if missing in (["solution"], ["cdsolution"]) else None}
    prediction = models.predict(model_id, values)
    actual_values, actual_units, actual_sources = dict(values), dict(units), dict(provenance)
    if accepted_default and prediction["status"] == "degraded":
        field = missing[0]
        assumed = prediction["assumed_fields"][field]
        actual_values[field] = assumed["value"]
        actual_units[field] = "无量纲"
        actual_sources[field] = {"source": "accepted_training_median", **assumed}
    return {"inputs": actual_values, "input_units": actual_units, "model_version": contract["artifact_checksums"],
            "input_sources": actual_sources, **prediction, "draft": draft}


_TOOL = StructuredTool.from_function(query_cd, name="cd_conversation_query")
tool_registry.register(_TOOL.name, _TOOL)


def answer_cd(request: dict, history: list | None) -> dict | None:
    question = str(request.get("question") or "")
    previous = request.get("_cd_draft")
    from .cd_flux_conversation import accepted,parse_acceptance
    flux_acceptance = parse_acceptance(question)
    accepts_default = bool(previous and (CD_ACCEPT_DEFAULT.fullmatch(question.strip()) or flux_acceptance))
    if CD_SAVE.fullmatch(question.strip()) and (previous or CD_INTENT.search(question)):
        return _save_cd_answer(request)
    from .cd_artifact_conversation import answer_attachment
    attachment = answer_attachment(request, question)
    if attachment is not None:
        return attachment
    if not CD_INTENT.search(question) and not accepts_default and not (previous and CD_FOLLOWUP.search(question)):
        return None

    from framework.llm.service import llm_service
    from framework.config import Config

    if not getattr(Config, "FUNCTION_CALLING_ENABLED", True):
        return {"status": "ok", "answer": "当前未启用 Cd 对话工具。"}

    obj = (request.get("analysis_context") or {}).get("object") or {}
    identifiers = request.get("validated_identifiers") or {}
    scope = {
        "parcel_id": identifiers.get("parcel_id"),
        "region_id": obj.get("id") if obj.get("type") in ADMIN_LEVELS else None,
        "region_type": obj.get("type") if obj.get("type") in ADMIN_LEVELS else None,
    }
    token = _draft_context.set(previous)
    default_token = _default_accepted.set(accepts_default)
    flux_token = accepted.set(flux_acceptance)
    try:
        result = _generate_cd_answer(llm_service, question, history, scope, previous)
    finally:
        _draft_context.reset(token)
        _default_accepted.reset(default_token)
        accepted.reset(flux_token)
    payload = (result.get("tool_results") or result.get("partial_results") or {}).get(_TOOL.name)
    if not payload:
        if not result.get("success") or any(not call["success"] for call in result.get("tool_calls_trace", [])):
            return {"status": "ok", "answer": "Cd 服务暂时无法完成查询或计算，请稍后重试。",
                    "_cd_artifact_scope": None,
                    "model_results": {"models": {"cd_conversation": {"status": "service_unavailable"}}}}
        return {"status": "ok", "answer": "暂未取得 Cd 服务结果。请明确地区、指标与查询或计算需求。",
                "_cd_artifact_scope": None}
    draft = payload.get("draft")
    payload = dict(payload)
    artifact_scope = payload.pop("artifact_scope", None)
    answer = {
        "no_data": "指定范围内没有可用的 Cd 数据。",
        "unsupported_year": payload.get("message"),
        "unavailable": "该 Cd 通量服务尚未接入。",
        "service_unavailable": "Cd 服务暂时无法完成查询或计算，请稍后重试。",
        "needs_analysis_object": "请明确地区、地块或全域范围；如有同名地区，请选择具体对象。",
        "needs_scenario_inputs": "请补充或核对本次计算所需的参数、年度与单位。",
        "partial": "已返回已知通量分项小计，仍有缺项，尚不能给出完整净收支或末期浓度。",
    }.get(payload.get("status"))
    return {
        "status": "ok",
        "answer": answer or result.get("content") or "Cd 服务已返回结构化结果。",
        "model_results": {"models": {"cd_conversation": payload}},
        "_cd_draft": draft,
        "_cd_artifact_scope": artifact_scope,
    }


def _generate_cd_answer(llm_service, question, history, scope, previous):
    return llm_service.generate_with_tools(
        prompt=(
            "只使用 Cd 工具返回的事实。遇到指标、实测或预测类别、区域或参数单位歧义时追问。"
            "不得猜测地区 ID、参数、单位或默认值。地区名称使用完整名称。"
            "明确实际统计口径、覆盖、来源、时期和单位状态。"
            "预测结果按来源分别展示有效记录数和已归属地块数。区分该层级不受支持与该范围无记录。"
            "参数计算前确认输入单位，不得用此前助手的文本作为参数值来源。"
            "parameter_units 仅传用户明确确认的单位。只有用户确认采用原训练标度时，未核验字段才传 model_native。"
            "作物或有效态预测补参或重算时调用 predict，parameters 只传本轮用户明确提供的值。"
            "通量查询调用flux，明细flux_results，参数flux_parameters，试算及补参flux_predict，年度对比flux_compare。"
            "用户要求试算时必须调用 flux_predict 才能给出计算结果。"
            "用地块已有记录试算时直接调用 flux_predict，传年度和来源，parameters 留空，让服务读取已记录值。"
            "flux_parameters 只用于参数查询，不得用该操作代替试算或把记录值复制为用户输入。"
            "全域仅在用户明确要求时传all_regions=true。企业未知不能填零。通量跨度一年，须明确情景year。"
            "通量默认接受须用户原话为：同意使用通量默认值：字段名（多项逗号分隔），服务端校验，不能自行接受。"
            "只提供partial或缺项时追问，不宣称已完成完整试算。禁止导入和业务覆盖重算。"
            f"当前通量草稿为 {previous if (previous or {}).get('calculation_type') == 'flux' else None}。"
            "只缺溶液态镉对数值且用户明确同意训练集中位数时，调用 predict 并保留该缺项，由服务填充并标记降级。"
            "切换年份或地区时传入新值。"
            f"当前 Cd 参数草稿模型为 {(previous or {}).get('model_id')}。"
            "输出简短结论，适合比较时使用表格。\n"
            f"用户问题：{question}"
        ),
        messages=history,
        tools=[_TOOL],
        default_args=scope,
        restrict_tools=True,
    )


def _save_cd_answer(request: dict) -> dict:
    from sqlalchemy.exc import SQLAlchemyError

    from framework.api.services.cd_trial import save_trial
    from framework.models import db

    message_id = request.get("_cd_trial_message_id")
    user_id = request.get("user_id")
    conversation_id = request.get("conversation_id")
    try:
        record_id = save_trial(user_id, conversation_id, message_id) if all((user_id, conversation_id, message_id)) else None
    except SQLAlchemyError:
        db.session.rollback()
        return {"status": "ok", "answer": "Cd 试算保存暂不可用，请稍后重试。"}
    if record_id is None:
        return {"status": "ok", "answer": "当前没有可保存的 Cd 试算结果，请先完成计算。"}
    return {"status": "ok", "answer": f"已保存 Cd 试算，记录编号为 {record_id}。",
            "model_results": {"models": {"cd_conversation": {"status": "saved", "record_id": record_id}}}}
