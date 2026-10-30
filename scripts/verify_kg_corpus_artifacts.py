"""Verify real GraphRAG artifacts against the production candidate adapter, without writes."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from framework.knowledge_graph.adapters.graphrag import (
        GraphRagArtifactBundle,GraphRagEntityRecord,GraphRagRelationshipRecord,
        GraphRagTextUnitRecord,StaticGraphRagArtifactProvider,MicrosoftGraphRagBackend)
    from framework.knowledge_graph.contracts import SourceChunk,ExtractionRequest
    from framework.knowledge_graph.schema import load_graph_schema
    from scripts.annotate_kg_gold_corpus import write_json
    p=argparse.ArgumentParser()
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    sources={r['sample_id']:r['source'] for r in (json.loads(x) for x in args.inputs.read_text(encoding='utf-8').splitlines())}
    records=[json.loads(path.read_text(encoding='utf-8')) for path in (args.run_dir/'responses').glob('*.json')]
    schema=load_graph_schema();checked=0;errors=[]
    for record in records:
        if record['state']!='completed':continue
        s=sources[record['sample_id']];a=record['artifact']
        try:
            bundle=GraphRagArtifactBundle(
                tuple(GraphRagEntityRecord(**e) for e in a['entities']),
                tuple(GraphRagRelationshipRecord(**r) for r in a['relationships']),
                tuple(GraphRagTextUnitRecord(**t) for t in a['text_units']))
            backend=MicrosoftGraphRagBackend(provider=StaticGraphRagArtifactProvider(bundle),schema=schema,version='3.3.0')
            request=ExtractionRequest('artifact-check:'+record['sample_id'],s['document_id'],s['file_sha256'],schema.schema_version,
                (SourceChunk(s['document_id'],s['file_sha256'],s['chunk_index'],s['text'],s['page']),))
            result=backend.extract(request)
            for relation in result.relations:
                for ev in relation.evidence:
                    if ev.quote!=s['text'][ev.span_start:ev.span_end] or ev.content_sha256!=s['file_sha256']:
                        raise ValueError('source_binding_mismatch')
            checked+=1
        except Exception as exc:
            errors.append(dict(sample_id=record['sample_id'],code=getattr(exc,'code',type(exc).__name__)))
    report=dict(expected_inputs=len(sources),observed_responses=len(records),
        completed_artifacts=sum(r['state']=='completed' for r in records),verified=checked,errors=errors,
        complete=len(records)==len(sources),passed=not errors,
        scope='artifact contract, schema direction, original file hash, page/chunk and literal spans; not repeated-call determinism',
        production_writes=False)
    write_json(args.output,report)
    print(json.dumps(report))
    return int(bool(errors))


if __name__=='__main__':
    raise SystemExit(main())
