"""Publish only individually adjudicated examples; never promote model agreement."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def adjudicated_rows(reference,decisions):
    from scripts.annotate_kg_gold_corpus import validate_annotation
    from framework.knowledge_graph.schema import load_graph_schema
    schema=load_graph_schema()
    by_id={r['sample_id']:r for r in reference}
    seen=set();output=[]
    for decision in decisions:
        sid=decision['sample_id']
        if sid in seen or sid not in by_id:
            raise ValueError('duplicate or unknown adjudication sample')
        seen.add(sid)
        row=by_id[sid]
        if decision.get('decision')!='accept':
            continue
        if (not str(decision.get('reviewer','')).strip() or not decision.get('reviewed_at')
                or decision.get('text_sha256')!=row['source']['text_sha256']
                or decision.get('proposal_sha256')!=row['proposal_sha256']):
            raise ValueError('adjudication provenance missing or stale')
        if row['review_priority']>=90:
            raise ValueError('unresolved invalid labels cannot be accepted')
        if hashlib.sha256(row['source']['text'].encode()).hexdigest()!=row['source']['text_sha256']:
            raise ValueError('source snapshot checksum mismatch')
        p=row['proposal']
        if hashlib.sha256(json.dumps(p,ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=row['proposal_sha256']:
            raise ValueError('proposal checksum mismatch')
        verified=validate_annotation(row['source'],dict(entities=p['entities'],relationships=[
            {k:r[k] for k in ('source','target','relation_type','quote')} for r in p['relationships']]),schema)
        if verified['validation_errors']:
            raise ValueError('adjudicated evidence does not bind to source')
        output.append(dict(schema='kg-adjudicated-reference-v3',gold_version='cultivated-land-corpus-gold-v3',
            sample_id=sid,source={k:v for k,v in row['source'].items() if k not in ('annotation_status','gold_approved')},
            entities=p['entities'],relationships=p['relationships'],disposition=p['disposition'],
            review=dict(method='explicit_manual_adjudication_import',**decision),gold_approved=True))
    return sorted(output,key=lambda r:r['sample_id'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--decisions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('use a new output version; existing gold cannot be overwritten')
    reference=[json.loads(x) for x in args.reference.read_text(encoding='utf-8').splitlines() if x.strip()]
    decisions=json.loads(args.decisions.read_text(encoding='utf-8'))['decisions']
    rows=adjudicated_rows(reference,decisions)
    if not rows:
        parser.error('no explicitly adjudicated rows; formal gold not published')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8',newline='\n')
    manifest=dict(schema='kg-adjudicated-gold-manifest-v3',reference_sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
        decisions_sha256=hashlib.sha256(args.decisions.read_bytes()).hexdigest(),output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        formal_gold_rows=len(rows),pending_rows=len(reference)-len(rows),
        split_counts=dict(Counter(r['source']['split'] for r in rows)),production_approved=False)
    args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))


if __name__=='__main__':
    main()
