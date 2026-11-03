"""Fixed-denominator internal acceptance metrics and an explicit confirmation gate."""
import math
import random
from .evaluation_v4_scoring import aggregate
from .silver_adjudication import score_silver_sample

def extraction_report(references,predictions,evidence_reviews=()):
    refs={r['visible_input']['sample_id']:r for r in references};preds={}
    for p in predictions:
        sid=p['sample_id']
        if sid in preds or sid not in refs:raise ValueError('duplicate_or_unknown_prediction')
        if p['input_sha256']!=refs[sid]['annotation']['input_sha256']:raise ValueError('input_context_mismatch')
        preds[sid]=p.get('annotation')
    scores={sid:score_silver_sample(r['annotation'],preds.get(sid)) for sid,r in refs.items()}
    groups={sid:r['source']['isolation_group'] for sid,r in refs.items()}
    tasks=['surface_chunk_mentions','surface_context_mentions','surface_relations']
    result={k:aggregate(scores,groups,task=k) for k in tasks}
    for k,v in result.items():
        v['precision']=v['tp']/(v['tp']+v['fp']) if v['tp']+v['fp'] else None
        v['recall']=v['tp']/(v['tp']+v['fn']) if v['tp']+v['fn'] else None
    review_map={}
    for row in evidence_reviews:
        key=(row['sample_id'],row['relation_index'])
        if key in review_map or row['sample_id'] not in refs:raise ValueError('duplicate_or_unknown_evidence_review')
        review_map[key]=row
    support=total=0
    for sid,p in preds.items():
        if p is None:continue
        for i,r in enumerate(p['relations']):
            if r['modality'] not in ('asserted','normative') or not refs[sid]['annotation']['eligibility_by_block']['chunk']['relations']:continue
            total+=1;support+=review_map.get((sid,i),{}).get('verdict')=='supported'
    return dict(samples=len(refs),received=len(preds),completed=sum(s['completed'] for s in scores.values()),tasks=result,
        excluded_body_samples=sum(not r['annotation']['eligibility_by_block']['chunk']['mentions'] for r in refs.values()),
        evidence_support=dict(supported=support,predicted_positive_relations=total,rate=support/total if total else None,missing_reviews_count_as_unsupported=True),
        fixed_reference_masks=True,sample_scores=scores,expert_certified=False)

def cluster_rate_interval(observations,groups,*,repeats=1000):
    bygroup={}
    for sid,(n,d) in observations.items():bygroup.setdefault(groups[sid],[]).append((n,d))
    keys=list(bygroup)
    if len(keys)<2:return dict(lower=None,upper=None,reason='insufficient_document_groups')
    rng=random.Random(4);values=[]
    for _ in range(repeats):
        n=d=0
        for g in rng.choices(keys,k=len(keys)):
            for a,b in bygroup[g]:n+=a;d+=b
        if d:values.append(n/d)
    values.sort()
    if not values:return dict(lower=None,upper=None,reason='no_metric_support')
    return dict(lower=values[int(.025*(len(values)-1))],upper=values[int(.975*(len(values)-1))],groups=len(keys),method='document-group bootstrap rate percentile')

