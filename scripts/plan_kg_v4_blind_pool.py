"""Read-only candidate inventory for a future document holdout, never certify blindness."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl
BASE=ROOT/'artifacts/knowledge_platform/gold-v4'

def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.document import Document
    excluded={r['file_sha256'] for r in read(BASE/'exposure-register.jsonl')}
    exposed_ids={r['document_id'] for r in read(BASE/'exposure-register.jsonl')}
    paths=list((ROOT/'artifacts/minimal_kg').glob('extraction_gold_v*.jsonl'))+[
        ROOT/'artifacts/knowledge_platform/gold-rebuild-v3/relation-challenge/codex-reference.jsonl']
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('file_sha256','content_sha256') and isinstance(item,str) and len(item)==64:excluded.add(item)
                if key=='document_id' and type(item) is int:exposed_ids.add(item)
                walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    for path in paths:
        if path.exists():
            for row in read(path):walk(row)
    engine=create_engine(Config.SQLALCHEMY_DATABASE_URI,connect_args={'connect_timeout':5})
    pool=[]
    try:
        with sessionmaker(bind=engine)() as session:
            for doc in session.query(Document).filter_by(status=1,review_status='approved',visibility_scope='public'):
                if doc.id not in exposed_ids and doc.file_hash not in excluded:
                    pool.append(dict(document_id=doc.id,file_sha256=doc.file_hash,document_kind=doc.document_kind,
                        chunk_count=doc.chunk_count,blindness_status='candidate_requires_full_exposure_and_duplicate_audit'))
    finally:engine.dispose()
    directory=BASE/'evaluation-design';directory.mkdir(exist_ok=True)
    jsonl(directory/'unseen-document-candidates.jsonl',sorted(pool,key=lambda r:r['file_sha256'] or ''))
    write(directory/'blind-pool-status.json',dict(candidate_documents=len(pool),known_excluded_documents=len(exposed_ids),
        known_excluded_hashes=len(excluded),source='approved public completed database metadata only; no new chunk text read',
        certified_blind_test_documents=0,labels_created=False,
        limitations=['exposure register is not guaranteed exhaustive','standard revisions and semantic duplicate audit pending','independent label custodian unavailable'],
        selection_allowed=False,reason='calibration and task contract gates must pass first'))
    print(json.dumps(dict(candidate_documents=len(pool),certified_blind_test_documents=0)))

if __name__=='__main__':main()
