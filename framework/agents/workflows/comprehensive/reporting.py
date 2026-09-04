"""Report generation with exact fact rendering and bounded revisions."""
from __future__ import annotations
import re
from typing import Any
from .contracts import EvidenceBundle, ReportPayload, ReportSection, TaskResult
from .prompt_catalog import REPORTER_PROMPT
from .structured_roles import StructuredRoleError

FACT_TOKEN=re.compile(r"\[\[fact:([a-z0-9_.-]+)\]\]")
RAW_NUMBER=re.compile(r"(?<![a-zA-Z\[])\d+(?:\.\d+)?")
REQUIRED_SECTION_IDS=("object-summary","execution-summary","quality","obstacles","conditional-specialty-results","priority-remediation","limitations","provenance")

PUBLIC_TERM_LABELS={
    "YTK":"土壤调理剂（亿土康）",
    "MBNT":"木本泥炭",
    "YXL":"有效磷",
    "DXBW":"地形部位",
    "SXJ":"速效钾",
    "GGNL":"灌溉能力",
    "SJD":"土壤酸碱度",
    "PSNL":"排水能力",
    "ZDGX":"质地构型",
    "YJZ":"有机质",
    "TRRZ":"土壤容重",
    "YXTCHD":"有效土层厚度",
    "GCHD":"耕层厚度",
    "GCZD":"耕层质地",
    "model-2":"耕地质量评价",
    "model-3":"障碍因素诊断",
    "model-4":"酸化改良测算",
    "model-5":"有机质培肥测算",
}
PUBLIC_TITLE_LABELS={
    "条件专项结果":"改良用量建议",
    "限制与降级":"使用说明",
    "数据与模型溯源":"数据说明",
}
PRIVATE_WORKFLOW_LINE=re.compile(
    r"节点状态|执行节点|trace(?:_id)?|checkpoint|Coordinator|TrafficGate|InputResolver|"
    r"PlanValidator|Wave\s*[12]|TriggerEvaluator|EvidenceResearcher|Reporter|Release",
    re.IGNORECASE,
)
STATUS_MARKER=re.compile(
    r"[（(\[]\s*(?:ok|succeeded|done|released|approved|drafted|resolved|completed)\s*[)）\]]",
    re.IGNORECASE,
)


def user_facing_text(text:str,*,fallback:str="相关分析已完成，以下结果可供地块管理参考。")->str:
    """Remove workflow internals and translate model codes in report-only text."""
    visible=[]
    for line in str(text).splitlines():
        if PRIVATE_WORKFLOW_LINE.search(line):
            continue
        line=STATUS_MARKER.sub("",line)
        for technical,label in PUBLIC_TERM_LABELS.items():
            line=re.sub(rf"(?<![A-Za-z0-9_-]){re.escape(technical)}(?![A-Za-z0-9_-])",label,line,flags=re.IGNORECASE)
        visible.append(line.rstrip())
    rendered="\n".join(visible).strip()
    return rendered or fallback


def flatten_scalar_payload(value:Any,*,prefix:str=""):
    out={}
    if isinstance(value,dict):
        for key,item in value.items(): out.update(flatten_scalar_payload(item,prefix=f"{prefix}.{key}" if prefix else key))
    elif isinstance(value,(str,int,float,bool)) and not isinstance(value,bool): out[prefix]=value
    return out
def format_fact(value,unit=None,*,fact_key=""):
    if isinstance(value,float):
        if fact_key.endswith("composite_index"):
            rendered=f"{value:.3f}".rstrip("0").rstrip(".")
        elif any(term in fact_key for term in (
            "dosage", ".dose", ".ytk", ".mbnt", ".YTK", ".MBNT",
        )):
            rendered=f"{value:.1f}".rstrip("0").rstrip(".")
        else:
            rendered=f"{value:.3f}".rstrip("0").rstrip(".")
    else:
        rendered=str(value)
    return f"{rendered} {unit}" if unit else rendered
