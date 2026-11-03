"""Reference support counts, not extraction quality or final acceptance scores."""
from collections import Counter,defaultdict
from pathlib import Path
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,dump
from framework.knowledge_graph.benchmark_protocol import load_schema


def surface(e):return e['type'],e['block_id'],re.sub(r'\s+','',e['text'])


def support_counts(references,membership):
    facts=defaultdict(set);groups=defaultdict(set);conditional=defaultdict(set);masks=Counter();entity_counts=Counter()
    for r in references:
        sample=membership[r['sample_id']];group=sample['isolation_group'];entities={e['id']:e for e in r['reference']['entities']}
        for key in {surface(e) for e in entities.values()}:entity_counts[key[1]+':'+key[0]]+=1
        for relation in r['reference']['relations']:
            if relation['modality'] not in ['asserted','normative']:continue
            if not any(e['block_id']=='chunk' and e['role']=='assertion' for e in relation['evidence']):continue
            key=(group,relation['type'],surface(entities[relation['source_id']]),surface(entities[relation['target_id']]),relation['modality'])
            facts[relation['type']].add(key);groups[relation['type']].add(group)
            conditional[relation['type']].add(key+(json.dumps(relation.get('conditions',[]),ensure_ascii=False,sort_keys=True),))
        masks.update(m['block_id']+':'+m['task']+':'+m['status'] for m in r['reference_masks'])
    return dict(entity_surface_items_per_sample=dict(entity_counts),fixed_reference_mask_counts=dict(masks),
        relations={kind:dict(unique_group_and_literal_endpoint_facts=len(values),document_groups=len(groups[kind]),
            conditional_claims=len(conditional[kind])) for kind,values in facts.items()},
        alias_semantic_deduplication_certified=False)


def main():
    membership={r['sample_id']:r for r in readlines(OUT/'dataset-v1/samples.jsonl')}
    result={}
    for track in ['representative','challenge']:
        for part in ['calibration','test']:
            key=track+':'+part;expected=[r for r in membership.values() if r['track']==track and r['partition']==part]
            path=OUT/f'reference-release-v1/{part}/references.jsonl'
            if part=='calibration' and (OUT/'calibration-silver-v1/manifest.json').exists():path=OUT/'calibration-silver-v1/references.jsonl'
            if part=='test' and (OUT/'test-silver-v1/manifest.json').exists():path=OUT/'test-silver-v1/references.jsonl'
            references=[r for r in readlines(path) if membership[r['sample_id']]['track']==track] if path.exists() else []
            result[key]=dict(expected=len(expected),source_reviewed_and_necessary_checks_passed=len(references),
                still_unlabeled_or_unresolved=len(expected)-len(references),support=support_counts(references,membership),
                status='inconclusive',missing_reference_is_not_negative=True)
    types=[r['id'] for r in load_schema(ROOT)['relation_types']]
    observed=result['challenge:test']['support']['relations']
    coverage={kind:dict(facts=observed.get(kind,{}).get('unique_group_and_literal_endpoint_facts',0),
        document_groups=observed.get(kind,{}).get('document_groups',0),
        missing_facts=max(0,30-observed.get(kind,{}).get('unique_group_and_literal_endpoint_facts',0)),
        missing_document_groups=max(0,10-observed.get(kind,{}).get('document_groups',0))) for kind in types}
    complete=all(r['still_unlabeled_or_unresolved']==0 for r in result.values())
    sufficient=complete and all(not r['missing_facts'] and not r['missing_document_groups'] for r in coverage.values())
    dump(OUT/'reference-release-v1/coverage-report.json',dict(status='inconclusive',tracks=result,
        relation_types=types,final_challenge_target_per_type=dict(facts=30,document_groups=10),
        final_challenge_type_coverage=coverage,all_500_references_available=complete,
        final_coverage_not_yet_established=not complete,all_relation_type_targets_met=sufficient,
        insufficient_types=[kind for kind,row in coverage.items() if row['missing_facts'] or row['missing_document_groups']],
        coverage_gaps_are_not_permission_to_replace_samples=True,
        candidate_backend_scores_computed=False,expert_certified=False))
    print({k:(v['source_reviewed_and_necessary_checks_passed'],v['expected']) for k,v in result.items()})


if __name__=='__main__':main()
