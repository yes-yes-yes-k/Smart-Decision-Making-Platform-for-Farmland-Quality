"""Guard the disabled-mode routing overhead against the legacy fast-path check."""
from __future__ import annotations
import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.agents.orchestrator import MultiAgentOrchestrator


def p95(values): return sorted(values)[max(0,int(len(values)*.95)-1)]
def main()->int:
    orchestrator=MultiAgentOrchestrator(); request={"question":"质量等级如何","user_id":1,"calculation_mode":"spatial","analysis_context":{"mode":"spatial","version":1,"object":{"type":"parcel","id":"P001"}}}
    def legacy_prepare():
        # Stable proxy for the existing request normalization/serialization work.
        for _ in range(20): json.dumps(request,ensure_ascii=False,sort_keys=True)
    baseline=[]; routed=[]
    for _ in range(200):
        start=time.perf_counter_ns(); legacy_prepare(); baseline.append(time.perf_counter_ns()-start)
        start=time.perf_counter_ns(); orchestrator.prepare_top_level_route(request); legacy_prepare(); routed.append(time.perf_counter_ns()-start)
    base=max(p95(baseline),1); ratio=p95(routed)/base
    print(json.dumps({"baseline_p95_ns":base,"routed_p95_ns":p95(routed),"ratio":ratio}))
    return 0 if ratio<=1.10 else 1
if __name__=="__main__": raise SystemExit(main())