def qa_report(references,predictions,judgements):
    refs={r['id']:r for r in references};pred={};judges={}
    for p in predictions:
        if p['id'] not in refs or p['id'] in pred:raise ValueError('duplicate_or_unknown_qa_prediction')
        pred[p['id']]=p
    for j in judgements:
        if j['id'] not in refs or j['id'] in judges:raise ValueError('duplicate_or_unknown_qa_judgement')
        judges[j['id']]=j
    counts=dict(samples=len(refs),completed=0,answerable=0,unanswerable=0,answerable_completed=0,correct_refusal=0,
        supported_answers=0,substantive_answers=0,citations_supported=0,judged_answers=0,evidence_recall_sum=0.0)
    per_sample=[]
    for qid,q in refs.items():
        p=pred.get(qid);j=judges.get(qid);answerable=q['answerability']=='answerable'
        counts['answerable']+=answerable;counts['unanswerable']+=not answerable
        complete=bool(p and p.get('state')=='completed');counts['completed']+=complete
        substantive=bool(complete and not p.get('abstain') and p.get('answer','').strip());counts['substantive_answers']+=substantive
        judged=bool(complete and j and j.get('state')=='completed');counts['judged_answers']+=judged
        bound=bool(p and p.get('citation_bindings_validated'))
        supported=bool(judged and substantive and bound and j.get('supported'));counts['supported_answers']+=supported
        correct_answer=bool(answerable and substantive and supported and j.get('answers_question'));counts['answerable_completed']+=correct_answer
        refused=bool(not answerable and complete and p.get('abstain') and judged and j.get('correct_refusal'));counts['correct_refusal']+=refused
        cited=bool(judged and substantive and bound and j.get('citations_supported'))
        counts['citations_supported']+=cited
        required={e['sample_id'] for e in q['evidence']};retrieved=set(p.get('retrieved_sample_ids',[])[:5]) if complete else set()
        recall=len(required&retrieved)/len(required) if answerable and required else None
        if recall is not None:counts['evidence_recall_sum']+=recall
        per_sample.append(dict(id=qid,completed=complete,judged=judged,supported=supported,substantive=substantive,citations_supported=cited,correct_answer=correct_answer,correct_refusal=refused,evidence_recall_at_5=recall))
    div=lambda n,d:n/d if d else None
    intervals={}
    if all(q.get('isolation_groups') for q in refs.values()):
        from .acceptance_data import Groups
        g=Groups({x for q in refs.values() for x in q['isolation_groups']})
        for q in refs.values():
            for x in q['isolation_groups'][1:]:g.union(q['isolation_groups'][0],x)
        groupkeys={qid:g.find(q['isolation_groups'][0]) for qid,q in refs.items()}
        for metric in ('availability','answerable_completion','correct_refusal','evidence_recall_at_5','supported_answer_rate','citation_support_rate'):
            obs={}
            for s in per_sample:
                answerable=refs[s['id']]['answerability']=='answerable'
                if metric=='availability':n,d=int(s['completed']),1
                elif metric=='answerable_completion':n,d=int(s['correct_answer']),int(answerable)
                elif metric=='correct_refusal':n,d=int(s['correct_refusal']),int(not answerable)
                elif metric=='supported_answer_rate':n,d=int(s['supported']),int(s['substantive'])
                elif metric=='citation_support_rate':n,d=int(s['citations_supported']),int(s['substantive'])
                else:n,d=s['evidence_recall_at_5'] or 0,int(answerable)
                obs[s['id']]=(n,d)
            intervals[metric]=cluster_rate_interval(obs,groupkeys)
    return dict(counts=counts,availability=div(counts['completed'],counts['samples']),
        answerable_completion=div(counts['answerable_completed'],counts['answerable']),correct_refusal=div(counts['correct_refusal'],counts['unanswerable']),
        supported_answer_rate=div(counts['supported_answers'],counts['substantive_answers']),
        citation_support_rate=div(counts['citations_supported'],counts['substantive_answers']),
        evidence_recall_at_5=div(counts['evidence_recall_sum'],counts['answerable']),sample_scores=per_sample,
        missing_judgements_never_count_as_supported=True,same_model_judge_bias=True,document_group_intervals=intervals,
        interval_limitation=None if intervals else 'source group metadata unavailable')

def threshold_proposal(metrics):
    # Suggestions are intentionally not executable approval.
    targets=dict(entity_precision=.90,entity_recall=.70,relation_precision=.90,relation_recall=.60,evidence_support=.95,
        availability=.98,qa_supported=.95,qa_answerable_completion=.85,qa_correct_refusal=.90,qa_evidence_recall_at_5=.80)
    supports=metrics.get('supports',{})
    return dict(status='inconclusive',approval_required=True,approved=False,priority='false relations and unsupported answers',
        proposals=[dict(metric=k,proposed_minimum=v,support=supports.get(k),
            maximum_failures_at_current_support=math.floor((1-v)*supports[k]+1e-9) if supports.get(k) is not None else None) for k,v in targets.items()],
        calibration=metrics,notes=['proposals are not thresholds','no final test before explicit user confirmation','zero support is inconclusive, not a perfect score'])

def require_final_approval(protocol,confirmation,*,config_sha256,threshold_sha256):
    if not confirmation or confirmation.get('approved_by')!='user' or confirmation.get('approved') is not True:raise ValueError('user_threshold_confirmation_required')
    if confirmation.get('config_sha256')!=config_sha256 or confirmation.get('threshold_sha256')!=threshold_sha256:raise ValueError('approval_does_not_match_frozen_protocol')
    if not protocol.get('thresholds') or protocol.get('dataset_ready') is not True:raise ValueError('final_dataset_or_thresholds_not_ready')
    return True

def evaluate_thresholds(measurements,thresholds):
    """Explicit confirmed rules only; no zero-support or missing-metric passes."""
    if not thresholds:raise ValueError('empty_threshold_policy')
    results=[]
    for name,spec in thresholds.items():
        operations=[k for k in ('minimum','maximum') if k in spec]
        support=spec.get('minimum_support')
        if len(operations)!=1 or type(support) is not int or support<=0:raise ValueError('invalid_threshold_rule')
        op=operations[0];limit=spec[op]
        if type(limit) not in (float,int) or not 0<=limit<=1:raise ValueError('invalid_threshold_limit')
        measured=measurements.get(name,{});value=measured.get('value');n=measured.get('support',0)
        state='inconclusive'
        if value is not None and n>=support:state='pass' if (value>=limit if op=='minimum' else value<=limit) else 'fail'
        results.append(dict(metric=name,value=value,support=n,rule=spec,status=state))
    status='fail' if any(r['status']=='fail' for r in results) else 'inconclusive' if any(r['status']=='inconclusive' for r in results) else 'pass'
    return dict(status=status,metrics=results)
