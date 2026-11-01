"""Read-only full-corpus benchmark audit. Flags are review leads, not automatic relabels."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from scripts.score_kg_corpus import normalize,fact_sets
from framework.knowledge_graph.gold_sampling import normalized_text
from framework.knowledge_graph.schema import load_graph_schema

BASE=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3'
OUT=BASE/'dataset-assessment'

def main():
    OUT.mkdir(exist_ok=True)
    rows=read(BASE/'codex-reference.jsonl');manifest=json.loads((BASE/'codex-reference.manifest.json').read_text(encoding='utf-8'))
    assert sha(BASE/'codex-reference.jsonl')==manifest['reference_sha256']
    original=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    assert sha(BASE/'samples.jsonl')==original['sample_sha256']
    stats={};flags=[]
    for split in ('all','development','validation','test'):
        selected=[r for r in rows if split=='all' or r['source']['split']==split]
        eligible=[r for r in selected if r['evaluation_eligible']]
        c=Counter();types=Counter();rt=Counter();rd=defaultdict(set);kinds=Counter();kind_ex=Counter();lengths=[];unique_rel=set();unique_ent=set()
        for row in selected:
            if not row['evaluation_eligible']:kind_ex[row['source']['document_kind']]+=1
        for row in eligible:
            s=row['source'];text=s['text'];nt=normalize(text);kinds[s['document_kind']]+=1
            c[row['disposition']]+=1;c['entity_annotations']+=len(row['entities']);c['relation_annotations']+=len(row['relationships'])
            nonliteral=[]
            for e in row['entities']:
                types[e['type']]+=1;unique_ent.add((e['type'],normalize(e['name'])))
                if normalize(e['name']) not in nt:
                    c['entity_annotations_not_normalized_literal']+=1;nonliteral.append(e)
            if nonliteral:c['samples_with_nonliteral_entities']+=1
            if len(fact_sets(row['entities'],[])[0])!=len(row['entities']):c['samples_with_duplicate_normalized_entities']+=1
            for r in row['relationships']:
                rt[r['relation_type']]+=1;rd[r['relation_type']].add(s['file_sha256']);lengths.append(len(r['quote']))
                unique_rel.add((normalize(r['source']),r['relation_type'],normalize(r['target'])))
                c['whole_chunk_quotes']+=r['quote']==text
                c['quotes_over_800_chars']+=len(r['quote'])>800
                c['relations_with_endpoint_not_literal_in_chunk']+=not all(normalize(r[k]) in nt for k in ('source','target'))
                c['quotes_without_both_endpoint_names']+=not all(normalize(r[k]) in normalize(r['quote']) for k in ('source','target'))
                c['invalid_quote_bindings']+=not (text[r['span_start']:r['span_end']]==r['quote'] and hashlib.sha256(r['quote'].encode()).hexdigest()==r['quote_sha256'])
            c['reference_heading_flag_samples']+=bool(__import__('re').search(r'参考文献|\bReferences\b',text,__import__('re').I))
            c['replacement_character_samples']+='\ufffd' in text
            c['numeric_onlyish_samples']+=sum(x.isalpha() or '\u3400'<=x<='\u9fff' for x in text)<30
            if split=='all':
                flags.append(dict(sample_id=row['sample_id'],index=row['index'],split=s['split'],nonliteral_entities=nonliteral,
                    whole_chunk_quotes=sum(r['quote']==text for r in row['relationships']),
                    quotes_without_both_endpoint_names=sum(not all(normalize(r[k]) in normalize(r['quote']) for k in ('source','target')) for r in row['relationships'])))
        stats[split]=dict(sample_count=len(selected),scored=len(eligible),documents=len({r['source']['file_sha256'] for r in eligible}),
            relation_positive_documents=len({r['source']['file_sha256'] for r in eligible if r['relationships']}),
            document_groups=len({r['source']['leakage_group'] for r in eligible}),counts=c,entity_types=types,relation_types=rt,
            relation_source_documents={k:len(v) for k,v in rd.items()},kind_counts=kinds,excluded_kind_counts=kind_ex,
            unique_entity_type_names=len(unique_ent),unique_directed_triples=len(unique_rel),
            quote_lengths=dict(min=min(lengths,default=0),max=max(lengths,default=0),mean=sum(lengths)/len(lengths) if lengths else None))
    group_splits=defaultdict(set);file_splits=defaultdict(set);text_splits=defaultdict(set)
    for row in rows:
        s=row['source'];group_splits[s['leakage_group']].add(s['split']);file_splits[s['file_sha256']].add(s['split']);text_splits[normalized_text(s['text'])].add(s['split'])
    # Exhaustive cross-split shingle check independently tests the sampler's heuristic.
    sources=[r['source'] for r in rows];sets=[]
    for s in sources:
        t=normalized_text(s['text']);sets.append({t[i:i+5] for i in range(max(1,len(t)-4))})
    duplicates=[]
    for i,a in enumerate(sources):
        for j in range(i):
            b=sources[j]
            if a['split']==b['split']:continue
            x,y=sets[i],sets[j]
            if min(len(x),len(y))<.85*max(len(x),len(y)):continue
            overlap=len(x&y);jac=overlap/max(1,len(x)+len(y)-overlap)
            if jac>=.85:duplicates.append(dict(a=a['sample_id'],b=b['sample_id'],jaccard=jac))
    report=dict(reference_sha256=manifest['reference_sha256'],scope='1000 frozen rows; machine-verifiable checks only, not expert semantic certification',
        source_lengths=dict(exactly_800_chars=sum(len(r['source']['text'])==800 for r in rows),under_200_chars=sum(len(r['source']['text'])<200 for r in rows),maximum=max(len(r['source']['text']) for r in rows)),
        statistics=stats,integrity=dict(reference_hash_valid=True,source_snapshot_hash_valid=True,
            file_split_conflicts=sum(len(v)>1 for v in file_splits.values()),group_split_conflicts=sum(len(v)>1 for v in group_splits.values()),
            normalized_exact_cross_split_duplicates=sum(len(v)>1 for v in text_splits.values()),
            exhaustive_cross_split_jaccard_085_pairs=duplicates),
        label_independence=dict(independent_human_review_count=sum(r['independent_human_review'] for r in rows),reviewer_kinds=dict(Counter(r['reviewer_kind'] for r in rows))),
        caveat='Nonliteral names and absent endpoint strings are flags, not proof of false labels; aliases/coreference/context may explain them. Missing semantic facts cannot be counted by mechanical checks.')
    write(OUT/'audit.json',report);jsonl(OUT/'sample-flags.jsonl',flags)
    # Stable semantic-review packet: content printed separately, never auto-relabelled.
    packet=[];seen=set()
    categories={
        'nonliteral_entity':[r for r in rows if r['evaluation_eligible'] and any(normalize(e['name']) not in normalize(r['source']['text']) for e in r['entities'])],
        'whole_chunk_evidence':[r for r in rows if r['evaluation_eligible'] and any(t['quote']==r['source']['text'] for t in r['relationships'])],
        'negative':[r for r in rows if r['evaluation_eligible'] and not r['entities']],
        'literal_entity_only':[r for r in rows if r['evaluation_eligible'] and r['entities'] and not r['relationships'] and all(normalize(e['name']) in normalize(r['source']['text']) for e in r['entities'])],
        'short_quote_relation':[r for r in rows if r['evaluation_eligible'] and r['relationships'] and all(len(t['quote'])<200 for t in r['relationships'])]}
    for category,pool in categories.items():
        selected=sorted(pool,key=lambda r:hashlib.sha256(r['sample_id'].encode()).hexdigest());count=0
        for r in selected:
            if r['sample_id'] in seen:continue
            seen.add(r['sample_id']);packet.append(dict(category=category,**r));count+=1
            if count==4:break
    jsonl(OUT/'semantic-review-packet.jsonl',packet)
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
