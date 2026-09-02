"""Interruptible LangGraph for a single parcel comprehensive diagnosis."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
from framework.llm.service import llm_service
from framework.rag.chain import rag_chain
from .confirmation import ConfirmationPolicy, ParcelInputResolver
from .contracts import DiagnosticPlan, EvidenceBundle, InputResolution, InteractionResponse, TaskResult
from .evidence import EvidenceResearcher, canonical_claims_from_results
from .execution import ExecutionScheduler, ModelToolExecutor, ResultValidator
from .planner import DiagnosticPlanner, OrmPlanningFactSource, PlanningFactsResolver, PlanValidator
from .reporting import AggregateProvenanceBuilder, ReportPolicyValidator, Reporter
from .state import ComprehensiveDiagnosticState
from .structured_roles import StructuredRoleRunner


@dataclass(frozen=True)
class ComprehensiveServices:
    planning_facts_resolver: Any
    planner: Any
    input_resolver: Any
    confirmation_policy: Any
    scheduler: Any
    researcher: Any
    reporter: Any
    provenance_builder: Any


def build_default_comprehensive_services(app) -> ComprehensiveServices:
    runner=StructuredRoleRunner(llm_service)
    return ComprehensiveServices(PlanningFactsResolver(OrmPlanningFactSource()),DiagnosticPlanner(runner,PlanValidator()),ParcelInputResolver(ParcelDataAccessor(app)),ConfirmationPolicy(),ExecutionScheduler(ModelToolExecutor(),ResultValidator()),EvidenceResearcher(runner,rag_chain),Reporter(runner,ReportPolicyValidator()),AggregateProvenanceBuilder())


def initial_state(request:dict[str,Any])->dict[str,Any]:
    return {"run_id":request["run_id"],"trace_id":request["trace_id"],"conversation_id":request["conversation_id"],"user_id":request["user_id"],"checkpoint_version":0,"interaction_state":"planning","normalized_request":request,"analysis_context_snapshot":request["analysis_context"],"object_version":request["analysis_context"].get("version",1),"task_results":{},"task_attempts":{},"degradations":[],"report_revision_count":0}


def build_comprehensive_graph(services:ComprehensiveServices,checkpointer):
    graph=StateGraph(ComprehensiveDiagnosticState)
    def plan_node(state):
        request=state["normalized_request"]; obj=state["analysis_context_snapshot"]["object"]
        facts=services.planning_facts_resolver.resolve(parcel_id=str(obj["id"]),user_message=request.get("question",request.get("message","")))
        plan=services.planner.create_plan(request=request,facts=facts,capabilities=request.get("capabilities",[]))
        return {"planning_facts":facts.__dict__,"request_facts":facts.__dict__,"diagnostic_plan":plan.model_dump(mode="json"),"interaction_state":"resolving_inputs"}
    def input_node(state):
        plan=DiagnosticPlan.model_validate(state["diagnostic_plan"])
        values=(state.get("confirmation") or {}).get("values",{})
        resolution=services.input_resolver.resolve(plan,analysis_context=state["analysis_context_snapshot"],user_values=values)
        version=state.get("checkpoint_version",0)
        if resolution.missing_inputs:
            version+=1
            response=interrupt({"interaction_state":"needs_input","run_id":state["run_id"],"checkpoint_version":version,"missing_inputs":list(resolution.missing_inputs),"proposed_defaults":resolution.proposed_defaults})
            action=InteractionResponse.model_validate(response)
            if action.action=="cancel": return {"interaction_state":"canceled","checkpoint_version":version}
            values=action.values
            resolution=services.input_resolver.resolve(plan,analysis_context=state["analysis_context_snapshot"],user_values=values)
        return {"resolved_inputs":resolution.model_dump(mode="json"),"missing_inputs":list(resolution.missing_inputs),"proposed_defaults":resolution.proposed_defaults,"confirmation":{"values":values},"interaction_state":"confirming","checkpoint_version":version}
    def confirm_node(state):
        plan=DiagnosticPlan.model_validate(state["diagnostic_plan"]); resolution=InputResolution.model_validate(state["resolved_inputs"])
        decision=services.confirmation_policy.decide(plan=plan,resolution=resolution,confirmed_hash=(state.get("confirmation") or {}).get("hash"))
        version=state.get("checkpoint_version",0)
        if decision.interaction_state=="needs_confirmation":
            version+=1
            response=interrupt({"interaction_state":"needs_confirmation","run_id":state["run_id"],"checkpoint_version":version,"plan":plan.model_dump(mode="json"),"confirmation_hash":decision.confirmation_hash,"proposed_defaults":resolution.proposed_defaults})
            action=InteractionResponse.model_validate(response)
            if action.action=="cancel": return {"interaction_state":"canceled","checkpoint_version":version}
            if action.action!="confirm_plan": raise ValueError("invalid_interaction_action")
        return {"confirmation":{"hash":decision.confirmation_hash},"interaction_state":"executing","checkpoint_version":version}
    def execute_node(state):
        outcome=services.scheduler.execute(DiagnosticPlan.model_validate(state["diagnostic_plan"]),resolution=InputResolution.model_validate(state["resolved_inputs"]),execution_context={"analysis_context":state["analysis_context_snapshot"],"verified":True,"trace_id":state["trace_id"]},request_facts=state.get("request_facts",{}),existing_results=state.get("task_results"),existing_attempts=state.get("task_attempts"),trace_id=state["trace_id"])
        core_failed=any(r.agent_id in {"model-2","model-3"} and r.status!="succeeded" for r in outcome.results.values())
        return {"task_results":{k:v.model_dump(mode="json") for k,v in outcome.results.items()},"task_attempts":outcome.attempts,"degradations":list(outcome.degradations),"interaction_state":"failed" if core_failed else "researching"}
    def research_node(state):
        results={k:TaskResult.model_validate(v) for k,v in state["task_results"].items()}; claims=canonical_claims_from_results(results)
        outcome=services.researcher.research_safe(task_results=results,claims=claims)
        degradations=list(state.get("degradations",[]))+([outcome.degradation] if outcome.degradation else [])
        return {"canonical_claims":claims,"evidence_items":[x.model_dump(mode="json") for x in outcome.bundle.items],"unsupported_claims":list(outcome.bundle.unsupported_claims),"degradations":degradations,"interaction_state":"reporting"}
    def report_node(state):
        results={k:TaskResult.model_validate(v) for k,v in state["task_results"].items()}; evidence=EvidenceBundle(items=tuple(state.get("evidence_items",[])),unsupported_claims=tuple(state.get("unsupported_claims",[])))
        payload,draft=services.reporter.compose(task_results=results,evidence=evidence,degradations=tuple(state.get("degradations",[])),revision_comment=state.get("revision_comment",""))
        return {"report_payload":payload.model_dump(mode="json"),"report_draft":draft,"interaction_state":"awaiting_release"}
    def release_node(state):
        version=state.get("checkpoint_version",0)+1
        response=interrupt({"interaction_state":"awaiting_release","run_id":state["run_id"],"checkpoint_version":version,"report_draft":state["report_draft"]})
        action=InteractionResponse.model_validate(response)
        if action.action=="cancel": return {"interaction_state":"canceled","checkpoint_version":version}
        if action.action=="request_revision":
            if state.get("report_revision_count",0)>=3: raise ValueError("report_revision_limit")
            return {"interaction_state":"reporting","revision_comment":action.comment,"report_revision_count":state.get("report_revision_count",0)+1,"checkpoint_version":version}
        if action.action!="release_report": raise ValueError("invalid_interaction_action")
        results={k:TaskResult.model_validate(v) for k,v in state["task_results"].items()}; evidence=EvidenceBundle(items=tuple(state.get("evidence_items",[])),unsupported_claims=tuple(state.get("unsupported_claims",[])))
        provenance=services.provenance_builder.build(analysis_context=state["analysis_context_snapshot"],task_results=results,evidence=evidence,trace_id=state["trace_id"])
        return {"interaction_state":"partial_complete" if state.get("degradations") else "completed","checkpoint_version":version,"provenance":provenance}
    graph.add_node("plan",plan_node); graph.add_node("input",input_node); graph.add_node("confirm",confirm_node); graph.add_node("execute",execute_node); graph.add_node("research",research_node); graph.add_node("report",report_node); graph.add_node("release",release_node)
    graph.set_entry_point("plan"); graph.add_edge("plan","input")
    graph.add_conditional_edges("input",lambda s:"end" if s.get("interaction_state")=="canceled" else "confirm",{"end":END,"confirm":"confirm"})
    graph.add_conditional_edges("confirm",lambda s:"end" if s.get("interaction_state")=="canceled" else "execute",{"end":END,"execute":"execute"})
    graph.add_conditional_edges("execute",lambda s:"end" if s.get("interaction_state")=="failed" else "research",{"end":END,"research":"research"})
    graph.add_edge("research","report"); graph.add_edge("report","release")
    graph.add_conditional_edges("release",lambda s:"report" if s.get("interaction_state")=="reporting" else "end",{"report":"report","end":END})
    return graph.compile(checkpointer=checkpointer)
