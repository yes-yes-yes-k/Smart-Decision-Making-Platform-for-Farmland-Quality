"""Adapt arbitration source citations to r4 cells without changing older runs."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.run_kg_benchmark_pilot_r4 as pilot
from scripts.rebuild_kg_extraction_benchmark import OUT,dump
from framework.knowledge_graph.benchmark_rebuild import sha256_file


def main():
    engine.RUN=OUT/'execution/pilot-r4-adjudication'
    # The old instruction string remains unchanged on disk and in r3 history.
    pilot.arbitration.INSTRUCTIONS=pilot.arbitration.INSTRUCTIONS.replace(
        'block_id,text,occurrence','block_id,start_cell,end_cell').replace('统一r3','统一r4')
    run,jobs,config=pilot.prepare(True)
    adapter=dict(entrypoint=Path(__file__).relative_to(ROOT).as_posix(),
        sha256=sha256_file(Path(__file__)),source_citation_transport='r4_source_cells',
        raw_quotes_and_occurrence_instructions_replaced=True)
    path=run/'transport-adapter.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=adapter:
        raise ValueError('r4_arbitration_adapter_changed')
    if not path.exists():dump(path,adapter)
    engine.validate_proposal=pilot.check_arbitration
    print(json.dumps(asyncio.run(engine.execute(jobs,config))))


if __name__=='__main__':main()
