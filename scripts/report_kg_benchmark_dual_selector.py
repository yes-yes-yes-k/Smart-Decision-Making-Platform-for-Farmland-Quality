"""All requested cases stay in denominators; contract checks are not semantics."""
from collections import Counter
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,lines,dump,budget_snapshot
from scripts.pilot_kg_benchmark_dual_selector import RUN

ANCHORS=dict(cn_effect='缓解',en_effect='alleviated',joined_english='alleviated',negation='未提高',planned='拟')


def control_check(proposal,key):
    entities={e['id']:e for e in proposal['entities']}
    inventory={(e['type'],e['text']) for e in entities.values()}
    relations={(r['type'],entities[r['source_id']]['text'],entities[r['target_id']]['text'],r['modality']) for r in proposal['relations']}
    expected_entities={tuple(x) for x in key['entities']};expected_relations={tuple(x) for x in key['relations']}
    anchor=ANCHORS.get(key['sample_id'].rsplit(':',1)[1]);support=[]
    for relation in proposal['relations']:
        source=entities[relation['source_id']]['text'];target=entities[relation['target_id']]['text']
        assertions=[e['text'] for e in relation['evidence'] if e['block_id']=='chunk' and e['role']=='assertion']
        support.append(any(source in text and target in text and (not anchor or anchor in text) for text in assertions))
    return dict(entity_inventory_exact=inventory==expected_entities,relation_inventory_exact=relations==expected_relations,
        control_assertion_contains_endpoints_and_predicate=all(support),
        expected_entities=sorted(expected_entities),actual_entities=sorted(inventory),
        expected_relations=sorted(expected_relations),actual_relations=sorted(relations),
        control_full_pass=inventory==expected_entities and relations==expected_relations and all(support))


def main(run=None):
    global RUN
    if run is not None:RUN=Path(run)
    config=json.loads((RUN/'run-config.json').read_text(encoding='utf-8'))
    keys={r['sample_id']:r for r in readlines(RUN/'private-control-keys.jsonl')}
    records={}
    for path in (RUN/'proposals').glob('*.json'):
        row=json.loads(path.read_text(encoding='utf-8'))
        if row['job_sha256']!=config['jobs'][row['id']]:raise ValueError('pilot_response_job_changed')
        records[row['id']]=row
    items=[]
    for job in config['jobs']:
        role,sid=job.split(':',1);row=records.get(job)
        item=dict(id=job,sample_id=sid,role=role,synthetic_control=sid in keys,
            state=row['state'] if row else 'missing',protocol_valid=bool(row and row['state']=='protocol_valid'))
        if row and row['state']!='protocol_valid':item['error']=row.get('error') or row.get('protocol',{}).get('errors')
        if item['protocol_valid']:
            p=row['protocol']['materialized_proposal']
            if sid in keys:item.update(control_check(p,keys[sid]))
            else:item.update(materialized_proposal=p,semantic_accuracy_not_automatically_certified=True)
        elif sid in keys:item['control_full_pass']=False
        items.append(item)
    controls=[r for r in items if r['synthetic_control']];sources=[r for r in items if not r['synthetic_control']]
    complete=len(records)==len(config['jobs'])
    passed=complete and all(r['protocol_valid'] for r in items) and all(r['control_full_pass'] for r in controls)
    report=dict(status='pass' if passed else 'fail' if complete else 'inconclusive',
        scope='selector_contract_and_fresh_control_probe_only_not_reference_release',
        expected_requests=len(config['jobs']),saved_responses=len(records),states=dict(Counter(r['state'] for r in items)),
        controls_expected=len(controls),controls_protocol_valid=sum(r['protocol_valid'] for r in controls),
        controls_full_pass=sum(r['control_full_pass'] for r in controls),
        failed_sources_expected=len(sources),failed_sources_protocol_valid=sum(r['protocol_valid'] for r in sources),
        permit_bulk_resume=False,permit_lift_semantic_hold=False,old_reference_labels_modified=False,
        fresh_controls_not_population_accuracy=True,same_model_error_correlation=True,expert_certified=False,
        independent_materialized_semantic_review_still_required=True,shared_budget=budget_snapshot())
    lines(RUN/'scored-items.jsonl',items);dump(RUN/'report.json',report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path)
    main(parser.parse_args().run)
