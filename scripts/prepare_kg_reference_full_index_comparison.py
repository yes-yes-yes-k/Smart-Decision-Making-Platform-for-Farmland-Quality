"""Prepare, but do not execute, full-index three-stage comparison requests.

Reuses the frozen r4 A/B requests. It does not retry old jobs, use their final
labels, or adopt the compact selector whose control quality regressed.
"""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,budget_snapshot,verify_history
from framework.knowledge_graph.benchmark_cells import indexed_block
from framework.knowledge_graph.benchmark_legacy_proposal_union import union_legacy_proposals
from framework.knowledge_graph.benchmark_reference_schema import build_reference_schema
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from scripts.review_kg_benchmark_reference import RULES

RUN=OUT/'execution/full-index-three-stage-comparison'


def prepare():
    verify_history()
    packets=readlines(OUT/'protocol-r4/controls-inputs.jsonl')+[p for p in readlines(OUT/'protocol-r4/pilot-inputs.jsonl')
        if p['sample_id'].startswith(('rebuild-v2:128:','rebuild-v2:859:'))]
    records={}
    for path in (OUT/'execution/pilot-r4/proposals').glob('*.json'):
        row=json.loads(path.read_text(encoding='utf-8'));records[row['id']]=row
    jobs=[]
    for p in packets:
        pair=[records[role+':'+p['sample_id']] for role in ['A','B']]
        if any(r['state']!='protocol_valid' for r in pair):raise ValueError('full_index_source_proposals_required')
        candidate=union_legacy_proposals([r['proposal'] for r in pair])
        packet=dict(p,candidate=candidate)
        source=dict(sample_id=p['sample_id'],blocks=[indexed_block(b) for b in p['blocks']],candidate=candidate)
        options=dict(messages=[dict(role='system',content=p['handbook']+'\n'+RULES),
            dict(role='user',content=json.dumps(source,ensure_ascii=False))],
            max_tokens=6144,response_format=build_reference_schema(candidate,load_schema(ROOT)))
        jobs.append(dict(id='full-index-review:'+p['sample_id'],phase='stability',packet=packet,options=options))
    return jobs


def main():
    jobs=prepare();b=budget_snapshot();remaining=2_000_000-b['by_phase']['stability']
    records=[]
    for job in jobs:
        reserve=len(json.dumps(job['options'],ensure_ascii=False).encode('utf-8'))+job['options']['max_tokens']+1024
        records.append(dict(id=job['id'],reserve_per_attempt=reserve,is_real_source='rebuild-v2:' in job['id']))
    lines(RUN/'request-plan.jsonl',jobs)
    dump(RUN/'preflight.json',dict(status='prepared_not_authorized_to_extend_phase_budget',
        model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        expected_jobs=len(jobs),control_jobs=14,real_source_jobs=2,
        previous_A_B_calls_reused=True,previous_final_labels_in_requests=False,
        full_character_ids_retained=True,compact_index_adopted=False,
        budget=b,stability_cap=2_000_000,remaining_stability=remaining,
        request_reservations=records,sum_first_attempt_reservations=sum(r['reserve_per_attempt'] for r in records),
        minimum_reservation=min(r['reserve_per_attempt'] for r in records),
        maximum_reservation=max(r['reserve_per_attempt'] for r in records),
        current_budget_cannot_complete_trial=True,cloud_calls=0,automatic_execution=False,
        files=[dict(path=str(Path(__file__).relative_to(ROOT)),sha256=sha256_file(Path(__file__))),
            dict(path='framework/knowledge_graph/benchmark_legacy_proposal_union.py',sha256=sha256_file(ROOT/'framework/knowledge_graph/benchmark_legacy_proposal_union.py'))]))
    print(json.dumps(dict(prepared_requests=len(jobs),cloud_calls=0,current_stability_remaining=remaining,
        minimum_reservation=min(r['reserve_per_attempt'] for r in records),maximum_reservation=max(r['reserve_per_attempt'] for r in records))))


if __name__=='__main__':main()
