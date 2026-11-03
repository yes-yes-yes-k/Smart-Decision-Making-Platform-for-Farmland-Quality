"""Score source-bound predictions against the frozen, task-masked AI silver release."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,sha
from framework.knowledge_graph.evaluation_v4_r3 import validate_r3
from framework.knowledge_graph.silver_adjudication import score_silver_sample
from framework.knowledge_graph.evaluation_v4_scoring import aggregate

DEFAULT=ROOT/'artifacts/knowledge_platform/gold-v4/silver-v1'

def score_release(release,predictions):
    manifest=json.loads((release/'manifest.json').read_text(encoding='utf-8'))
    if sha(release/'reference.jsonl')!=manifest['reference_sha256']:raise ValueError('frozen_reference_changed')
    rows=read(release/'reference.jsonl');refs={r['visible_input']['sample_id']:r for r in rows}
    if len(rows)!=100 or len(refs)!=100:raise ValueError('100_unique_reference_samples_required')
    scored={};groups={};seen=set();invalid={}
    for p in predictions:
        sid=p['sample_id']
        if sid not in refs or sid in seen:raise ValueError('unknown_or_duplicate_prediction_sample')
        seen.add(sid);r=refs[sid]
        if p.get('input_sha256')!=r['annotation']['input_sha256']:raise ValueError('prediction_input_hash_mismatch')
        try:
            annotation=validate_r3(r['visible_input'],p['answer'])
        except (ValueError,KeyError,TypeError) as exc:
            invalid[sid]=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
            annotation=None
        scored[sid]=score_silver_sample(r['annotation'],annotation)
    for sid,r in refs.items():
        groups[sid]=r['source']['leakage_group']
        if sid not in scored:scored[sid]=score_silver_sample(r['annotation'])
    tasks=['surface_chunk_mentions','surface_context_mentions','surface_relations','chunk_mentions','context_mentions','relations','normalization_on_reference_known_mentions']
    return dict(samples=100,received=len(seen),valid_completed=sum(s['completed'] for s in scored.values()),
        missing_samples=sorted(set(refs)-seen),invalid_predictions=invalid,
        reference_sha256=manifest['reference_sha256'],reference_counts=manifest['counts'],
        tasks={t:aggregate(scored,groups,task=t) for t in tasks},
        body_clear_negatives=sum(s['body_negative'] for s in scored.values()),
        body_correct_negatives=sum(s['body_correct_negative'] for s in scored.values()),
        primary_tasks=tasks[:3],exact_span_metrics_are_diagnostic=True,
        missing_or_invalid='counted as missing predictions with false negatives on eligible tasks; never dropped from denominator',
        semantic_evidence_sufficiency='requires independent review; exact-span evidence diagnostic is not semantic certification',
        independent_evaluation=False,expert_certified=False,production_approved=False,sample_scores=scored)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--release',type=Path,default=DEFAULT);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=score_release(a.release,read(a.predictions));write(a.output,report)
    print(json.dumps({k:report[k] for k in ('samples','received','valid_completed')},ensure_ascii=False))
