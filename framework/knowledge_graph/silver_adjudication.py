"""Source-first silver adjudication. Model quality suggestions cannot skip visible blocks."""
import copy
from .evaluation_v4 import validate_input,bind,input_digest
from .evaluation_v4_r3 import align_fragment,validate_r3

def review_routes(visible,model_quality=None):
    blocks=validate_input(visible)
    return dict(entity_blocks=list(blocks),relation_blocks=['chunk'],model_quality_is_advisory=True,
        blocks_skipped_by_model_quality=[],requires_source_adjudication=True)

def literal_fragment(visible,block,text,occurrence=0,anchor=None):
    blocks=validate_input(visible)
    if text=='$TITLE':text=blocks['document_title']['text']
    if anchor:
        _,anchor_audit=align_fragment(dict(block_id=block,text=anchor,occurrence=0),blocks)
        anchor_text=blocks[block]['text'][anchor_audit['span_start']:anchor_audit['span_end']]
        local,local_audit=align_fragment(dict(block_id=block,text=text,occurrence=0),{block:dict(text=anchor_text)})
        position=anchor_audit['span_start']+local_audit['span_start'];source=blocks[block]['text'];resolved=local['text'];index=-1;occurrence=-1
        while index<position:
            index=source.find(resolved,index+1);occurrence+=1
            if index<0:raise ValueError('anchor_binding_failed')
        text=resolved
    # Occurrence is chosen explicitly by the adjudicator; it never uses the mention-list index.
    raw,audit=align_fragment(dict(block_id=block,text=text,occurrence=occurrence),blocks)
    return raw,audit

def build_decision(visible,decision):
    if len(decision.get('reason',''))<12:raise ValueError('source_specific_review_reason_required')
    blocks=validate_input(visible);entities=[];binding=[];normalization_proofs=[]
    for i,spec in enumerate(decision.get('entities',[])):
        if isinstance(spec,(tuple,list)):
            kind,text=spec;block='chunk';occurrence=0;canonical=None
        else:
            kind,text=spec['type'],spec['text'];block=spec.get('block','chunk');occurrence=spec.get('occurrence',0);canonical=spec.get('canonical_name')
        fragment,audit=literal_fragment(visible,block,text,occurrence,spec.get('anchor') if isinstance(spec,dict) else None)
        entities.append(dict(id=f'm{i}',type=kind,fragment=fragment,canonical_name=canonical,
            normalization_status='known' if canonical else 'unknown',reason='source-adjudicated literal mention'))
        binding.append(dict(mention_id=f'm{i}',**audit))
        if canonical:
            proof=spec.get('normalization_evidence') if isinstance(spec,dict) else None
            if not proof:raise ValueError('known_normalization_requires_source_proof')
            p,_=literal_fragment(visible,block,proof)
            compact=lambda s:''.join(s.split())
            if compact(canonical) not in compact(p['text']) or compact(fragment['text']) not in compact(p['text']):raise ValueError('normalization_proof_missing_names')
            normalization_proofs.append(dict(mention_id=f'm{i}',canonical_name=canonical,evidence=bind(p,blocks)))
    relations=[]
    for spec in decision.get('relations',[]):
        src,kind,tgt=spec['source'],spec['type'],spec['target']
        if type(src) is not int or type(tgt) is not int or not 0<=src<len(entities) or not 0<=tgt<len(entities):raise ValueError('bad_adjudicated_endpoint')
        evidence=[]
        for ev in spec['evidence']:
            if isinstance(ev,str):block,text,occ='chunk',ev,0
            else:block,text,occ=ev.get('block','chunk'),ev['text'],ev.get('occurrence',0)
            f,a=literal_fragment(visible,block,text,occ);evidence.append(f);binding.append(dict(relation_index=len(relations),**a))
        for m in (entities[src],entities[tgt]):
            if m['fragment']['block_id']!='chunk' and m['fragment'] not in evidence:evidence.append(m['fragment'])
        relations.append(dict(source=f'm{src}',target=f'm{tgt}',relation_type=kind,modality=spec.get('modality','asserted'),
            evidence=evidence,reason=spec.get('reason',decision['reason'])))
    ent=decision.get('entity_complete',True);rel=decision.get('relation_complete',True)
    if type(ent) is not bool or type(rel) is not bool:raise ValueError('explicit_task_completeness_required')
    # This is an adjudicator decision, not a model relevance/readability prediction.
    quality=dict(grade='A' if ent and rel else 'B',entity_eligible=ent or 'document_title' in blocks,
        relation_eligible=rel,numeric_eligible=False,reason=decision['reason'])
    raw=dict(quality=quality,mentions=entities,relations=relations,
        completeness=dict(entities=True,relations=rel),notes='; '.join(decision.get('uncertainties',[])))
    annotation=validate_r3(visible,raw)
    annotation.update(contract_revision='v4-silver-r5',input_sha256=input_digest(visible),
        eligibility_by_block={bid:dict(mentions=ent if bid=='chunk' else decision.get('title_eligible',True),relations=rel if bid=='chunk' else False) for bid in blocks},
        body_annotation_complete=ent,uncertainties=decision.get('uncertainties',[]),
        review_routes=review_routes(visible),adjudication_binding_audit=binding,
        reviewer='Codex',reviewer_kind='ai_agent',review_method='direct_source_adjudication',
        legacy_exposure=True,independent_double_annotation=False,expert_certified=False,production_approved=False)
    if normalization_proofs:annotation['normalization_evidence']=normalization_proofs
    return annotation

