"""Offline release invariants. Identity/empty probes are NOT model quality results."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,sha
from scripts.score_kg_silver100 import score_release,DEFAULT
from framework.knowledge_graph.silver_adjudication import build_decision,score_silver_sample
from framework.knowledge_graph.evaluation_v4 import input_digest

def verify():
    manifest=json.loads((DEFAULT/'manifest.json').read_text(encoding='utf-8'))
    rows=read(DEFAULT/'reference.jsonl');ledger=read(DEFAULT/'source-adjudications.jsonl')
    assert len(rows)==100 and [r['index'] for r in rows]==list(range(100))
    assert sha(DEFAULT/'reference.jsonl')==manifest['reference_sha256']
    assert sha(DEFAULT/'source-adjudications.jsonl')==manifest['ledger_sha256']
    assert sha(DEFAULT.parent/'calibration/inputs.jsonl')==manifest['source_inputs_sha256']
    assert [r['visible_input'] for r in rows]==read(DEFAULT.parent/'calibration/inputs.jsonl')
    assert sha(ROOT/'framework/knowledge_graph/silver_adjudication.py')==manifest['validator_sha256']
    for r,item in zip(rows,sorted(ledger,key=lambda r:r['index'])):
        a=r['annotation'];v=r['visible_input']
        assert a==build_decision(v,item['decision']) and a['input_sha256']==input_digest(v)
        assert r['source']['split']=='development'
        for m in a['mentions']:
            f=m['fragment'];text=next(b['text'] for b in v['blocks'] if b['block_id']==f['block_id'])
            assert text[f['span_start']:f['span_end']]==f['text']
        s=score_silver_sample(a,a)
        for key in ('surface_chunk_mentions','surface_context_mentions','surface_relations'):
            if s[key] is not None:assert s[key]['fp']==s[key]['fn']==0
        if not a['eligibility_by_block']['chunk']['mentions']:assert s['chunk_mentions'] is None and not s['body_correct_negative']
    empty=score_release(DEFAULT,[])
    assert empty['samples']==100 and empty['valid_completed']==0 and len(empty['missing_samples'])==100
    assert empty['tasks']['surface_chunk_mentions']['fn']==manifest['counts']['scored_surface_body_entities']
    assert empty['tasks']['surface_relations']['fn']==manifest['counts']['scored_positive_relations']
    assert empty['body_correct_negatives']==0
    history=json.loads((DEFAULT.parent/'history-freeze.json').read_text(encoding='utf-8'))
    assert all(sha(Path(f['path']))==f['sha256'] for f in history['files'])
    report=dict(passed=True,source_decisions_validated=100,literal_bindings=True,fixed_mask_identity_probe=True,
        missing_prediction_denominator=100,missing_body_entity_false_negatives=empty['tasks']['surface_chunk_mentions']['fn'],
        missing_relation_false_negatives=empty['tasks']['surface_relations']['fn'],historical_hashes_unchanged=len(history['files']),
        reference_sha256=manifest['reference_sha256'],model_accuracy_evaluation=False,cloud_calls=0,
        label='offline contract invariants only; not independent semantic accuracy')
    write(DEFAULT/'release-verification.json',report);print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':verify()
