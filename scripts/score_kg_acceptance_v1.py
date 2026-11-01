"""Offline calibration scoring; test scoring is blocked until matching user approval."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_kg_acceptance_v1 import OUT,verify_freeze
from scripts.experiment_kg_recall import read,write,sha
from framework.knowledge_graph.evaluation_v4 import input_digest
from framework.knowledge_graph.evaluation_v4_r3 import validate_r3
from framework.knowledge_graph.acceptance_metrics import extraction_report,qa_report,require_final_approval,evaluate_thresholds

def final_guard(partition):
    if partition!='test':return None
    protocol_path=OUT/'approved-protocol.json';confirmation_path=OUT/'threshold-confirmation.json'
    protocol=json.loads(protocol_path.read_text(encoding='utf-8')) if protocol_path.exists() else {}
    confirmation=json.loads(confirmation_path.read_text(encoding='utf-8')) if confirmation_path.exists() else None
    require_final_approval(protocol,confirmation,config_sha256=sha(OUT/'run-config.json'),threshold_sha256=sha(protocol_path) if protocol_path.exists() else '')
    if protocol.get('implementation_manifest_sha256')!=sha(OUT/'implementation-manifest.json'):raise ValueError('approved_implementation_changed')
    if not {'test/reference-proposals.jsonl','qa/reference-proposals.jsonl','pool/selection.jsonl'}<=set(protocol.get('reference_hashes',{})):raise ValueError('approved_reference_hashes_missing')
    for relative,expected in protocol['reference_hashes'].items():
        path=(OUT/relative).resolve()
        if OUT.resolve() not in path.parents or not path.is_file() or sha(path)!=expected:raise ValueError('approved_reference_changed')
    return protocol

def score_extraction(partition,predictions,evidence_reviews=()):
    verify_freeze();protocol=final_guard(partition)
    sources=read(OUT/partition/'samples.jsonl');inputs={v['sample_id']:v for v in read(OUT/partition/'inputs.jsonl')}
    path=OUT/partition/'reference-proposals.jsonl';references=read(path) if path.exists() else []
    refids={r['visible_input']['sample_id'] for r in references}
    if len(refids)!=len(references) or refids-set(inputs):raise ValueError('invalid_reference_inventory')
    seen=set();parsed=[];invalid=[]
    for p in predictions:
        sid=p['sample_id']
        if sid in seen or sid not in inputs:raise ValueError('duplicate_or_unknown_prediction')
        seen.add(sid)
        if p.get('input_sha256')!=input_digest(inputs[sid]):raise ValueError('prediction_input_hash_mismatch')
        try:a=validate_r3(inputs[sid],p['answer'])
        except (ValueError,KeyError,TypeError) as exc:a=None;invalid.append(dict(sample_id=sid,error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__))
        parsed.append(dict(sample_id=sid,input_sha256=p['input_sha256'],annotation=a))
    tracks={}
    for track in ('representative','challenge'):
        rs=[r for r in references if r['source']['track']==track];ids={r['visible_input']['sample_id'] for r in rs}
        tracks[track]=extraction_report(rs,[p for p in parsed if p['sample_id'] in ids],[r for r in evidence_reviews if r['sample_id'] in ids]) if rs else None
    evaluations={}
    if protocol and len(refids)==len(sources):
        for track,m in tracks.items():
            if m is None:continue
            e=m['tasks']['surface_chunk_mentions'];r=m['tasks']['surface_relations'];ev=m['evidence_support']
            measurements={k:dict(value=value,support=n) for k,value,n in [('entity_precision',e['precision'],e['tp']+e['fp']),('entity_recall',e['recall'],e['tp']+e['fn']),
                ('relation_precision',r['precision'],r['tp']+r['fp']),('relation_recall',r['recall'],r['tp']+r['fn']),('evidence_support',ev['rate'],ev['predicted_positive_relations']),
                ('availability',m['completed']/m['samples'] if m['samples'] else None,m['samples']),('exclusion_rate',m['excluded_body_samples']/m['samples'] if m['samples'] else None,m['samples'])]}
            evaluations[track]=evaluate_thresholds(measurements,protocol['thresholds']['extraction'][track])
    status='fail' if any(e['status']=='fail' for e in evaluations.values()) else 'pass' if len(evaluations)==2 and all(e['status']=='pass' for e in evaluations.values()) else 'inconclusive'
    return dict(status=status,evaluations=evaluations,partition=partition,sampled_total=len(sources),reference_samples=len(refids),missing_reference_samples=sorted(set(inputs)-refids),
        received_predictions=len(seen),missing_predictions=sorted(set(inputs)-seen),invalid_predictions=invalid,tracks=tracks,
        eligible_for_acceptance=len(refids)==len(sources),note='calibration is diagnostic only; final scoring requires matching confirmed thresholds; incomplete reference never yields a pass')

def score_questions(partition,predictions,judgements):
    verify_freeze();protocol=final_guard(partition)
    path=OUT/'qa/reference-proposals.jsonl';refs=[q for q in read(path) if q['partition']==partition] if path.exists() else []
    if len({q['id'] for q in refs})!=len(refs):raise ValueError('duplicate_qa_reference')
    target=20 if partition=='calibration' else 80
    metrics=qa_report(refs,predictions,judgements) if refs else None;evaluation=None
    if protocol and len(refs)==target:
        c=metrics['counts'];supports=dict(availability=c['samples'],supported_answer_rate=c['substantive_answers'],citation_support_rate=c['substantive_answers'],answerable_completion=c['answerable'],correct_refusal=c['unanswerable'],evidence_recall_at_5=c['answerable'])
        evaluation=evaluate_thresholds({k:dict(value=metrics[k],support=n) for k,n in supports.items()},protocol['thresholds']['qa'])
    return dict(status=evaluation['status'] if evaluation else 'inconclusive',evaluation=evaluation,partition=partition,target_questions=target,validated_questions=len(refs),
        metrics=metrics,missing_reference_questions=target-len(refs),
        note='keyword checks do not certify semantic support; no final pass without frozen rules')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('task',choices=['extraction','qa']);p.add_argument('--partition',choices=['calibration','test'],default='calibration');p.add_argument('--predictions',type=Path,required=True);p.add_argument('--reviews',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    final_guard(a.partition)
    predictions=read(a.predictions);reviews=read(a.reviews) if a.reviews else []
    result=score_extraction(a.partition,predictions,reviews) if a.task=='extraction' else score_questions(a.partition,predictions,reviews)
    write(a.output,result);print(json.dumps({k:v for k,v in result.items() if k in ('status','sampled_total','reference_samples','target_questions','validated_questions')}))
