"""Freeze source-adjudicated AI reference, retaining unknown-source samples."""
import argparse
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.annotate_kg_gold_corpus import validate_annotation, write_json
from framework.knowledge_graph.schema import load_graph_schema


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def freeze_rows(candidates, ledger, quality, expected=1000):
    if len(candidates) != expected or len(ledger) != expected:
        raise ValueError('complete source review required')
    by_index = {r['index']: r for r in ledger}
    if set(by_index) != set(range(expected)) or len(by_index) != len(ledger):
        raise ValueError('duplicate or missing review index')
    if set(quality) - set(by_index):
        raise ValueError('unknown quality decision index')
    output = []
    for i, candidate in enumerate(candidates):
        decision, source = by_index[i], candidate['source']
        actual = hashlib.sha256(source['text'].encode()).hexdigest()
        if (actual != source['text_sha256'] or actual != decision['source_text_sha256']
                or decision['parent_proposal_sha256'] != candidate['proposal_sha256']
                or decision['sample_id'] != source['sample_id']):
            raise ValueError(f'stale review binding: {i}')
        if (decision['reviewer_kind'] != 'ai_agent' or decision['independent_human_review']
                or not decision.get('reviewed_at') or len(decision.get('reason', '')) < 12):
            raise ValueError(f'invalid review identity: {i}')
        annotation = decision['annotation']
        clean = validate_annotation(source, {
            'entities': annotation['entities'],
            'relationships': [{k:r[k] for k in ('source','target','relation_type','quote')}
                              for r in annotation['relationships']]}, load_graph_schema())
        if clean['validation_errors']:
            raise ValueError(f'invalid reviewed annotation: {i}')
        output.append(dict(schema='kg-codex-reference-v3', index=i,
            sample_id=source['sample_id'], source=source,
            entities=clean['entities'], relationships=clean['relationships'],
            disposition=clean['disposition'], evaluation_eligible=i not in quality,
            source_quality=quality.get(i, 'readable_source'),
            adjudication=decision, reviewer_kind='ai_agent', independent_human_review=False,
            reference_approved=True, production_approved=False))
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--corpus', type=Path, default=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3')
    args = p.parse_args()
    directory = args.corpus
    target = directory/'codex-reference.jsonl'
    if target.exists():
        raise ValueError('frozen reference already exists; use a new version')
    candidates = read_rows(directory/'candidate-reference.jsonl')
    original_samples=read_rows(directory/'samples.jsonl')
    original_manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if digest(directory/'samples.jsonl')!=original_manifest['sample_sha256']:
        raise ValueError('original source snapshot changed')
    if [r['source'] for r in candidates]!=original_samples:
        raise ValueError('candidate sources differ from frozen original samples')
    status = json.loads((directory/'reference-status.json').read_text(encoding='utf-8'))
    if digest(directory/'candidate-reference.jsonl') != status['candidate_sha256']:
        raise ValueError('candidate snapshot changed')
    quality = {x['index']:x['reason'] for x in read_rows(directory/'codex-source-quality.jsonl')}
    rows = freeze_rows(candidates, read_rows(directory/'codex-adjudications.jsonl'), quality)
    target.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in rows), encoding='utf-8')
    inputs = directory/'graphrag-inputs.jsonl'
    # A separate source-only file is the ONLY input accepted by the inference runner.
    inputs.write_text(''.join(json.dumps(dict(sample_id=r['sample_id'],source=r['source']),
        ensure_ascii=False, sort_keys=True)+'\n' for r in rows), encoding='utf-8')
    eligible = [r for r in rows if r['evaluation_eligible']]
    relations = Counter(v['relation_type'] for r in eligible for v in r['relationships'])
    schema = load_graph_schema()
    manifest = dict(schema='kg-codex-reference-manifest-v3', frozen_at=datetime.now(UTC).isoformat(),
        sample_count=len(rows), document_count=len({r['source']['document_id'] for r in rows}),
        evaluation_eligible=len(eligible), unscored_source_quality=len(rows)-len(eligible),
        entities=sum(len(r['entities']) for r in eligible),
        relationships=sum(len(r['relationships']) for r in eligible), relation_types=dict(relations),
        missing_relation_types=sorted(schema.relation_type_ids-set(relations)),
        dispositions=dict(Counter(r['disposition'] for r in eligible)),
        splits=dict(Counter(r['source']['split'] for r in eligible)),
        reference_sha256=digest(target), inference_inputs_sha256=digest(inputs),
        ledger_sha256=digest(directory/'codex-adjudications.jsonl'),
        quality_decisions_sha256=digest(directory/'codex-source-quality.jsonl'),
        candidate_sha256=digest(directory/'candidate-reference.jsonl'), schema_digest=schema.digest,
        reviewer='Codex', reviewer_kind='ai_agent', independent_human_review=False,
        production_approved=False, purpose='user-authorized AI-adjudicated development reference; not expert-certified gold',
        inference_context='original chunk text only; document metadata retained for provenance, not inserted into v6 prompt',
        limitations=['AI adjudication can be wrong; not independent expert certification',
                    'Strict mention scores penalize translations and aliases; no answer-derived alias tuning',
                    'Some adjudicated mentions used document-title context; v6 receives chunk text only'])
    write_json(directory/'codex-reference.manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
