"""Allow-listed execution, validation, retry and two-wave scheduling."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from framework.function_calling.specialized_tools import get_specialized_tools_for
from .contracts import DiagnosticPlan, DiagnosticTask, InputResolution, TaskResult


class TaskExecutionError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool=False): super().__init__(code); self.code,self.retryable=code,retryable


class ModelToolExecutor:
    LOCKED_KEYS=frozenset({"parcel_id","parcel_code","area_code"})
    def __init__(self, tools: dict | None = None): self._tools=tools
    def invoke(self, task: DiagnosticTask, *, arguments: dict[str,Any], execution_context: dict[str,Any]) -> dict[str,Any]:
        context=execution_context.get("analysis_context") or {}
        obj=context.get("object") or {}
        if not execution_context.get("verified") or obj.get("type")!="parcel": raise TaskExecutionError("unverified_analysis_context")
        parcel_id=str(obj.get("id") or "")
        if arguments.get("parcel_id") != parcel_id: raise TaskExecutionError("analysis_object_conflict")
        tools=self._tools or get_specialized_tools_for({task.agent_id})
        try: return tools[task.agent_id].invoke(arguments)
        except (TimeoutError, ConnectionError) as exc: raise TaskExecutionError("transient_tool_error",retryable=True) from exc
        except TaskExecutionError: raise
        except Exception as exc: raise TaskExecutionError("tool_execution_failed") from exc


class ResultValidationError(ValueError): pass


REQUIRED_PAYLOAD_KEYS={
    "model-1":("parcel_id","stability_modules"),
    "model-2":("parcel_id","quality_grade","composite_index"),
    "model-3":("parcel_id",),
    "model-4":("parcel_id",),
    "model-5":("parcel_id",),
}


class ResultValidator:
    def validate(self, task: DiagnosticTask, raw: dict[str,Any], *, arguments: dict[str,Any], trace_id: str) -> TaskResult:
        if not isinstance(raw,dict): raise ResultValidationError("invalid_result_type")
        if raw.get("status") in {"error","failed"}: raise ResultValidationError("model_execution_failed")
        payload=raw.get("result") or raw.get("payload") or raw.get("data") or raw
        if not isinstance(payload,dict): raise ResultValidationError("invalid_payload")
        payload=dict(payload); payload.setdefault("parcel_id",arguments.get("parcel_id"))
        missing=[k for k in REQUIRED_PAYLOAD_KEYS[task.agent_id] if payload.get(k) is None]
        if missing: raise ResultValidationError(f"incomplete_{task.agent_id}_payload")
        if str(payload["parcel_id"]) != str(arguments.get("parcel_id")): raise ResultValidationError("result_object_conflict")
        return TaskResult(task_id=task.task_id,agent_id=task.agent_id,status="succeeded",payload=payload,key_inputs={k:arguments.get(k) for k in ("parcel_id","area_code","land_type") if arguments.get(k) is not None},model_version=str(raw.get("model_version") or raw.get("version") or "current"),data_as_of=raw.get("data_as_of"),data_version=raw.get("data_version"),calculated_at=datetime.now(timezone.utc).isoformat(),trace_id=trace_id)


class TriggerEvaluator:
    def predicate(self,name:str,facts:dict[str,Any])->bool:
        if name in {"history_available","user_requested_acidification","user_requested_organic_matter"}: return bool(facts.get(name))
        if name=="acidification_evidence": return bool(facts.get("acidification_evidence"))
        if name=="organic_matter_evidence": return bool(facts.get("organic_matter_evidence"))
        return False
    def task_enabled(self,task:DiagnosticTask,facts:dict[str,Any])->bool:
        if task.trigger.type=="always": return True
        values=[self.predicate(x,facts) for x in task.trigger.predicates]
        return all(values) if task.trigger.type=="all" else any(values)


@dataclass(frozen=True)
class ExecutionOutcome:
    results: dict[str,TaskResult]
    attempts: dict[str,int]
    degradations: tuple[str,...]


def parse_existing_results(values): return {k:(v if isinstance(v,TaskResult) else TaskResult.model_validate(v)) for k,v in (values or {}).items()}


def failed_task_result(task:DiagnosticTask,*,trace_id:str,code:str,status:str="failed") -> TaskResult:
    return TaskResult(task_id=task.task_id,agent_id=task.agent_id,status=status,payload={},key_inputs={},model_version="unknown",data_as_of=None,data_version=None,calculated_at=datetime.now(timezone.utc).isoformat(),trace_id=trace_id,error_code=code)


def derive_trigger_facts(results, resolution, request_facts):
    facts=dict(request_facts)
    obstacle=next((r.payload for r in results.values() if r.agent_id=="model-3" and r.status=="succeeded"),{})
    text=str(obstacle).casefold()
    facts["acidification_evidence"]=any(x in text for x in ("酸化","soil_ph","ph"))
    facts["organic_matter_evidence"]=any(x in text for x in ("有机质","organic_matter","som"))
    return facts


class ExecutionScheduler:
    def __init__(self,executor:ModelToolExecutor,validator:ResultValidator,evaluator:TriggerEvaluator|None=None): self.executor,self.validator,self.evaluator=executor,validator,evaluator or TriggerEvaluator()
    def execute(self,plan:DiagnosticPlan,*,resolution:InputResolution,execution_context:dict,request_facts:dict,existing_results:dict|None=None,existing_attempts:dict|None=None,trace_id:str)->ExecutionOutcome:
        results=parse_existing_results(existing_results); attempts=dict(existing_attempts or {}); degradations=[]
        core=[t for t in plan.tasks if t.agent_id in {"model-1","model-2","model-3"}]
        self._run_wave(core,results,attempts,degradations,resolution,execution_context,request_facts,trace_id)
        facts=derive_trigger_facts(results,resolution,request_facts)
        self._run_wave([t for t in plan.tasks if t.agent_id in {"model-4","model-5"}],results,attempts,degradations,resolution,execution_context,facts,trace_id)
        return ExecutionOutcome(results,attempts,tuple(degradations))
    def _run_wave(self,tasks,results,attempts,degradations,resolution,context,facts,trace_id):
        for task in tasks:
            if task.task_id in results and results[task.task_id].status=="succeeded": continue
            if not self.evaluator.task_enabled(task,facts):
                results[task.task_id]=failed_task_result(task,trace_id=trace_id,code="trigger_not_met",status="skipped"); continue
            args=resolution.task_arguments.get(task.task_id,{})
            last_code="execution_failed"
            for _ in range(3):
                attempts[task.task_id]=attempts.get(task.task_id,0)+1
                try:
                    raw=self.executor.invoke(task,arguments=args,execution_context=context)
                    results[task.task_id]=self.validator.validate(task,raw,arguments=args,trace_id=trace_id); break
                except TaskExecutionError as exc:
                    last_code=exc.code
                    if not exc.retryable: break
                except ResultValidationError as exc: last_code=str(exc); break
            else: pass
            if task.task_id not in results or results[task.task_id].status!="succeeded":
                status="failed" if task.required else "degraded"
                results[task.task_id]=failed_task_result(task,trace_id=trace_id,code=last_code,status=status)
                if not task.required: degradations.append(f"{task.agent_id}:{last_code}")
