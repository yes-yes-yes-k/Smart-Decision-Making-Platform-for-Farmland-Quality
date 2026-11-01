"""Persistent isolated GraphRAG runner. Reads source-only frozen inputs, no labels."""
import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.annotate_kg_gold_corpus import write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_input(row):
    if set(row) != {'sample_id','source'}:
        raise ValueError('inference input must contain source only')
    s = row['source']
    if hashlib.sha256(s['text'].encode()).hexdigest() != s['text_sha256']:
        raise ValueError('source text checksum mismatch')
    if any(k in s for k in ('entities','relationships','proposal','annotation','adjudication')):
        raise ValueError('labels must not enter inference inputs')


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    os.environ.update(KG_EXTRACTION_BASE_URL='https://api.siliconflow.cn/v1',
        KG_EXTRACTION_ALLOW_SILICONFLOW='true', KG_EXTRACTION_LITERAL_EVIDENCE='false',
        KG_EXTRACTION_MODEL=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash'))
    from scripts.graphrag_extract import extract
    from framework.knowledge_graph.extraction_config import backend_config_digest
    from framework.knowledge_graph.schema import load_graph_schema
    from importlib.metadata import version
    if version('graphrag') != '3.3.0':
        raise ValueError('runtime_version_mismatch')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    if sha(args.inputs) != manifest['inference_inputs_sha256']:
        raise ValueError('frozen inputs checksum mismatch')
    rows = [json.loads(x) for x in args.inputs.read_text(encoding='utf-8').splitlines()]
    for row in rows:
        validate_input(row)
    config = dict(backend='microsoft-graphrag', runtime='3.3.0',
        source_inputs_sha256=sha(args.inputs), model=os.environ['KG_EXTRACTION_MODEL'],
        backend_config_digest=backend_config_digest('microsoft-graphrag','3.3.0',load_graph_schema().schema_version),
        bridge_sha256=sha(ROOT/'scripts/graphrag_extract.py'),
        transport_sha256=sha(ROOT/'framework/knowledge_graph/graph_record_transport.py'),
        reference_sha256=manifest['reference_sha256'], prompt_contains_answers=False,
        prompt_context='original chunk text only', max_workers=args.workers,
        experiment_profile=args.profile, diagnostics=args.diagnostics)
    if args.profile == 'v9-two-stage':
        config['two_stage_sha256'] = sha(ROOT/'framework/knowledge_graph/two_stage_extraction.py')
        config['evidence_policy'] = 'literal quote <=800 chars with both exact endpoint mentions'
    if args.profile == 'v10-span':
        config['span_module_sha256'] = sha(ROOT/'framework/knowledge_graph/span_extraction.py')
        config['evidence_policy'] = 'token intervals resolved locally to Unicode character spans; quote covers both selected occurrences <=800 chars'
    if args.profile == 'v11-candidate':
        config['candidate_module_sha256'] = sha(ROOT/'framework/knowledge_graph/candidate_selection.py')
        config['selection_module_sha256'] = sha(ROOT/'framework/knowledge_graph/span_extraction.py')
        config['evidence_policy'] = 'fixed lexicon literal source candidates; local sentence windows covering selected occurrences <=800 chars'
    config_hash = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    args.run_dir.mkdir(parents=True,exist_ok=True)
    config_path = args.run_dir/'config.json'
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError('run configuration changed; use a new directory')
    write_json(config_path, config)
    selected = rows[:args.limit] if args.limit else rows
    semaphore = asyncio.Semaphore(args.workers)
    records = []
    start = time.monotonic()

    def progress(state):
        done = len(records)
        write_json(args.run_dir/'progress.json', dict(state=state, total=len(selected), completed=done,
            succeeded=sum(r['state']=='completed' for r in records),
            failed=sum(r['state']=='failed' for r in records),
            elapsed_seconds=round(time.monotonic()-start,2), updated_at=datetime.now(UTC).isoformat()))

    async def one(row):
        async with semaphore:
            s = row['source']
            # sample IDs contain ':'; hash filenames to avoid NTFS alternate streams.
            filename = hashlib.sha256(row['sample_id'].encode()).hexdigest()+'.json'
            path = args.run_dir/'responses'/filename
            if path.exists():
                result = json.loads(path.read_text(encoding='utf-8'))
                if result['config_hash'] != config_hash or result['source_text_sha256'] != s['text_sha256']:
                    raise ValueError('stale response cache')
            else:
                before = time.monotonic()
                try:
                    raw = await extract(dict(chunks=[dict(content=s['text'],chunk_index=s['chunk_index'])]),
                        experiment_profile=args.profile, diagnostics=args.diagnostics)
                    result = dict(state='completed', artifact=raw,usage=raw['usage'])
                except Exception as exc:
                    # Do not log exception messages; provider errors can echo public source or credentials.
                    allowed = {'invalid_model_output','incomplete_model_response','unknown_entity_type',
                        'ambiguous_entity_types','missing_relation_endpoint','invalid_relation_direction',
                        'unknown_relation_type','invalid_evidence_quote'}
                    code = str(exc) if str(exc) in allowed else type(exc).__name__
                    result = dict(state='failed',code=code,usage=getattr(exc,'kg_usage',None), diagnostics=getattr(exc,'kg_trace',None))
                result.update(sample_id=row['sample_id'],source_text_sha256=s['text_sha256'],
                    config_hash=config_hash,elapsed_seconds=time.monotonic()-before)
                write_json(path,result)
            records.append(result)
            progress('running')
            if len(records)%20 == 0 or len(records)==len(selected):
                print(json.dumps(dict(completed=len(records),total=len(selected),failed=sum(r['state']=='failed' for r in records))),flush=True)
    progress('running')
    await asyncio.gather(*(one(row) for row in selected))
    records.sort(key=lambda r:r['sample_id'])
    (args.run_dir/'responses.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in records),encoding='utf-8')
    progress('completed')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--limit',type=int)
    p.add_argument('--profile', choices=['v6','v8-recall','v9-two-stage','v10-span','v11-candidate'], default='v6')
    p.add_argument('--diagnostics', action='store_true')
    args = p.parse_args()
    if not 1<=args.workers<=4:
        p.error('workers must be 1..4')
    logging.disable(logging.CRITICAL)
    asyncio.run(run(args))


if __name__=='__main__':
    main()
