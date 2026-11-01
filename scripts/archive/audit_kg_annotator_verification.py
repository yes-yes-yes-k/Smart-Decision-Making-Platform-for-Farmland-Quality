"""Keep common target correctness separate from complete annotation usability."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write
from scripts.verify_kg_annotation_load import target_value

def main():
    base=ROOT/'artifacts/knowledge_platform/gold-v4'
    directory=base/'annotator-protocol-load-v1'
    cases={r['id']:r for r in read(directory/'private-answer-key.jsonl')};records=read(directory/'responses.jsonl')
    details=[]
    for r in records:
        available=False;correct=False;value=None
        try:
            if r.get('finish_reason')!='stop':raise ValueError('no_complete_response')
            payload=json.loads(r['content'])
            value=payload['answer'] if r['mode']=='atomic' else target_value(cases[r['id']],payload)
            available=True;correct=value==cases[r['id']]['expected']
        except (ValueError,KeyError,TypeError):pass
        details.append(dict(id=r['id'],round=r['round'],mode=r['mode'],target_available=available,target_correct=correct,
            observed_target=value,fully_usable=r['usable_correct'],validation_error=r.get('error')))
    report={m:dict(attempts=12,target_observable=sum(r['target_available'] for r in details if r['mode']==m),
        target_correct=sum(r['target_correct'] for r in details if r['mode']==m),
        fully_usable=sum(r['fully_usable'] for r in details if r['mode']==m)) for m in ('atomic','full_contract')}
    write(directory/'common-target-audit.json',dict(metrics=report,details=details,
        scope='target correctness can be observed even if another field invalidates the full form; it is not final annotation accuracy'))
    write(directory/'protocol-limitations.json',dict(
        single_judgment_wording_retained_in_exploratory_system=True,
        actual_system_change='answer-only requirement was replaced with task-specified output, but single-judgment wording remained',
        clean_causal_comparison=False,output_protocol_and_instruction_length_differ=True,
        remedies='separate neutral two-control sensitivity check, retain all prior outcomes, no gate relaxation',
        no_claim_that_load_alone_caused_errors=True))
    print(json.dumps(report))

if __name__=='__main__':main()
