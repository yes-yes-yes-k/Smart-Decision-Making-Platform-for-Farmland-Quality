"""Re-score actual prior live results on the identical new-gold input corpus."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from framework.knowledge_graph.gold_evaluation import prediction_rows, entity_scores, source_locator_score, source_span_coverage
from framework.knowledge_graph.candidate_pipeline import CanonicalEntityCatalog
from scripts.evaluate_kg_extraction_backend import evaluate_rows, read_jsonl


def rescore(gold, records):
    predictions, entities=[],[]
    catalog=CanonicalEntityCatalog.from_json()
    for record in records:
        if record['state']=='completed':
            rows,items=prediction_rows(record['result'],catalog)
            predictions.extend(rows);entities.extend(items)
    report=evaluate_rows(gold,predictions,backend_name='microsoft-graphrag',backend_version='3.3.0',
        elapsed_seconds=sum(r['elapsed_seconds'] for r in records),
        input_documents=len({r['document_id'] for r in records}),cost_usd=None,
        cost_source='offline re-score of actual live calls; not an additional paid inference run',
        evaluation_mode='live_backend_predictions')
    report['metrics']['entities']=entity_scores(gold,entities)
    report.update(prediction_origin='offline_rescore_of_cached_live_calls', production_approved=False,
        source_locator_score=source_locator_score(gold,predictions),
        source_span_coverage=source_span_coverage(gold,predictions),request_count=len(records),
        failed_requests=[{k:r.get(k) for k in ('document_id','chunk_index','code')} for r in records if r['state']!='completed'])
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gold',type=Path,required=True)
    parser.add_argument('--old-run',type=Path,required=True)
    parser.add_argument('--new-run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    old_manifest=json.loads((args.old_run/'input-manifest.json').read_text(encoding='utf-8'))
    new_manifest=json.loads((args.new_run/'input-manifest.json').read_text(encoding='utf-8'))
    def inputs(manifest):
        return {(r['document_id'],r['chunks'][0]['chunk_index']):r for r in manifest['requests']}
    old_inputs,new_inputs=inputs(old_manifest),inputs(new_manifest)
    if not all(old_inputs.get(k)==v for k,v in new_inputs.items()):
        raise ValueError('Cannot compare: the actual request snapshots differ')
    def records(path):
        rows=[json.loads(p.read_text(encoding='utf-8')) for p in (path/'responses').glob('*.json')]
        selected=[r for r in rows if (r['document_id'],r['chunk_index']) in new_inputs]
        if len(selected)!=len(new_inputs) or len({(r['document_id'],r['chunk_index']) for r in selected})!=len(new_inputs):
            raise ValueError('Missing or duplicate request results')
        if len({r['backend_config_digest'] for r in selected})!=1:
            raise ValueError('Mixed backend versions')
        return selected
    old,new=records(args.old_run),records(args.new_run)
    gold=read_jsonl(args.gold)
    result=dict(schema='kg-same-gold-backend-comparison-v1',gold_sha256=hashlib.sha256(args.gold.read_bytes()).hexdigest(),
        gold_rows=len(gold),request_count=len(new_inputs),identical_source_requests=True,
        old_config=old[0]['backend_config_digest'],new_config=new[0]['backend_config_digest'],
        old_backend=rescore(gold,old),new_backend=rescore(gold,new),
        production_approved=False,
        caveats=['Both sides use the same revised gold and identical source snapshots.',
            'Old side reuses actual live results, including failures; this is not a fresh old-backend inference run.',
            'No gold labels or quotes were supplied in inference prompts.',
            'Source review was performed by Codex, not independently human adjudicated.',
            'Gold has positive facts only, not exhaustive negative annotation.'])
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('gold_rows','request_count','old_config','new_config')}))


if __name__=='__main__':
    main()
