"""Explicit finite resume, retaining immutable jobs and avoiding cached-batch I/O."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.build_kg_benchmark_final_references as runner
from scripts.rebuild_kg_extraction_benchmark import OLD,budget_snapshot
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.benchmark_reference_hold import require_no_semantic_hold


async def run():
    require_no_semantic_hold(runner.OUT)
    budget=AuthorizedBudgetV2(OLD/'budget.sqlite3',authorization=runner.AUTH,allocation=runner.ALLOCATION)
    if budget.summary()['inflight']:raise ValueError('resolve_confirmed_interrupted_attempts_before_explicit_resume')
    original_execute=runner.engine.execute
    original_compile=runner.compile_progress
    report=runner.BASE/'report.json'
    last_requests=json.loads(report.read_text(encoding='utf-8'))['shared_budget']['requests'] if report.exists() else -1

    async def execute(jobs,config,**kwargs):
        directory=runner.engine.RUN/'proposals'
        cached=[]
        for job in jobs:
            path=directory/(runner.engine.digest(job['id'])+'.json')
            if not path.exists():break
            row=json.loads(path.read_text(encoding='utf-8'))
            if row['job_sha256']!=runner.engine.digest(job):raise ValueError('cached_job_changed')
            if row['state']=='budget_blocked':raise ValueError('archive_unattempted_budget_block_before_resume')
            cached.append(row)
        if len(cached)==len(jobs):return dict(budget=budget.summary(),stopped=False)
        return await original_execute(jobs,config,**kwargs)

    def compile_progress(*args):
        nonlocal last_requests
        requests=budget_snapshot()['requests']
        if requests!=last_requests:
            original_compile(*args);last_requests=requests

    runner.engine.execute=execute;runner.compile_progress=compile_progress
    await runner.run()


if __name__=='__main__':asyncio.run(run())
