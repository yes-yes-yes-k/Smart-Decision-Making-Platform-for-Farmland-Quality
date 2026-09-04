"""Initial/resume facade and stable workflow output envelope."""
from __future__ import annotations
from langgraph.types import Command
from .checkpointing import workflow_thread_config
from .contracts import InteractionResponse, WorkflowOutput
from .graph import initial_state


class WorkflowConflict(RuntimeError): http_status=409
class WorkflowNotFound(RuntimeError): http_status=404
class CheckpointerUnavailable(RuntimeError): http_status=503


def plan_summary(state):
    plan=state.get("diagnostic_plan") or {}
    return {"plan_version":plan.get("plan_version"),"tasks":[{"task_id":x.get("task_id"),"agent_id":x.get("agent_id"),"required":x.get("required")} for x in plan.get("tasks",[])]}


def normalize_graph_output(result)->WorkflowOutput:
    interrupts=result.get("__interrupt__") or (); interaction={}
    if interrupts: interaction=getattr(interrupts[0],"value",{}) or {}
    state=interaction.get("interaction_state") or result.get("interaction_state","failed")
    return WorkflowOutput(interaction_state=state,run_id=interaction.get("run_id") or result["run_id"],checkpoint_version=int(interaction.get("checkpoint_version",result.get("checkpoint_version",0))),analysis_context=result.get("analysis_context_snapshot",{}),plan_summary=plan_summary(result),missing_inputs=tuple(interaction.get("missing_inputs",result.get("missing_inputs",[]))),proposed_defaults=interaction.get("proposed_defaults",result.get("proposed_defaults",{})),report_draft=interaction.get("report_draft") or result.get("report_draft"),answer=result.get("report_draft") if state in {"completed","partial_complete"} else None,degradations=tuple(result.get("degradations",[])),provenance=result.get("provenance",{}),trace_id=result.get("trace_id",""))


class ComprehensiveWorkflowRuntime:
    def __init__(self,graph): self._graph=graph
    def run_initial(self,request):
        config=workflow_thread_config(request["conversation_id"],request["run_id"])
        return normalize_graph_output(self._graph.invoke(initial_state(request),config=config))
    def resume(self,*,conversation_id:int,response:InteractionResponse):
        config=workflow_thread_config(conversation_id,response.run_id)
        snapshot=self._graph.get_state(config)
        if not snapshot or not snapshot.values: raise WorkflowNotFound("workflow_not_found")
        current=normalize_graph_output(dict(snapshot.values)|({"__interrupt__":snapshot.tasks[0].interrupts} if snapshot.tasks and snapshot.tasks[0].interrupts else {}))
        if response.expected_checkpoint_version != current.checkpoint_version: raise WorkflowConflict("checkpoint_version_conflict")
        return normalize_graph_output(self._graph.invoke(Command(resume=response.model_dump(mode="json")),config=config))
