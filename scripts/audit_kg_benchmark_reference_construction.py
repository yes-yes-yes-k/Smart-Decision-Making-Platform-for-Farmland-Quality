"""Source-reference construction evidence, never an expert accuracy estimate."""
from collections import Counter
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,dump,lines
from scripts.audit_kg_reference_correlated_errors import primary_signature,title_assertions
from framework.knowledge_graph.benchmark_reference_gate import check_reference


def compare_pair(left,right,reference):
    a=primary_signature(left);b=primary_signature(right);gold=primary_signature(reference)
    return dict(entity_inventory_agreement=a[0]==b[0],relation_inventory_agreement=a[1]==b[1],
        jointly_omitted_entity_surfaces=len(gold[0]-(a[0]|b[0])),
        jointly_omitted_relation_facts=len(gold[1]-(a[1]|b[1])),
        shared_extra_entity_surfaces=len((a[0]&b[0])-gold[0]),
        shared_extra_relation_facts=len((a[1]&b[1])-gold[1]))


def main():
    membership={r['sample_id']:r for r in readlines(OUT/'dataset-v1/samples.jsonl')}
    items=[];provenance_errors=[];summary={}
    for part in ['calibration','test']:
        base=OUT/'references-v1'/part
        frozen=OUT/('calibration-silver-v1' if part=='calibration' else 'test-silver-v1')
        reference_path=frozen/'references.jsonl' if (frozen/'manifest.json').exists() else OUT/f'reference-release-v1/{part}/references.jsonl'
        refs={r['sample_id']:r for r in readlines(reference_path)} if reference_path.exists() else {}
        config=json.loads((base/'initial/run-config.json').read_text(encoding='utf-8'))
        records={}
        for path in (base/'initial/proposals').glob('*.json'):
            row=json.loads(path.read_text(encoding='utf-8'))
            if row['id'] in records:provenance_errors.append(dict(id=row['id'],error='duplicate_original_response'))
            if config['jobs'].get(row['id'])!=row['job_sha256']:provenance_errors.append(dict(id=row['id'],error='request_hash_mismatch'))
            records[row['id']]=row
        counts=Counter();strata={}
        for sid,sample in membership.items():
            if sample['partition']!=part:continue
            a=records.get('A:'+sid);b=records.get('B:'+sid)
            row=dict(sample_id=sid,partition=part,track=sample['track'],stratum=sample['stratum'],
                reference_available=sid in refs,A_state=a['state'] if a else 'missing',B_state=b['state'] if b else 'missing')
            counts['expected_pairs']+=1
            if a and b:counts['paired_responses_saved']+=1
            if a and b and a['state']==b['state']=='protocol_valid':
                counts['both_protocol_valid']+=1
                left=a['protocol']['materialized_proposal'];right=b['protocol']['materialized_proposal']
                row['A_title_assertion_indices']=title_assertions(a['proposal'])
                row['B_title_assertion_indices']=title_assertions(b['proposal'])
                row['shared_title_assertion_violation']=bool(row['A_title_assertion_indices'] and row['B_title_assertion_indices'])
                if row['shared_title_assertion_violation']:counts['shared_title_assertion_violation_pairs']+=1
                if sid in refs:
                    row.update(compare_pair(left,right,refs[sid]['reference']))
                    counts['valid_pairs_with_AI_reference']+=1
                    for key in ['jointly_omitted_entity_surfaces','jointly_omitted_relation_facts',
                        'shared_extra_entity_surfaces','shared_extra_relation_facts']:
                        counts[key]+=row[key]
            if sid in refs:
                counts['reference_available']+=1
                gate=check_reference(refs[sid])
                if not gate['reference_ready']:provenance_errors.append(dict(sample_id=sid,error='reference_evidence_gate_failed',details=gate['errors']))
                masks=refs[sid]['reference_masks']
                row['fixed_task_mask_counts']=dict(Counter(m['status'] for m in masks))
            items.append(row)
            key=json.dumps(sample['stratum'],sort_keys=True,ensure_ascii=False)
            group=strata.setdefault(key,Counter());group['expected']+=1;group['reference_available']+=sid in refs
        summary[part]=dict(counts=counts,strata={k:dict(v) for k,v in strata.items()},
            reference_is_frozen=(frozen/'manifest.json').exists())
    destination=OUT/'reference-construction-audit-v1'
    lines(destination/'items.jsonl',items)
    dump(destination/'report.json',dict(status='inconclusive',partitions=summary,
        integrity_status='fail' if provenance_errors else 'pass',provenance_errors=provenance_errors,
        all_500_references_available=sum(v['counts']['reference_available'] for v in summary.values())==500,
        independent_requests_do_not_imply_independent_errors=True,
        initial_requests_same_model_same_prompt_temperature_zero=True,
        shared_deviations_are_relative_to_AI_reference_not_expert_truth=True,
        same_model_judge_may_share_unobserved_errors=True,expert_certified=False,
        semantic_accuracy_estimated=False,candidate_backend_scores_computed=False))
    print(json.dumps({k:dict(v['counts']) for k,v in summary.items()},ensure_ascii=False))
    if provenance_errors:raise ValueError('reference_construction_integrity_failed')


if __name__=='__main__':main()
