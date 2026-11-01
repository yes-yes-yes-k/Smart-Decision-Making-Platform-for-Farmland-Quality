"""Real repeated-call diagnostics on a source previously yielding relations."""
import argparse
from dataclasses import asdict
from datetime import UTC,datetime
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--literal-evidence',action='store_true')
    args=parser.parse_args()
    if args.literal_evidence:
        os.environ['KG_EXTRACTION_LITERAL_EVIDENCE']='true'
    os.environ.update(KG_EXTRACTION_BASE_URL='https://api.siliconflow.cn/v1',KG_EXTRACTION_ALLOW_SILICONFLOW='true',
        KG_EXTRACTION_MODEL=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash'))
    from framework.knowledge_graph.adapters.live_graphrag import LiveMicrosoftGraphRagBackend
    from framework.knowledge_graph.contracts import ExtractionRequest,SourceChunk
    from framework.knowledge_graph.schema import load_graph_schema
    from framework.knowledge_graph.conformance import evaluate_extraction_backend
    backend=LiveMicrosoftGraphRagBackend(os.environ.get('KG_GRAPHRAG_PYTHON') or ROOT/'.tools/graphrag-runtime/Scripts/python.exe')
    records=[json.loads(p.read_text(encoding='utf-8')) for p in (args.run_dir/'responses').glob('*.json')]
    candidates=sorted((r for r in records if r['state']=='completed' and r['result']['relations']
        and r['backend_config_digest']==backend._config_digest),key=lambda r:(r['document_id'],r['chunk_index']))
    if not candidates:
        parser.error('no source previously yielding relations for this backend')
    selected=candidates[0]
    manifest=json.loads((args.run_dir/'input-manifest.json').read_text(encoding='utf-8'))
    payload=next(r for r in manifest['requests'] if r['document_id']==selected['document_id']
        and r['chunks'][0]['chunk_index']==selected['chunk_index'])
    request=ExtractionRequest(**{**payload,'chunks':tuple(SourceChunk(**c) for c in payload['chunks'])})
    calls=[]
    class Measured:
        name,version=backend.name,backend.version
        def extract(self,request):
            call={}
            try:
                result=backend.extract(request)
                call.update(state='completed',result=result.to_dict())
                return result
            except Exception as exc:
                call.update(state='failed',code=getattr(exc,'code',type(exc).__name__))
                raise
            finally:
                call['usage']=backend.provider.last_usage
                calls.append(call)
    report=evaluate_extraction_backend(Measured(),request,load_graph_schema())
    diagnostics=args.run_dir/'nonempty-conformance-calls.json'
    diagnostics.write_text(json.dumps(calls,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary=dict(backend_name=backend.name,backend_version=backend.version,backend_config_digest=backend._config_digest,
        passed=report.passed,issues=[asdict(i) for i in report.issues],
        evaluation_mode='up_to_two_uncached_live_calls',actual_calls=len(calls),
        selection='first document/chunk with relations in prior real run, independent of gold answers',
        selected_document_id=selected['document_id'],selected_chunk_index=selected['chunk_index'],
        previously_nonempty=True,call_summaries=[{k:v for k,v in c.items() if k!='result'} | (
            dict(entities=len(c['result']['entities']),relations=len(c['result']['relations']),
                 raw_output_fingerprint=c['result']['raw_output_fingerprint']) if 'result' in c else {}) for c in calls],
        generated_at=datetime.now(UTC).isoformat(),production_approved=False)
    args.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    main()
