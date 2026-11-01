"""Offline review hints across current references; never auto-relabel or exclude."""
from collections import Counter
from pathlib import Path
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,lines,dump


def latin(character):return bool(character and re.fullmatch('[A-Za-z]',character))
def compact(value):return re.sub(r'\s+','',value)


def screen(reference):
    blocks={b['block_id']:b['text'] for b in reference['visible_input']['blocks']}
    entities={e['id']:e for e in reference['reference']['entities']};hints=[]
    for entity in entities.values():
        text=blocks[entity['block_id']];start,end=entity['start'],entity['end'];value=entity['text']
        if value and ((start>0 and latin(text[start-1]) and latin(value[0])) or
            (end<len(text) and latin(value[-1]) and latin(text[end]))):
            hints.append(dict(kind='latin_token_internal_boundary',entity_id=entity['id'],surface=value,
                context=text[max(0,start-35):min(len(text),end+35)]))
        if value.endswith((',', '，',';','；')):
            hints.append(dict(kind='trailing_list_punctuation',entity_id=entity['id'],surface=value))
    for index,relation in enumerate(reference['reference']['relations']):
        assertions=[e['text'] for e in relation['evidence'] if e['role']=='assertion' and e['block_id']=='chunk']
        endpoints={compact(entities[relation[k]]['text']) for k in ['source_id','target_id']}
        if assertions and all(compact(q).strip('.,，。;；') in endpoints for q in assertions):
            hints.append(dict(kind='assertion_spans_only_repeat_endpoint_mentions',relation_index=index,
                relation_type=relation['type'],evidence=assertions))
    return hints


def main():
    calibration={r['sample_id'] for r in readlines(OUT/'dataset-v1/calibration-samples.jsonl')}
    rows=readlines(OUT/'calibration-silver-v1/references.jsonl')+readlines(OUT/'reference-release-v1/test/references.jsonl')
    result=[];counts=Counter();partitions=Counter()
    for reference in rows:
        hints=screen(reference)
        if hints:
            part='calibration' if reference['sample_id'] in calibration else 'test'
            result.append(dict(sample_id=reference['sample_id'],partition=part,hints=hints,
                all_hints_require_source_adjudication=True,labels_changed=False))
            counts.update(h['kind'] for h in hints);partitions[part]+=1
    dest=OUT/'semantic-quality-audit-v1'
    lines(dest/'boundary-review-hints.jsonl',result)
    report=dict(status='inconclusive',references_screened=len(rows),samples_with_review_hints=len(result),
        flagged_samples_by_partition=dict(partitions),hint_counts=dict(counts),
        diagnostic_only_not_error_counts=True,concatenated_PDF_text_can_trigger_valid_entity_boundaries=True,
        no_automatic_relabeling_or_mask_expansion=True,unflagged_samples_not_semantically_certified=True,
        incomplete_final400_roster_not_silently_treated_as_negative=True)
    dump(dest/'boundary-screen-report.json',report);print(json.dumps(report))


if __name__=='__main__':main()
