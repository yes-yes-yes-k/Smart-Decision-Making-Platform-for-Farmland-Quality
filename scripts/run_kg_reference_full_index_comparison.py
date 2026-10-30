"""Execute the prepared 16 full-index adjudications under shared global caps."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.prepare_kg_reference_full_index_comparison import RUN,prepare
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,dump,budget_snapshot
from scripts.replay_kg_benchmark_reference_review import validate
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file

AUTH=OUT/'execution/project-budget-authorization.json'
ALLOCATION=OUT/'execution/phase-allocation.json'


async def main():
    engine.RUN=RUN
    jobs=prepare()
    from scripts.inspect_kg_acceptance_review import audit_database
    source_ids={j['packet']['sample_id'] for j in jobs if 'rebuild-v2:' in j['id']}
    from scripts.rebuild_kg_extraction_benchmark import readlines
    sources=[r for r in readlines(OUT/'protocol/pilot-source-map.jsonl') if r['sample_id'] in source_ids]
    checks,missing=audit_database(sources)
    if missing or any(r['reasons'] for r in checks):raise ValueError('current_public_source_qualification_changed')
    dump(RUN/'source-qualification.json',dict(checks=checks,missing=missing,read_only=True))
    policy=json.loads(AUTH.read_text(encoding='utf-8'))
    budget=lambda path,**ignored:AuthorizedBudget(path,authorization=AUTH,allocation=ALLOCATION)
    engine.Budget=budget;engine.limits=lambda:dict(stability=2_200_000,total=10_000_000,requests=5000)
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        initial_phase_limit=2_200_000,global_token_limit=10_000_000,global_request_limit=5000,
        automatic_phase_reallocation=policy['automatic_phase_reallocation'],concurrency=1,
        authorization_sha256=sha256_file(AUTH),jobs={j['id']:engine.digest(j) for j in jobs},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in [Path(__file__),ROOT/'framework/knowledge_graph/benchmark_budget_policy.py',ROOT/'scripts/replay_kg_benchmark_reference_review.py']])
    destination=RUN/'run-config.json'
    if destination.exists() and json.loads(destination.read_text(encoding='utf-8'))!=config:raise ValueError('comparison_config_frozen')
    if not destination.exists():dump(destination,config)
    engine.validate_proposal=validate
    stopped=False
    try:
        for index,job in enumerate(jobs):
            dump(RUN/'batch-state.json',dict(active=True,next_index=index,total=len(jobs),budget=budget_snapshot()))
            result=await engine.execute([job],config)
            if result['stopped']:stopped=True;break
    finally:
        dump(RUN/'batch-state.json',dict(active=False,background_running=False,budget_stopped=stopped,
            total=len(jobs),saved=len(list((RUN/'proposals').glob('*.json'))),budget=budget_snapshot()))


if __name__=='__main__':asyncio.run(main())
