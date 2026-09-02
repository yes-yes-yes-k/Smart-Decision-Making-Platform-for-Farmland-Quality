"""Report generation with exact fact rendering and bounded revisions."""
from __future__ import annotations
import re
from typing import Any
from .contracts import EvidenceBundle, ReportPayload, TaskResult
from .prompt_catalog import REPORTER_PROMPT

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
def format_fact(value,unit=None):
    rendered=format(value,".15g") if isinstance(value,float) else str(value)
    return f"{rendered} {unit}" if unit else rendered
def build_fact_table(results:dict[str,TaskResult])->dict[str,str]:
    table={}
    for result in results.values():
        if result.status=="succeeded":
            for key,value in flatten_scalar_payload(result.payload).items(): table[f"{result.agent_id}.{key}"]=format_fact(value)
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
        payload=self._runner.generate(role="reporter",prompt=prompt,schema=ReportPayload)
        return payload,self._validator.validate_and_render(payload,task_results=task_results,evidence=evidence)
    def revise(self,*,current_revision_count:int,**kwargs):
        if current_revision_count>=3: raise ReportRevisionLimit("report_revision_limit")
        payload,rendered=self.compose(**kwargs)
        return payload,rendered,current_revision_count+1


class AggregateProvenanceBuilder:
    def __init__(self,result_builder=None): self._result_builder=result_builder
    def build(self,*,analysis_context:dict,task_results:dict[str,TaskResult],evidence:EvidenceBundle,trace_id:str)->dict:
        return {"trace_id":trace_id,"analysis_context":analysis_context,"models":[{"agent_id":r.agent_id,"model_version":r.model_version,"data_version":r.data_version,"status":r.status} for r in task_results.values()],"sources":[x.model_dump(mode="json") for x in evidence.items]}
