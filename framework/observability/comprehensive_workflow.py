"""Low-cardinality in-process metrics for comprehensive workflow events."""
from __future__ import annotations
from collections import Counter
from threading import Lock

_counts=Counter(); _lock=Lock()
ALLOWED_EVENTS=frozenset({"intent","plan","interaction","task_attempt","task_result","degradation","release"})


def record_comprehensive_event(event:str,**labels)->None:
    if event not in ALLOWED_EVENTS: raise ValueError("unknown_comprehensive_event")
    safe=tuple(sorted((str(k),str(v)) for k,v in labels.items() if k in {"mode","state","agent_id","status","code"}))
    with _lock: _counts[(event,safe)]+=1


def comprehensive_metrics_snapshot()->list[dict]:
    with _lock: return [{"event":event,"labels":dict(labels),"count":count} for (event,labels),count in sorted(_counts.items(),key=str)]
