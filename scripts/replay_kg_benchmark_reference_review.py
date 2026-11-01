"""Fix deterministic evidence coordinate materialization; replay saved responses.

Does not repair model text, change decisions, fill missing fields, or call models.
Original request results and their validation errors remain immutable.
"""
import copy
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.review_kg_benchmark_reference as review
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,budget_snapshot
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_protocol_r2 import locate
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from scripts.report_kg_benchmark_pilot import signature

DEST=OUT/'execution/pilot-r4-reference-replay-v2'
ORIGINAL_VALIDATE=review.validate_proposal


def validate_with_coordinates(packet,proposal,schema):
    material=copy.deepcopy(proposal)
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    for relation in material['relations']:
        relation['evidence']=[dict(f,**{k:v for k,v in locate(f,blocks).items() if k not in f})
                              for f in relation['evidence']]
    return ORIGINAL_VALIDATE(packet,material,schema)


def validate(packet,raw,schema):
    previous=review.validate_proposal
    review.validate_proposal=validate_with_coordinates
    try:
        result=review.check(packet,raw,schema)
        blocks={b['block_id']:b['text'] for b in packet['blocks']}
        # Save the same program-derived coordinates used by validation.
        for relation in result['materialized_proposal']['relations']:
            relation['evidence']=[dict(f,**{k:v for k,v in locate(f,blocks).items() if k not in f}) for f in relation['evidence']]
        return result
    finally:
        review.validate_proposal=previous


def main():
    packets={r['sample_id']:r for name in ['controls-inputs.jsonl','pilot-inputs.jsonl'] for r in readlines(OUT/'protocol-r4'/name)}
    keys={r['sample_id']:r for r in readlines(OUT/'protocol-r4/private-control-keys.jsonl')}
    candidates={}
    for p in (OUT/'execution/pilot-r4-adjudication/proposals').glob('*.json'):
        r=json.loads(p.read_text(encoding='utf-8'));candidates[r['id'].removeprefix('arbitrate:')]=json.loads(r['content'])
    results=[];references=[]
    for path in sorted((review.RUN/'proposals').glob('*.json')):
        saved=json.loads(path.read_text(encoding='utf-8'));sid=saved['id'].removeprefix('review:')
        packet=dict(packets[sid],candidate=candidates[sid])
        row=dict(sample_id=sid,original_state=saved['state'],original_response_sha256=sha256_file(path),
            control=sid in keys,model_recalled=False)
        try:
            checked=validate(packet,json.loads(saved['content']),load_schema(ROOT))
            row.update(state='protocol_valid' if checked['protocol_complete'] else 'protocol_rejected',validated=checked)
            if sid in keys:
                row['control_inventory_exact']=signature(checked['materialized_proposal'])==signature(keys[sid]['expected'])
                row['control_masks_applicable']=all(m['status']=='applicable' for m in checked['source_reference_masks'])
            elif checked['reference_ready']:
                references.append(dict(sample_id=sid,visible_input={k:packet[k] for k in ['sample_id','blocks']},
                    reference=checked['materialized_proposal'],reference_masks=checked['source_reference_masks'],
                    source_decision_reviews=checked['decision_reviews'],relation_reviews=checked['relation_reviews'],
                    normalization_reviews=checked['normalization_reviews'],
                    reference_status='development_trial_AI_silver_draft_not_final',
                    protocol_revision='r4-reference-replay-v2',expert_certified=False,same_model_error_correlation=True))
        except (ValueError,KeyError,TypeError) as exc:
            row.update(state='failed',error=str(exc))
        results.append(row)
    control_rows=[r for r in results if r['control']]
    report=dict(status='inconclusive',offline_validation_replay=True,
        correction='derive_missing_evidence_start_end_from_existing_literal_source_spans',
        no_model_fields_filled=True,cloud_requests=0,old_results_modified=False,
        cases=len(results),states=dict(Counter(r['state'] for r in results)),
        expected_real_sources=10,real_source_drafts_ready=len(references),
        controls=len(control_rows),control_references_exact=sum(r.get('control_inventory_exact',False) for r in control_rows),
        control_masks_applicable=sum(r.get('control_masks_applicable',False) for r in control_rows),
        unresolved=[dict(sample_id=r['sample_id'],error=r.get('error'),issues=r.get('validated',{}).get('unresolved'),
            protocol_errors=r.get('validated',{}).get('errors')) for r in results
            if r['state']!='protocol_valid' or not r.get('validated',{}).get('reference_ready')],
        handbook_validated=False,formal_acceptance_ready=False,expert_certified=False,
        same_model_error_correlation=True,shared_budget=budget_snapshot())
    lines(DEST/'replayed-items.jsonl',results)
    lines(DEST/'source-reference-drafts.jsonl',references)
    dump(DEST/'report.json',report)
    dump(DEST/'validation-version.json',dict(checker_sha256=sha256_file(Path(__file__)),
        original_checker_sha256=sha256_file(ROOT/'scripts/review_kg_benchmark_reference.py'),
        responses_unchanged=True,semantic_decisions_unchanged=True))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
