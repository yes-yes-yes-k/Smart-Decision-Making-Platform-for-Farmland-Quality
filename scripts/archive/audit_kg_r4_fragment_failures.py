"""Classify source-binding errors without repairing or rescoring prior annotations."""
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write
from framework.knowledge_graph.evaluation_v4 import validate_input
from framework.knowledge_graph.evaluation_v4_r3 import align_fragment
from scripts.calibrate_kg_v4_r4 import BASE,OUT

def main():
    inputs={r['sample_id']:r for r in read(BASE/'calibration/inputs.jsonl')[:10]};counts=Counter();details=[]
    for arm in ('A','B'):
        for r in read(OUT/('diagnostic-'+arm)/'responses.jsonl'):
            entries=[t for t in r['trace'] if t['stage']=='entities' and t.get('content')]
            if not entries:continue
            try:payload=json.loads(entries[-1]['content'])
            except ValueError:counts['unparseable_entity_response']+=1;continue
            blocks=validate_input(inputs[r['sample_id']])
            for m in payload.get('mentions',[]):
                fragment=m.get('fragment',{});reason=None
                try:align_fragment(fragment,blocks);continue
                except (ValueError,TypeError,KeyError):pass
                try:
                    align_fragment(dict(fragment,occurrence=0),blocks)
                    reason='text_exists_but_supplied_occurrence_invalid'
                except (ValueError,TypeError,KeyError):reason='text_not_found_even_at_first_occurrence'
                counts[reason]+=1;details.append(dict(arm=arm,sample_id=r['sample_id'],fragment=fragment,flag=reason))
    write(OUT/'fragment-failure-audit.json',dict(counts=counts,details=details,
        interpretation='diagnostic leads only; no index was changed, no failed annotation was promoted, no score recomputed'))
    print(json.dumps(counts))

if __name__=='__main__':main()