def build_fact_table(results:dict[str,TaskResult])->dict[str,str]:
    table={}
    for result in results.values():
        if result.status=="succeeded":
            for key,value in flatten_scalar_payload(result.payload).items():
                fact_key=f"{result.agent_id}.{key}"
                table[fact_key]=format_fact(value,fact_key=fact_key)
    return table


class ReportPolicyError(ValueError): pass
class ReportRevisionLimit(ValueError): pass


class ReportPolicyValidator:
    def validate_and_render(self,payload:ReportPayload,*,task_results:dict[str,TaskResult],evidence:EvidenceBundle)->str:
        ids=[s.section_id for s in payload.sections]
        if ids!=list(REQUIRED_SECTION_IDS): raise ReportPolicyError("required_sections")
        facts=build_fact_table(task_results); sources={x.source_id for x in evidence.items}
        rendered=[]
        for section in payload.sections:
            text=section.prose_template
            tokens=set(FACT_TOKEN.findall(text))
            if tokens != set(section.fact_refs): raise ReportPolicyError("fact_reference_mismatch")
            if any(ref not in facts for ref in tokens): raise ReportPolicyError("unknown_fact_reference")
            without_tokens=FACT_TOKEN.sub("",text)
            if RAW_NUMBER.search(without_tokens): raise ReportPolicyError("raw_number_forbidden")
            if any(source not in sources for source in section.source_ids): raise ReportPolicyError("unknown_source")
            text=FACT_TOKEN.sub(lambda m:facts[m.group(1)],text)
            title=PUBLIC_TITLE_LABELS.get(section.title,section.title)
            rendered.append(f"## {user_facing_text(title,fallback='诊断结果')}\n\n{user_facing_text(text)}")
        return f"# {user_facing_text(payload.title,fallback='地块综合诊断与改良建议')}\n\n"+"\n\n".join(rendered)


