"""Publish only validated development trial drafts; never formal acceptance labels."""
import argparse
from collections import Counter
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,budget_snapshot
from scripts.report_kg_benchmark_pilot import results,signature
from framework.knowledge_graph.benchmark_rebuild import sha256_file


def main():
    parser=argparse.ArgumentParser();parser.add_argument('revision',choices=['r3','r4']);args=parser.parse_args()
    pilot=OUT/f'execution/pilot-{args.revision}'
    run=OUT/f'execution/pilot-{args.revision}-adjudication'
    proto=OUT/f'protocol-{args.revision}'
    controls={r['sample_id']:r for r in readlines(proto/'private-control-keys.jsonl')}
    packets={r['sample_id']:r for n in ['controls-inputs.jsonl','pilot-inputs.jsonl'] for r in readlines(proto/n)}
    records={}
    for p in (run/'proposals').glob('*.json'):
        r=json.loads(p.read_text(encoding='utf-8'));records[r['id'].removeprefix('arbitrate:')]=r
    summary,comparisons=results(args.revision)
    references=[];details=[]
    for sid,packet in packets.items():
        record=records.get(sid)
        check=record.get('protocol',{}) if record else {}
        valid=bool(record and record['state']=='protocol_valid')
        ready=valid and check.get('reference_ready',False)
        item=dict(sample_id=sid,control=sid in controls,
            arbitration_state=record['state'] if record else 'missing',
            source_arbitration_valid=valid,reference_ready=ready,
            unresolved=check.get('unresolved',[]),
            error=record.get('error') if record else 'not_attempted',
            reference_masks=check.get('source_reference_masks'),source_rulings=check.get('source_rulings'),
            relation_reviews=check.get('relation_reviews'),normalization_reviews=check.get('normalization_reviews'))
        if valid and sid in controls:
            item['arbitrated_control_inventory_matches']=signature(check['materialized_proposal'])==signature(controls[sid]['expected'])
        if ready and sid not in controls:
            references.append(dict(sample_id=sid,visible_input={k:packet[k] for k in ['sample_id','blocks']},
                proposal=check['materialized_proposal'],reference_masks=check['source_reference_masks'],
                relation_reviews=check['relation_reviews'],normalization_reviews=check['normalization_reviews'],
                source_rulings=check['source_rulings'],reference_status='development_trial_ai_draft_not_final',
                expert_certified=False,same_model_error_correlation=True,
                annotation_config_sha256=sha256_file(pilot/'run-config.json'),
                arbitration_config_sha256=sha256_file(run/'run-config.json')))
        details.append(item)
    sources=[r for r in details if not r['control']]
    control_rows=[r for r in details if r['control']]
    protocol_pass=summary['critical_control_gate_passed'] and all(r['source_arbitration_valid'] and r['reference_ready'] for r in details)
    report=dict(revision=args.revision,status='inconclusive',protocol_validation='pass' if protocol_pass else 'inconclusive',
        expected=len(packets),arbitration_attempted=len(records),arbitration_states=dict(Counter(r['state'] for r in records.values())),
        real_source_arbitrations_valid=sum(r['source_arbitration_valid'] for r in sources),
        real_source_references_ready=len(references),expected_real_sources=len(sources),
        real_source_cases_unresolved=[r['sample_id'] for r in sources if not r['reference_ready']],
        controls=len(control_rows),controls_arbitrated_exact=sum(r.get('arbitrated_control_inventory_matches',False) for r in control_rows),
        original_control_gate=summary['critical_control_gate_passed'],
        body_positive_relations=sum(r['modality'] in {'asserted','normative'} for ref in references for r in ref['proposal']['relations']),
        normalization_and_surface_tasks_separate=True,
        advisory_quality_does_not_change_scoring_masks=True,
        sample_count_not_increased=True,expert_certified=False,
        same_model_error_correlation=True,handbook_validated=protocol_pass,
        formal_acceptance_ready=False,shared_budget=budget_snapshot())
    lines(run/'source-reference-drafts.jsonl',references)
    lines(run/'adjudication-items.jsonl',details)
    dump(run/'report.json',report)
    dump(pilot/'adjudication-summary.json',report)
    if protocol_pass:
        dump(proto/'validated-protocol.json',dict(scope='internal_AI_silver_annotation_workflow_only',
            handbook_sha256=sha256_file(proto/'annotation-handbook.md'),
            report_sha256=sha256_file(run/'report.json'),expert_certified=False,
            formal_acceptance_thresholds_not_confirmed=True))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
