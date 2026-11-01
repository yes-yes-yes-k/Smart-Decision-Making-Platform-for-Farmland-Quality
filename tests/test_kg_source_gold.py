import hashlib
import json
from pathlib import Path
import pytest
from scripts.build_kg_source_gold import build, reviewed_span
from framework.knowledge_graph.schema import load_graph_schema
from framework.knowledge_graph.graph_record_transport import json_to_graph_records
from framework.knowledge_graph.adapters.graphrag import MicrosoftGraphRagBackend, GraphRagRelationshipRecord, GraphRagAdapterError
from framework.knowledge_graph.contracts import SourceChunk


def test_reviewed_marker_span_preserves_source_whitespace():
    text = '前言：有效土层\n厚度，改善结构。后记'
    start,end = reviewed_span(text,'有效土层厚度','改善结构。')
    assert text[start:end] == '有效土层\n厚度，改善结构。'


def test_revised_gold_has_literal_bound_spans_and_unchanged_labels():
    root=Path(__file__).resolve().parents[1]
    parent=root/'artifacts/minimal_kg/extraction_gold_v1.jsonl'
    gold=[json.loads(x) for x in parent.read_text(encoding='utf-8').splitlines()]
    snapshots=json.loads((root/'.tools/kg-gold-evaluation/v1/input-manifest.json').read_text(encoding='utf-8')) if (root/'.tools/kg-gold-evaluation/v1/input-manifest.json').exists() else None
    if snapshots is None:
        pytest.skip('local source snapshots not available')
    rows, decisions=build(gold,snapshots)
    assert len(rows)==88 and len(decisions)==94
    assert hashlib.sha256(parent.read_bytes()).hexdigest()=='16af6ee0743856f1a851f841e09b6cfbb6af79c1df83a70b4d7751845e3f29dd'
    for row in rows:
        assert row['relation']==gold[row['source_revision']['original_row']]['relation']
        evidence=row['evidence']
        chunk=next(c for r in snapshots['requests'] for c in r['chunks'] if c['document_id']==evidence['document_id'] and c['chunk_index']==evidence['chunk_index'])
        assert chunk['content'][evidence['span_start']:evidence['span_end']]==evidence['quote']


@pytest.mark.parametrize('quote,valid',[('施用石灰\n治理酸化',True),('石灰可以治理酸化',False),('',False)])
def test_model_quote_must_be_literal_not_paraphrased(quote,valid):
    payload=dict(entities=[dict(name='施用石灰',type='measure'),dict(name='酸化',type='obstacle')],
        relationships=[dict(source='施用石灰',target='酸化',relation_type='addresses',quote=quote)])
    if valid:
        assert 'addresses' in json_to_graph_records(json.dumps(payload),load_graph_schema(),source_text='采用施用石灰\n治理酸化。')
    else:
        with pytest.raises(ValueError,match='invalid_evidence_quote'):
            json_to_graph_records(json.dumps(payload),load_graph_schema(),source_text='采用施用石灰\n治理酸化。')


def test_adapter_carries_exact_quote_span_and_rejects_fabricated_quote():
    chunk=SourceChunk(1,'hash',0,'前言。施用石灰治理酸化。结束',1)
    record=GraphRagRelationshipRecord('r','石灰','酸化',('unit',),relation_type='addresses',quote='施用石灰治理酸化。')
    evidence=MicrosoftGraphRagBackend._evidence(record,{'unit':chunk})[0]
    assert evidence.span_start==3 and evidence.quote=='施用石灰治理酸化。'
    bad=GraphRagRelationshipRecord('r','石灰','酸化',('unit',),quote='并不存在的原文')
    with pytest.raises(GraphRagAdapterError,match='not literal'):
        MicrosoftGraphRagBackend._evidence(bad,{'unit':chunk})


def test_span_coverage_is_supplementary_and_disjoint_quotes_do_not_match():
    from framework.knowledge_graph.gold_evaluation import source_span_coverage
    from copy import deepcopy
    gold=dict(relation=dict(type='addresses',source=dict(type='measure',name='施用石灰'),
        target=dict(type='obstacle',name='土壤酸化')),
        evidence=dict(document_id=1,page=2,chunk_index=1,span_start=10,span_end=20))
    prediction=deepcopy(gold)
    prediction['evidence'].update(span_start=15,span_end=25,quote_sha256='different')
    score=source_span_coverage([gold],[prediction])
    assert score['character_recall']==0.5
    prediction['evidence'].update(span_start=20,span_end=25)
    assert source_span_coverage([gold],[prediction])['gold_rows_with_overlap']==0


def test_experimental_evidence_mode_has_distinct_config_identity(monkeypatch):
    from framework.knowledge_graph.extraction_config import backend_config_digest
    monkeypatch.delenv('KG_EXTRACTION_LITERAL_EVIDENCE',raising=False)
    baseline=backend_config_digest('microsoft-graphrag','3.3.0','schema')
    monkeypatch.setenv('KG_EXTRACTION_LITERAL_EVIDENCE','true')
    experimental=backend_config_digest('microsoft-graphrag','3.3.0','schema')
    assert baseline!=experimental