class Reporter:
    def __init__(self,runner,validator:ReportPolicyValidator): self._runner,self._validator=runner,validator
    def compose(self,*,task_results:dict[str,TaskResult],evidence:EvidenceBundle,degradations:tuple[str,...]=(),revision_comment:str=""):
        prompt=f"{REPORTER_PROMPT.system}\nresults={[r.model_dump(mode='json') for r in task_results.values()]}\nevidence={evidence.model_dump(mode='json')}\ndegradations={degradations}\nrevision={revision_comment}"
        try:
            payload=self._runner.generate(role="reporter",prompt=prompt,schema=ReportPayload)
        except StructuredRoleError:
            payload=self._deterministic_payload(task_results, degradations)
        return payload,self._validator.validate_and_render(payload,task_results=task_results,evidence=evidence)
    def revise(self,*,current_revision_count:int,**kwargs):
        if current_revision_count>=3: raise ReportRevisionLimit("report_revision_limit")
        payload,rendered=self.compose(**kwargs)
        return payload,rendered,current_revision_count+1

    @staticmethod
    def _deterministic_payload(
        task_results: dict[str, TaskResult], degradations: tuple[str, ...]
    ) -> ReportPayload:
        by_agent = {
            result.agent_id: result
            for result in task_results.values()
            if result.status == "succeeded"
        }

        def translated_factors(values: Any) -> str:
            if not isinstance(values, (list, tuple)):
                return ""
            labels = [PUBLIC_TERM_LABELS.get(str(value), str(value)) for value in values]
            return "、".join(labels)

        quality = by_agent.get("model-2")
        if quality and {
            "quality_grade", "composite_index",
        }.issubset(quality.payload):
            quality_text = (
                "耕地质量等级为 [[fact:model-2.quality_grade]] 级，"
                "综合指数为 [[fact:model-2.composite_index]]。"
            )
            quality_refs = (
                "model-2.quality_grade", "model-2.composite_index",
            )
        else:
            quality_text = "本轮质量评价未形成可用结果，建议复核基础数据后重试。"
            quality_refs = ()

        diagnosis = by_agent.get("model-3")
        if diagnosis and "obstacle_type" in diagnosis.payload:
            primary = translated_factors(diagnosis.payload.get("primary_factors"))
            secondary = translated_factors(diagnosis.payload.get("secondary_factors"))
            factor_text = ""
            if primary:
                factor_text += f"主要关注{primary}。"
            if secondary:
                factor_text += f"同时关注{secondary}。"
            obstacle_text = (
                "当前障碍类型为 [[fact:model-3.obstacle_type]]。" + factor_text
            )
            obstacle_refs = ("model-3.obstacle_type",)
        else:
            obstacle_text = "本轮未形成可用的障碍诊断结果。"
            obstacle_refs = ()

        specialty_parts: list[str] = []
        specialty_refs: list[str] = []
        acidification = by_agent.get("model-4")
        if acidification:
            for keys, label in (
                (("soil_conditioner_dosage", "ytk", "YTK"), "土壤调理剂（亿土康）"),
                (("woody_peat_dosage", "mbnt", "MBNT"), "木本泥炭"),
            ):
                key = next(
                    (candidate for candidate in keys if acidification.payload.get(candidate) is not None),
                    None,
                )
                if key:
                    specialty_parts.append(
                        f"{label}建议施用量为 [[fact:model-4.{key}]] 公斤/公顷。"
                    )
                    specialty_refs.append(f"model-4.{key}")
        organic = by_agent.get("model-5")
        if organic:
            dose_key = next(
                (key for key in ("dose_prediction", "dose") if key in organic.payload),
                None,
            )
            if dose_key:
                specialty_parts.append(
                    "有机质培肥建议施用量为 "
                    f"[[fact:model-5.{dose_key}]] 吨/公顷。"
                )
                specialty_refs.append(f"model-5.{dose_key}")
        specialty_text = "".join(specialty_parts) or "本轮没有触发专项改良用量测算。"

        limitation_text = (
            "当前未接入外部资料检索，报告以地块数据库和专业计算结果为准；"
            "实施前建议结合现场调查和最新土样复核。"
            if degradations
            else "实施前建议结合现场调查和最新土样复核。"
        )

        section_values = (
            ("object-summary", "分析对象", "本报告基于当前选中地块的权威数据生成。", ()),
            ("execution-summary", "诊断摘要", "已完成耕地质量、主要限制因素和改良用量分析。", ()),
            ("quality", "耕地质量", quality_text, quality_refs),
            ("obstacles", "主要限制因素", obstacle_text, obstacle_refs),
            ("conditional-specialty-results", "改良用量建议", specialty_text, tuple(specialty_refs)),
            ("priority-remediation", "优先改良措施", "优先处理主要限制因素，分步实施土壤改良，并保留施用和复测记录。", ()),
            ("limitations", "使用说明", limitation_text, ()),
            ("provenance", "数据说明", "结果由当前地块权威数据和已完成的专业计算生成。", ()),
        )
        return ReportPayload(
            title="地块综合诊断与改良建议",
            sections=tuple(
                ReportSection(
                    section_id=section_id,
                    title=title,
                    prose_template=prose,
                    fact_refs=fact_refs,
                )
                for section_id, title, prose, fact_refs in section_values
            ),
            degradations=degradations,
            prompt_version="reporter-deterministic-v1",
        )


class AggregateProvenanceBuilder:
    def __init__(self,result_builder=None): self._result_builder=result_builder
    def build(self,*,analysis_context:dict,task_results:dict[str,TaskResult],evidence:EvidenceBundle,trace_id:str)->dict:
        return {"trace_id":trace_id,"analysis_context":analysis_context,"models":[{"agent_id":r.agent_id,"model_version":r.model_version,"data_version":r.data_version,"status":r.status} for r in task_results.values()],"sources":[x.model_dump(mode="json") for x in evidence.items]}