def score_scope(annotation,reference=None):
    """Exclude unknown blocks from both labels and predictions; not a correct-negative shortcut."""
    reference=reference if reference is not None else annotation
    result=copy.deepcopy(annotation);elig=reference['eligibility_by_block']
    result['mentions']=[m for m in result['mentions'] if elig[m['fragment']['block_id']]['mentions']]
    kept={m['id'] for m in result['mentions']}
    result['relations']=[r for r in result['relations'] if r['source'] in kept and r['target'] in kept and elig['chunk']['relations']]
    result['quality']['entity_eligible']=any(v['mentions'] for v in elig.values())
    result['quality']['relation_eligible']=elig['chunk']['relations']
    return result


def surface_key(mention):
    """A representative literal occurrence, not exhaustive mention tagging.

    Collapse repeat locations and whitespace only; no guessed aliases, case or OCR repair.
    Exact positions remain a secondary diagnostic in the original scorer.
    """
    f=mention['fragment']
    return f['block_id'],''.join(f['text'].split()),mention['type']


def surface_facts(annotation):
    ms={m['id']:m for m in annotation['mentions']}
    return {surface_key(m) for m in ms.values()},{
        (surface_key(ms[r['source']]),r['relation_type'],surface_key(ms[r['target']]),r['modality'])
        for r in annotation['relations'] if r['modality'] in ('asserted','normative')}


def score_silver_sample(reference,prediction=None):
    from .evaluation_v4_scoring import score_sample,metric
    if prediction is not None and (reference['sample_id']!=prediction['sample_id'] or reference['input_sha256']!=prediction['input_sha256']):
        raise ValueError('input_context_mismatch')
    gold=score_scope(reference)
    pred=score_scope(prediction,reference) if prediction is not None else None
    result=score_sample(gold,pred)
    ge,gr=surface_facts(gold);pe,pr=surface_facts(pred or dict(mentions=[],relations=[]))
    masks=reference['eligibility_by_block']
    # An eligible title cannot turn an excluded chunk into an empty, scored negative.
    for bid,key in [('chunk','chunk_mentions'),('document_title','context_mentions')]:
        eligible=masks.get(bid,{}).get('mentions',False)
        result[key]=result[key] if eligible else None
        result['surface_'+key]=metric({m for m in ge if m[0]==bid},{m for m in pe if m[0]==bid}) if eligible else None
    result['surface_relations']=metric(gr,pr) if masks['chunk']['relations'] else None
    result['body_negative']=bool(masks['chunk']['mentions'] and masks['chunk']['relations'] and not {m for m in ge if m[0]=='chunk'} and not gr)
    result['body_correct_negative']=bool(pred is not None and result['body_negative'] and not {m for m in pe if m[0]=='chunk'} and not pr)
    result['scoring_policy']='representative literal surface inventory primary; exact-span diagnostic; fixed reference masks'
    result['numeric_eligible']=False
    return result
