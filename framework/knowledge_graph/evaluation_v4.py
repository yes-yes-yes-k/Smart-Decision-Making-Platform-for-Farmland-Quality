"""Versioned benchmark contract: literal mentions, optional normalization, typed evidence."""
import hashlib
import json
from .schema import load_graph_schema


def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

def input_digest(row):
    return digest(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')))

def bind(fragment,blocks):
    if set(fragment)!={'block_id','text','occurrence'}:raise ValueError('invalid_fragment_fields')
    bid,quote,occurrence=fragment['block_id'],fragment['text'],fragment['occurrence']
    if bid not in blocks or not isinstance(quote,str) or not quote.strip() or type(occurrence) is not int or occurrence<0:
        raise ValueError('invalid_fragment')
    text=blocks[bid]['text'];start=-1
    for _ in range(occurrence+1):
        start=text.find(quote,start+1)
        if start<0:raise ValueError('fragment_not_in_visible_input')
    return dict(block_id=bid,text=quote,span_start=start,span_end=start+len(quote),text_sha256=digest(quote))

def validate_input(row):
    if set(row)!={'sample_id','blocks'} or not isinstance(row['blocks'],list):raise ValueError('invalid_visible_input')
    blocks={b['block_id']:b for b in row['blocks']}
    if len(blocks)!=len(row['blocks']) or 'chunk' not in blocks:raise ValueError('duplicate_or_missing_block')
    for b in blocks.values():
        if set(b)!={'block_id','kind','text','text_sha256'} or b['kind'] not in ('chunk','document_title') or digest(b['text'])!=b['text_sha256']:
            raise ValueError('invalid_block_checksum')
    return blocks

def validate_annotation(visible,answer):
    blocks=validate_input(visible);schema=load_graph_schema()
    if set(answer)!={'quality','mentions','relations','completeness','notes'}:raise ValueError('invalid_annotation_fields')
    quality=answer['quality']
    if set(quality)!={'grade','entity_eligible','relation_eligible','numeric_eligible','reason'} or quality['grade'] not in ('A','B','C'):
        raise ValueError('invalid_quality')
    if any(type(quality[k]) is not bool for k in ('entity_eligible','relation_eligible','numeric_eligible')):raise ValueError('invalid_eligibility')
    if quality['grade']=='C' and any(quality[k] for k in ('entity_eligible','relation_eligible','numeric_eligible')):raise ValueError('unreadable_cannot_be_negative')
    if set(answer['completeness'])!={'entities','relations'} or any(type(v) is not bool for v in answer['completeness'].values()):raise ValueError('invalid_completeness')
    mentions=[];by_id={};seen=set()
    for m in answer['mentions']:
        if set(m)!={'id','type','fragment','canonical_name','normalization_status','reason'}:raise ValueError('invalid_mention_fields')
        if not isinstance(m['id'],str) or m['id'] in by_id or m['type'] not in schema.entity_type_ids:raise ValueError('invalid_mention_id_or_type')
        bound=bind(m['fragment'],blocks);key=(bound['block_id'],bound['span_start'],bound['span_end'],m['type'])
        if key in seen:raise ValueError('duplicate_mention')
        seen.add(key)
        if m['normalization_status'] not in ('known','unknown'):raise ValueError('invalid_normalization')
        if (m['normalization_status']=='unknown' and m['canonical_name'] is not None) or (m['normalization_status']=='known' and (not isinstance(m['canonical_name'],str) or not m['canonical_name'].strip())):
            raise ValueError('invalid_normalization')
        item={**m,'fragment':bound,'context_entity':blocks[bound['block_id']]['kind']!='chunk'}
        mentions.append(item);by_id[m['id']]=item
    relations=[]
    for r in answer['relations']:
        if set(r)!={'source','target','relation_type','modality','evidence','reason'}:raise ValueError('invalid_relation_fields')
        if r['source'] not in by_id or r['target'] not in by_id:raise ValueError('missing_relation_endpoint')
        if not schema.allows(r['relation_type'],by_id[r['source']]['type'],by_id[r['target']]['type']):raise ValueError('invalid_relation_direction')
        if r['modality'] not in ('asserted','normative','hypothetical','negated','unknown'):raise ValueError('invalid_modality')
        if not r['evidence']:raise ValueError('missing_evidence')
        relations.append({**r,'evidence':[bind(e,blocks) for e in r['evidence']]})
    return dict(sample_id=visible['sample_id'],input_sha256=input_digest(visible),quality=quality,mentions=mentions,
        relations=relations,completeness=answer['completeness'],notes=answer['notes'],
        reviewer_kind='ai_agent',expert_certified=False,production_approved=False)

def mention_key(m):
    f=m['fragment'];return(f['block_id'],f['span_start'],f['span_end'],m['type'])

def fact_keys(annotation):
    mentions={m['id']:m for m in annotation['mentions']}
    return {mention_key(m) for m in mentions.values()}, {(
        mention_key(mentions[r['source']]),r['relation_type'],mention_key(mentions[r['target']]),r['modality'])
        for r in annotation['relations'] if r['modality'] in ('asserted','normative')}

def agreement(a,b):
    from scripts.score_kg_corpus import scores
    ae,ar=fact_keys(a);be,br=fact_keys(b)
    # Symmetric F1; precision/recall direction is annotator A -> annotator B, not accuracy.
    return dict(mentions=scores(ae,be),relations=scores(ar,br),quality_equal=a['quality']==b['quality'])
