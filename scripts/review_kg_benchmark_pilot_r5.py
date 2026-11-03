"""Sequential final pilot adjudications to fit conservative reservation headroom."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.run_kg_benchmark_pilot_r5 as pilot
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,budget_snapshot
from framework.knowledge_graph.benchmark_rebuild import sha256_file


async def run():
    engine.RUN=OUT/'execution/pilot-r5-reference-review'
    jobs,config=pilot.prepare('review')
    schedule=dict(concurrency=1,upper_authorized_concurrency=2,
        reason='preserve_conservative_reservation_headroom_below_2000000_stability_cap',
        entrypoint=Path(__file__).relative_to(ROOT).as_posix(),sha256=sha256_file(Path(__file__)),
        expected_jobs=len(jobs),initial_budget=budget_snapshot())
    dump(engine.RUN/'schedule.json',schedule)
    engine.validate_proposal=pilot.check_reference
    stopped=False
    try:
        for index,job in enumerate(jobs):
            dump(engine.RUN/'batch-state.json',dict(active=True,total=len(jobs),next_index=index,budget=budget_snapshot()))
            result=await engine.execute([job],config)
            if result['stopped']:
                stopped=True;break
    finally:
        dump(engine.RUN/'batch-state.json',dict(active=False,background_running=False,
            total=len(jobs),saved=len(list((engine.RUN/'proposals').glob('*.json'))),
            budget_stopped=stopped,budget=budget_snapshot()))


if __name__=='__main__':asyncio.run(run())
