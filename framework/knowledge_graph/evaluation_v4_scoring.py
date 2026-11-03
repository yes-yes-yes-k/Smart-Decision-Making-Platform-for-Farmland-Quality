"""Task-separated scoring; no expert correctness inferred from AI agreement."""
from collections import Counter
import random
from .evaluation_v4 import mention_key,fact_keys

def metric(gold,pred):
    tp=len(gold&pred)
    return dict(expected=len(gold),predicted=len(pred),tp=tp,fp=len(pred-gold),fn=len(gold-pred),
        precision=tp/len(pred) if pred else None,recall=tp/len(gold) if gold else None,
        f1=2*tp/(len(gold)+len(pred)) if gold or pred else None)

def relation_map(annotation):
    ms={m['id']:m for m in annotation['mentions']}
    return {(mention_key(ms[r['source']]),r['relation_type'],mention_key(ms[r['target']]),r['modality']):r
        for r in annotation['relations'] if r['modality'] in ('asserted','normative')}

def positions(evidence):
    return {(e['block_id'],i) for e in evidence for i in range(e['span_start'],e['span_end'])}

def score_sample(gold,prediction=None):
    completed=prediction is not None
    if completed and gold['input_sha256']!=prediction['input_sha256']:raise ValueError('input_context_mismatch')
    empty=dict(mentions=[],relations=[])
    pred=prediction if completed else empty
    ge,gr=fact_keys(gold);pe,pr=fact_keys(pred)
    entity_eligible=gold['quality']['entity_eligible'] and gold['completeness']['entities']
    relation_eligible=gold['quality']['relation_eligible'] and gold['completeness']['relations']
    def links(a):return {(mention_key(m),m['canonical_name']) for m in a['mentions'] if m['normalization_status']=='known'}
    known_keys={k for k,v in links(gold)}
    gl=links(gold);pl={(k,v) for k,v in links(pred) if k in known_keys}
    # Unknown references are abstentions, never silently treated as incorrect links.
    evidence_gold=set();evidence_pred=set()
    gm,pm=relation_map(gold),relation_map(pred)
    for key in gm.keys()&pm.keys():
        evidence_gold.update((key,*x) for x in positions(gm[key]['evidence']))
        evidence_pred.update((key,*x) for x in positions(pm[key]['evidence']))
    return dict(completed=completed,entity_eligible=entity_eligible,relation_eligible=relation_eligible,
        mentions=metric(ge,pe) if entity_eligible else None,
        chunk_mentions=metric({m for m in ge if m[0]=='chunk'},{m for m in pe if m[0]=='chunk'}) if entity_eligible else None,
        context_mentions=metric({m for m in ge if m[0]!='chunk'},{m for m in pe if m[0]!='chunk'}) if entity_eligible else None,
        normalization_on_reference_known_mentions=metric(gl,pl) if entity_eligible else None,
        known_normalization_mentions=len(known_keys),unknown_normalization_mentions=sum(m['normalization_status']=='unknown' for m in gold['mentions']),
        relations=metric(gr,pr) if relation_eligible else None,
        evidence_character_overlap_on_matched_facts=metric(evidence_gold,evidence_pred) if relation_eligible else None,
        evidence_semantic_sufficiency='requires_independent_review',
        negative=bool(entity_eligible and relation_eligible and not ge and not gr),
        correct_negative=bool(completed and entity_eligible and relation_eligible and not ge and not gr and not pe and not pr))

def score_given_entities(gold,prediction):
    if fact_keys(gold)[0]!=fact_keys(prediction)[0]:raise ValueError('oracle_entity_inventory_changed')
    return score_sample(gold,prediction)['relations']

def score_given_mentions_normalization(gold,prediction):
    if fact_keys(gold)[0]!=fact_keys(prediction)[0]:raise ValueError('oracle_mention_inventory_changed')
    return score_sample(gold,prediction)['normalization_on_reference_known_mentions']

def cluster_bootstrap(sample_scores,document_groups,*,task='mentions',repeats=1000,seed=4):
    groups={}
    for sid,score in sample_scores.items():groups.setdefault(document_groups[sid],[]).append(score)
    names=list(groups);rng=random.Random(seed);estimates=[]
    if len(names)<2:return dict(lower=None,upper=None,reason='insufficient_document_groups')
    for _ in range(repeats):
        tp=fp=fn=0
        for name in rng.choices(names,k=len(names)):
            for score in groups[name]:
                m=score.get(task)
                if m is not None:tp+=m['tp'];fp+=m['fp'];fn+=m['fn']
        if 2*tp+fp+fn:estimates.append(2*tp/(2*tp+fp+fn))
    estimates.sort()
    if not estimates:return dict(lower=None,upper=None,reason='no_positive_or_predicted_facts')
    return dict(lower=estimates[int(.025*(len(estimates)-1))],upper=estimates[int(.975*(len(estimates)-1))],
        method='document-group bootstrap F1 percentile',repeats=repeats,seed=seed,groups=len(names))

def aggregate(sample_scores,document_groups,task='mentions'):
    eligible=[s[task] for s in sample_scores.values() if s.get(task) is not None]
    tp=sum(m['tp'] for m in eligible);fp=sum(m['fp'] for m in eligible);fn=sum(m['fn'] for m in eligible)
    by_group={}
    for sid,s in sample_scores.items():
        if s.get(task) is not None:by_group.setdefault(document_groups[sid],[]).append(s[task])
    macro=[]
    for rows in by_group.values():
        t=sum(m['tp'] for m in rows);f=sum(m['fp'] for m in rows);n=sum(m['fn'] for m in rows)
        if 2*t+f+n:macro.append(2*t/(2*t+f+n))
    return dict(eligible_samples=len(eligible),tp=tp,fp=fp,fn=fn,micro_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
        document_macro_f1=sum(macro)/len(macro) if macro else None,document_macro_support=len(macro),
        interval=cluster_bootstrap(sample_scores,document_groups,task=task),
        availability=sum(s['completed'] for s in sample_scores.values())/len(sample_scores) if sample_scores else None)

def release_gates(calibration,scorer_verified):
    reasons=[]
    if calibration.get('samples')!=100 or calibration.get('paired_completed')!=100:reasons.append('100 paired completed annotations required')
    if not calibration.get('numeric_agreement_gate'):reasons.append('annotation agreement thresholds not met')
    if not calibration.get('adjudication_complete'):reasons.append('adjudication incomplete')
    if not scorer_verified:reasons.append('scorer verification required')
    return dict(allow_ai_reference_expansion=not reasons,allow_model_experiment=not reasons,
        expert_certified=False,production_approved=False,reasons=reasons)
