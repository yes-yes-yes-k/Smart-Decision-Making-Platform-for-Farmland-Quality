"""Freeze a source-only v4 workspace and blind AI calibration packets; no label migration."""
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha,BASE
from scripts.score_kg_corpus import normalize
from framework.knowledge_graph.evaluation_v4 import digest,input_digest,validate_input

OUT=BASE.parent/'gold-v4'

def main():
    if OUT.exists():raise ValueError('v4 workspace already frozen')
    parent=json.loads((BASE/'codex-reference.manifest.json').read_text(encoding='utf-8'))
    assert sha(BASE/'codex-reference.jsonl')==parent['reference_sha256']
    rows=read(BASE/'codex-reference.jsonl');visible=[]
    for row in rows:
        source=row['source'];blocks=[dict(block_id='chunk',kind='chunk',text=source['text'],text_sha256=digest(source['text']))]
        if source['document_title']:blocks.append(dict(block_id='document_title',kind='document_title',text=source['document_title'],text_sha256=digest(source['document_title'])))
        item=dict(sample_id=row['sample_id'],blocks=blocks);validate_input(item);visible.append(item)
    by_id={r['sample_id']:r for r in visible};dev=[r for r in rows if r['source']['split']=='development'];selected=[];seen=set();docs=Counter();strata={}
    categories={
        'relation':lambda r:bool(r['relationships']),
        'entity_only':lambda r:bool(r['entities']) and not r['relationships'],
        'negative':lambda r:r['evaluation_eligible'] and not r['entities'] and not r['relationships'],
        'normalization':lambda r:any(normalize(e['name']) not in normalize(r['source']['text']) for e in r['entities']),
        'source_quality':lambda r:not r['evaluation_eligible'] or len(r['source']['text'])<200 or '|' in r['source']['text'] or '\ufffd' in r['source']['text']}
    for kind,predicate in categories.items():
        chosen=[]
        for row in sorted([r for r in dev if predicate(r)],key=lambda r:digest('v4-calibration:'+r['sample_id'])):
            group=row['source']['leakage_group']
            if row['sample_id'] in seen or docs[group]>=2:continue
            chosen.append(row);seen.add(row['sample_id']);docs[group]+=1
            if len(chosen)==20:break
        if len(chosen)!=20:raise ValueError('insufficient calibration stratum '+kind)
        strata[kind]=[r['sample_id'] for r in chosen];selected.extend(chosen)
    OUT.mkdir();cal=OUT/'calibration';cal.mkdir()
    jsonl(OUT/'visible-inputs.jsonl',visible)
    jsonl(OUT/'migration-queue.jsonl',[dict(sample_id=r['sample_id'],input_sha256=input_digest(by_id[r['sample_id']]),
        source=r['source'],legacy_reference_sha256=parent['reference_sha256'],status='unannotated_v4',
        legacy_labels_migrated=False,expert_certified=False) for r in rows])
    ordered=sorted([by_id[r['sample_id']] for r in selected],key=lambda r:digest('blind-order:'+r['sample_id']))
    jsonl(cal/'inputs.jsonl',ordered)
    for arm in ('A','B'):jsonl(cal/('annotator-'+arm+'.jsonl'),ordered)
    write(cal/'private-sampling-manifest.json',dict(samples=100,document_groups=len(docs),strata=strata,
        source_split='development',strata_are_diagnostic_not_new_gold=True,visible_sha256=sha(cal/'inputs.jsonl'),
        annotator_packets_identical=sha(cal/'annotator-A.jsonl')==sha(cal/'annotator-B.jsonl'),
        annotations_not_present=True,reference_answers_not_sent=True))
    jsonl(OUT/'exposure-register.jsonl',[dict(file_sha256=r['source']['file_sha256'],leakage_group=r['source']['leakage_group'],
        document_id=r['source']['document_id'],reason='historical_v3_AI_review_and_evaluation',eligible_for_new_blind_test=False)
        for r in {r['source']['file_sha256']:r for r in rows}.values()])
    write(OUT/'manifest.json',dict(contract='kg-evaluation-v4.0',source_rows=1000,source_inputs_sha256=sha(OUT/'visible-inputs.jsonl'),
        legacy_reference_sha256=parent['reference_sha256'],calibration_inputs_sha256=sha(cal/'inputs.jsonl'),
        default_status='unannotated',expert_certified=False,production_approved=False,
        tracks=['historical_source_distribution','diagnostic_relation_challenge','new_blind_test_not_yet_established'],
        prerequisites=['AI calibration agreement and adjudication','new task scorer verification','independent document exposure audit'],
        model_experiments_allowed=False))
    print(json.dumps(dict(source_rows=1000,calibration_samples=100,document_groups=len(docs),status='source_only_frozen')))

if __name__=='__main__':main()
