"""Repeat uncached real calls using a previously nonempty source, never gold labels."""
import argparse
from dataclasses import asdict
from datetime import UTC,datetime
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.annotate_kg_gold_corpus import write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():
        raise ValueError('conformance output exists; use a new version')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    os.environ.update(KG_EXTRACTION_BASE_URL='https://api.siliconflow.cn/v1',
        KG_EXTRACTION_ALLOW_SILICONFLOW='true',KG_EXTRACTION_LITERAL_EVIDENCE='false',
        KG_EXTRACTION_MODEL=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash'))
    from framework.knowledge_graph.adapters.live_graphrag import LiveMicrosoftGraphRagBackend
    from framework.knowledge_graph.contracts import SourceChunk,ExtractionRequest
    from framework.knowledge_graph.conformance import evaluate_extraction_backend
    from framework.knowledge_graph.schema import load_graph_schema
    backend=LiveMicrosoftGraphRagBackend(ROOT/'.tools/graphrag-runtime/Scripts/python.exe')
    config=json.loads((args.run_dir/'config.json').read_text(encoding='utf-8'))
    if config['backend_config_digest']!=backend._config_digest:
        raise ValueError('baseline and conformance configuration differ')
    records=[json.loads(path.read_text(encoding='utf-8')) for path in (args.run_dir/'responses').glob('*.json')]
    nonempty=sorted([r for r in records if r['state']=='completed' and r['artifact']['relationships']],key=lambda r:r['sample_id'])
    if not nonempty:
        raise ValueError('no previously nonempty source')
    selected=nonempty[0]
    row=next(json.loads(x) for x in args.inputs.read_text(encoding='utf-8').splitlines() if json.loads(x)['sample_id']==selected['sample_id'])
    s=row['source'];schema=load_graph_schema()
    request=ExtractionRequest('v3-conformance:'+row['sample_id'],s['document_id'],s['file_sha256'],schema.schema_version,
        (SourceChunk(s['document_id'],s['file_sha256'],s['chunk_index'],s['text'],s['page']),))
    calls=[]
    class Measured:
        name,version=backend.name,backend.version
        def extract(self,request):
            entry={}
            try:
                result=backend.extract(request)
                entry.update(state='completed',result=result.to_dict())
                return result
            except Exception as exc:
                entry.update(state='failed',code=getattr(exc,'code',type(exc).__name__))
                raise
            finally:
                entry['usage']=backend.provider.last_usage
                calls.append(entry)
    report=evaluate_extraction_backend(Measured(),request,schema)
    write_json(args.output.with_name('conformance-calls.json'),calls)
    summary=dict(passed=report.passed,issues=[asdict(i) for i in report.issues],
        backend_config_digest=backend._config_digest,actual_calls=len(calls),
        selection='first lexicographic sample ID with relations in baseline predictions; no gold-based selection',
        sample_id=row['sample_id'],source_text_sha256=s['text_sha256'],
        independent_human_review=False,production_approved=False,
        generated_at=datetime.now(UTC).isoformat(),
        calls=[{k:v for k,v in c.items() if k!='result'} | (dict(
            entities=len(c['result']['entities']),relationships=len(c['result']['relations']),
            fingerprint=c['result']['raw_output_fingerprint']) if 'result' in c else {}) for c in calls])
    write_json(args.output,summary)
    print(json.dumps(summary))


if __name__=='__main__':
    main()
