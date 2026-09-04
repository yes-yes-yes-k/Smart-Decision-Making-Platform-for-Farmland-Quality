"""Authoritative input resolution and confirmation policy."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any

from .contracts import DiagnosticPlan, InputResolution, ResolvedValue

LAND_TYPE_ALIASES={"upland":"upland","paddy":"paddy","旱地":"upland","水田":"paddy"}
FERTILIZER_TYPE_ALIASES={"compound":"compound","urea":"urea","复合肥":"compound","尿素":"urea"}


class ParcelInputResolver:
    def __init__(self, accessor): self._accessor=accessor
    def resolve(self, plan: DiagnosticPlan, *, analysis_context: dict[str, Any], user_values: dict[str, Any] | None = None) -> InputResolution:
        obj=analysis_context.get("object") or {}
        if obj.get("type") != "parcel" or not obj.get("id"): raise ValueError("parcel_context_required")
        snapshot=self._accessor.get_parcel_snapshot(str(obj["id"]))
        if snapshot is None: raise ValueError("parcel_not_found")
        supplied=dict(user_values or {})
        invalid=set()
        for key,aliases in (("land_type",LAND_TYPE_ALIASES),("fertilizer_type",FERTILIZER_TYPE_ALIASES)):
            if supplied.get(key) is not None:
                normalized=aliases.get(str(supplied[key]).strip().casefold())
                if normalized is None:
                    invalid.add(key); supplied[key]=None
                else:
                    supplied[key]=normalized
        base={"parcel_id":snapshot.parcel_id,"parcel_code":snapshot.parcel_code,"area_code":snapshot.area_code,"land_type":snapshot.land_type,"fertilizer_type":snapshot.fertilizer_type,"target_ph":snapshot.target_ph}
        base.update(snapshot.indicators)
        # The object identity is never user-overridable.
        supplied.pop("parcel_id", None); supplied.pop("parcel_code", None); supplied.pop("area_code", None)
        base.update({k:v for k,v in supplied.items() if v is not None})
        defaults={}
        needs_acidification=any(task.agent_id=="model-4" for task in plan.tasks)
        if needs_acidification and not base.get("fertilizer_type") and "fertilizer_type" not in invalid:
            defaults["fertilizer_type"]="compound"
            base["fertilizer_type"]="compound"
        if needs_acidification and not base.get("target_ph") and base.get("land_type") in {"upland","paddy"}:
            defaults["target_ph"]=6.5 if base["land_type"]=="paddy" else 6.0
            base["target_ph"]=defaults["target_ph"]
        resolved={
            k:ResolvedValue(
                value=v,
                source="user" if k in supplied else ("confirmed_default" if k in defaults else "parcel_db"),
                source_version="request" if k in supplied else ("workflow-default:v1" if k in defaults else snapshot.source_version),
            )
            for k,v in base.items() if v is not None
        }
        missing=[]
        args={}
        for task in plan.tasks:
            current={k:v for k,v in base.items() if v is not None}
            if task.agent_id in {"model-4","model-5"} and ("land_type" in invalid or current.get("land_type") not in {"upland","paddy"}): missing.append("land_type")
            if task.agent_id=="model-4" and ("fertilizer_type" in invalid or current.get("fertilizer_type") not in {"compound","urea"}): missing.append("fertilizer_type")
            args[task.task_id]=current
        return InputResolution(task_arguments=args,resolved_values=resolved,missing_inputs=tuple(sorted(set(missing))),proposed_defaults=defaults,object_version=int(analysis_context.get("version",1)))


@dataclass(frozen=True)
class ConfirmationDecision:
    interaction_state: str
    reason_codes: tuple[str,...]
    confirmation_hash: str


def confirmation_hash(plan: DiagnosticPlan, resolution: InputResolution) -> str:
    raw=json.dumps({"plan":plan.model_dump(mode="json"),"inputs":resolution.model_dump(mode="json")},sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class ConfirmationPolicy:
    def decide(self, *, plan: DiagnosticPlan, resolution: InputResolution, confirmed_hash: str | None = None) -> ConfirmationDecision:
        digest=confirmation_hash(plan,resolution)
        if resolution.missing_inputs: return ConfirmationDecision("needs_input",("missing_inputs",),digest)
        reasons=[]
        if resolution.proposed_defaults: reasons.append("result_affecting_defaults")
        if confirmed_hash != digest: reasons.append("plan_not_confirmed")
        return ConfirmationDecision("ready_to_execute" if not reasons else "needs_confirmation",tuple(reasons),digest)
