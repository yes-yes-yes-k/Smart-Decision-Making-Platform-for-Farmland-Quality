"""Measure observed shared errors without treating agreement as correctness."""
from pathlib import Path
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,readlines
from scripts.report_kg_benchmark_pilot import signature


def title_assertions(proposal):
    return [i for i,r in enumerate(proposal.get('relations',[])) if any(
        e.get('role')=='assertion' and e.get('block_id')=='document_title' for e in r.get('evidence',[]))]


def primary_signature(proposal):
    byid={e['id']:(e['type'],e['block_id'],re.sub(r'\s+','',e['text'])) for e in proposal.get('entities',[])}
    return set(byid.values()),{(r['type'],byid.get(r['source_id']),byid.get(r['target_id']),r['modality'],
        json.dumps(r.get('conditions',[]),sort_keys=True,ensure_ascii=False)) for r in proposal.get('relations',[])}


def main():
    records={}
    for p in (OUT/'references-v1/calibration/initial/proposals').glob('*.json'):
        r=json.loads(p.read_text(encoding='utf-8'));records[r['id']]=r
    items=[];valid_pairs=0;equal=0;surface_equal=0;entity_equal=0;relation_equal=0
    for r in readlines(OUT/'dataset-v1/calibration-samples.jsonl'):
        sid=r['sample_id'];a=records.get('A:'+sid);b=records.get('B:'+sid)
        if not a or not b:continue
        if a['state']!='protocol_valid' or b['state']!='protocol_valid':continue
        valid_pairs+=1
        agreement=signature(a['protocol']['materialized_proposal'])==signature(b['protocol']['materialized_proposal']);equal+=agreement
        left_primary=primary_signature(a['protocol']['materialized_proposal']);right_primary=primary_signature(b['protocol']['materialized_proposal'])
        surface_equal+=left_primary==right_primary;entity_equal+=left_primary[0]==right_primary[0];relation_equal+=left_primary[1]==right_primary[1]
        left=title_assertions(a['proposal']);right=title_assertions(b['proposal'])
        if left or right:items.append(dict(sample_id=sid,A_title_assertion_indices=left,B_title_assertion_indices=right,
            shared_error=bool(left and right),inventory_agreement=agreement))
    release=OUT/'reference-release-v1/calibration/requires-adjudication.jsonl'
    failures=readlines(release) if release.exists() else []
    dump(OUT/'references-v1/calibration/correlated-error-audit.json',dict(status='partial_observation_not_accuracy_estimate',
        expected_pairs=100,valid_pairs_observed=valid_pairs,inventory_agreeing_pairs=equal,
        inventory_agreement_basis='mention_type_block_literal_text_occurrence_and_relations',
        primary_surface_inventory_agreeing_pairs=surface_equal,entity_surface_agreeing_pairs=entity_equal,relation_fact_agreeing_pairs=relation_equal,
        primary_surface_policy='whitespace_only_no_case_or_OCR_repair_no_occurrence_penalty',
        inventory_agreement_rate=equal/valid_pairs if valid_pairs else None,
        shared_title_assertion_errors=sum(r['shared_error'] for r in items),shared_error_denominator=valid_pairs,
        cases=items,source_review_release_gate_failures=failures,
        same_model_deterministic_prompt_error_correlation=True,expert_certified=False,
        inference='independent_requests_do_not_imply_independent_errors'))
    print(valid_pairs,equal,sum(r['shared_error'] for r in items))


if __name__=='__main__':main()
