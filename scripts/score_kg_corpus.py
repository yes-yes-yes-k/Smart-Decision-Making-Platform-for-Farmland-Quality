"""Chunk-level scoring retains isolated entities, negatives and provider failures."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.annotate_kg_gold_corpus import write_json


def normalize(value):
    # Preserve mathematical signs, decimals, chemical indices and identifiers.
    return ''.join(unicodedata.normalize('NFKC',value).casefold().split())


def fact_sets(entities,relations):
    lookup={normalize(e['name']):e['type'] for e in entities}
    es={(e['type'],normalize(e['name'])) for e in entities}
    def key(r):
        s,t=normalize(r['source']),normalize(r['target'])
        if s not in lookup or t not in lookup:
            raise ValueError('prediction relation endpoint missing')
        return (lookup[s],s,r['relation_type'],lookup[t],t)
    return es,{key(r) for r in relations},{(*key(r),r['quote_sha256']) for r in relations}


def scores(gold,prediction):
    tp=len(gold & prediction)
    precision=tp/len(prediction) if prediction else None
    recall=tp/len(gold) if gold else None
    return dict(expected=len(gold),predicted=len(prediction),true_positive=tp,
        false_positive=len(prediction-gold),false_negative=len(gold-prediction),
        precision=precision,recall=recall,
        f1=(2*tp/(len(gold)+len(prediction))) if gold or prediction else None)


def prediction(record,source):
    if record['state']!='completed':
        return [],[]
    if record['source_text_sha256']!=source['text_sha256']:
        raise ValueError('prediction source checksum mismatch')
    a=record['artifact']
    entities=[dict(name=e['title'],type=e['entity_type']) for e in a['entities']]
    relations=[]
    for r in a['relationships']:
        quote=r.get('quote',source['text'])
        if quote not in source['text']:
            raise ValueError('prediction evidence not literal')
        start=source['text'].index(quote)
        relations.append(dict(source=r['source'],target=r['target'],relation_type=r['relation_type'],
            quote=quote,span_start=start,span_end=start+len(quote),
            quote_sha256=hashlib.sha256(quote.encode()).hexdigest()))
    return entities,relations


def evaluate(reference,records):
    by_id={r['sample_id']:r for r in records}
    if len(by_id)!=len(records):
        raise ValueError('duplicate prediction sample')
    expected_ids={r['sample_id'] for r in reference}
    if set(by_id)-expected_ids:
        raise ValueError('unknown prediction sample')
    report={}
    details=[]
    for split in ['all','development','validation','test']:
        selected=[r for r in reference if split=='all' or r['source']['split']==split]
        eligible=[r for r in selected if r['evaluation_eligible']]
        gold_sets=[set(),set(),set()];pred_sets=[set(),set(),set()]
        negatives=correct_negatives=complete=fail=missing=exact_chunks=0
        span_total=span_covered=0
        types=Counter()
        for row in eligible:
            sid=row['sample_id']
            record=by_id.get(sid,dict(state='missing'))
            completed=record['state']=='completed'
            complete+=completed
            fail+=record['state']=='failed'
            missing+=record['state']=='missing'
            pe,pr=prediction(record,row['source'])
            gs=fact_sets(row['entities'],row['relationships'])
            ps=fact_sets(pe,pr)
            for i in range(3):
                gold_sets[i].update((sid,*k) for k in gs[i])
                pred_sets[i].update((sid,*k) for k in ps[i])
            negative=not gs[0] and not gs[1]
            negatives+=negative
            correct_negatives+=bool(negative and completed and not ps[0] and not ps[1])
            exact_chunks+=bool(completed and gs[:2]==ps[:2])
            for r in row['relationships']:
                types[r['relation_type']]+=1
                # Overlap is explicitly supplementary; full-chunk v6 evidence cannot establish precise citation.
                key=next(iter(fact_sets(row['entities'],[r])[1]))
                intervals=[]
                for p in pr:
                    if key in fact_sets(pe,[p])[1]:
                        lo=max(r['span_start'],p['span_start']);hi=min(r['span_end'],p['span_end'])
                        if hi>lo:intervals.append((lo,hi))
                positions=set()
                for lo,hi in intervals:positions.update(range(lo,hi))
                span_total+=r['span_end']-r['span_start'];span_covered+=len(positions)
            if split=='all':
                details.append(dict(sample_id=sid,index=row['index'],split=row['source']['split'],
                    state=record['state'],entities=scores(gs[0],ps[0]),relations=scores(gs[1],ps[1]),
                    exact_facts=bool(completed and gs[:2]==ps[:2])))
        report[split]=dict(sample_count=len(selected),scored_samples=len(eligible),
            excluded_source_quality=len(selected)-len(eligible),completed_requests=complete,
            failed_requests=fail,missing_requests=missing,
            entities=scores(gold_sets[0],pred_sets[0]),relations=scores(gold_sets[1],pred_sets[1]),
            exact_evidence=scores(gold_sets[2],pred_sets[2]),relation_type_counts=dict(types),
            negative_samples=negatives,correct_negative_samples=correct_negatives,
            negative_accuracy=correct_negatives/negatives if negatives else None,
            exact_fact_samples=exact_chunks,exact_fact_accuracy=exact_chunks/len(eligible) if eligible else None,
            matching_fact_span_coverage=dict(expected_characters=span_total,covered_characters=span_covered,
                recall=span_covered/span_total if span_total else None))
        from framework.knowledge_graph.schema import load_graph_schema
        report[split]['by_relation_type']={kind:scores(
            {k for k in gold_sets[1] if k[3]==kind},
            {k for k in pred_sets[1] if k[3]==kind})
            for kind in sorted(load_graph_schema().relation_type_ids)}
    return report,details


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--corpus',type=Path,default=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3')
    p.add_argument('--run-dir',type=Path,required=True)
    args=p.parse_args()
    directory=args.corpus
    manifest=json.loads((directory/'codex-reference.manifest.json').read_text(encoding='utf-8'))
    raw=(directory/'codex-reference.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest['reference_sha256']:
        raise ValueError('frozen reference changed')
    reference=[json.loads(x) for x in raw.decode('utf-8').splitlines()]
    records=[json.loads(path.read_text(encoding='utf-8')) for path in sorted((args.run_dir/'responses').glob('*.json'))]
    config=json.loads((args.run_dir/'config.json').read_text(encoding='utf-8'))
    config_hash=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    if config['reference_sha256']!=manifest['reference_sha256'] or any(r['config_hash']!=config_hash for r in records):
        raise ValueError('response configuration/reference changed')
    report,details=evaluate(reference,records)
    usage=Counter()
    for r in records:usage.update(r.get('usage') or {})
    output=dict(schema='kg-corpus-evaluation-v3',backend='Microsoft GraphRAG 3.3.0',
        config=config,
        reference_sha256=manifest['reference_sha256'],reviewer_kind='ai_agent',
        independent_human_review=False,production_approved=False,
        complete=len(records)==len(reference) and report['all']['missing_requests']==0,
        attempted_samples=len(records),sample_count=len(reference),metrics=report,
        usage=dict(usage),provider_failures=dict(Counter(r.get('code') for r in records if r['state']=='failed')),
        money_cost=None,
        limitations=manifest['limitations']+[
            'Exact typed-mention matching with case/Unicode/whitespace normalization only; translations are unmatched',
            'v6 attaches the whole original chunk as relation evidence; span coverage is not citation precision',
            'Some reviewed relations use a whole chunk as contextual evidence; exact matches on those do not demonstrate precise excerpt generation',
            'Failure counts as missed gold and never a correct negative; unreadable-source samples are unscored',
            'No tuning or backend selection based on validation/test labels; holdout is document-disjoint, AI-reviewed'])
    progress_path=args.run_dir/'progress.json'
    progress=json.loads(progress_path.read_text(encoding='utf-8')) if progress_path.exists() else {}
    seconds=progress.get('elapsed_seconds')
    output['performance']=dict(wall_seconds=seconds,
        requests_per_wall_minute=(len(records)*60/seconds if seconds else None),
        summed_request_seconds=sum(r.get('elapsed_seconds',0) for r in records),
        workers=config['max_workers'],timing_scope='real inference runner invocation; not annotation or adjudication time')
    write_json(directory/'graphrag-v6-codex-report.json',output)
    (directory/'graphrag-v6-codex-errors.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in details),encoding='utf-8')
    print(json.dumps(dict(complete=output['complete'],attempted=len(records),metrics=report['all'],usage=dict(usage))))


if __name__=='__main__':
    main()
