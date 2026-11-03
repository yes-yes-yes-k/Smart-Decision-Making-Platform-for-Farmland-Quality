"""Read-only source corpus snapshot for a larger, auditable gold rebuild."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--chunks',type=int,default=1000)
    parser.add_argument('--documents',type=int,default=250)
    parser.add_argument('--seed',default='kg-gold-rebuild-20261027-v1')
    args=parser.parse_args()
    if args.chunks<args.documents or args.documents<200:
        parser.error('require at least 200 documents and one chunk per document')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    if (args.output_dir/'samples.jsonl').exists():
        parser.error('snapshot already exists; use a new version directory')
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.document import Document
    from framework.models.document_label import DocumentLabel
    from framework.knowledge_graph.jobs import document_is_graph_eligible
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    from framework.knowledge_graph.gold_sampling import document_order,sample_document_chunks,assign_splits,digest
    engine=create_engine(Config.SQLALCHEMY_DATABASE_URI,connect_args={'connect_timeout':5})
    with sessionmaker(bind=engine)() as session:
        documents=[]
        for d in session.query(Document).filter_by(status=1,review_status='approved',visibility_scope='public'):
            if document_is_graph_eligible(d):
                documents.append(dict(id=d.id,title=d.title or d.doc_name,kind=d.document_kind,
                    file_sha256=d.file_hash,expected_count=d.chunk_count,domain_labels=[]))
        by_id={d['id']:d for d in documents}
        for label in session.query(DocumentLabel).filter_by(review_status='approved'):
            if label.document_id in by_id:
                by_id[label.document_id]['domain_labels'].append(label.label_code)
    engine.dispose()
    reader=WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR)
    samples=[];seen=set();selected=[];rejected=[]
    per_doc=(args.chunks+args.documents-1)//args.documents
    for doc in document_order(documents,args.seed):
        if len(samples)>=args.chunks:
            break
        chunks=reader.read_published_chunks(document_id=doc['id'],content_sha256=doc['file_sha256'],expected_count=doc['expected_count'])
        if len(chunks)!=doc['expected_count']:
            rejected.append(dict(document_id=doc['id'],reason='chunk_count_or_hash_binding_mismatch'));continue
        try:
            rows=sample_document_chunks(doc,chunks,seed=args.seed,count=min(per_doc,args.chunks-len(samples)),seen=seen)
        except ValueError:
            rejected.append(dict(document_id=doc['id'],reason='invalid_page_or_chunk_provenance'));continue
        if rows:
            samples.extend(rows);selected.append(doc)
        if len(selected)%25==0:
            print(json.dumps(dict(documents=len(selected),chunks=len(samples))),flush=True)
    if len(samples)!=args.chunks or len(selected)<200:
        raise ValueError('insufficient eligible source coverage; no final snapshot written')
    splits=assign_splits(samples,args.seed)
    path=args.output_dir/'samples.jsonl'
    path.write_text(''.join(json.dumps(s,ensure_ascii=False,sort_keys=True)+'\n' for s in samples),encoding='utf-8',newline='\n')
    manifest=dict(schema='kg-gold-rebuild-source-corpus-v1',seed=args.seed,read_only=True,
        source_documents=len(documents),source_chunks=sum(d['expected_count'] for d in documents),
        sampled_documents=len(selected),sampled_chunks=len(samples),split_counts=splits,
        kind_counts=dict(Counter(s['document_kind'] for s in samples)),
        domain_counts=dict(Counter(label for s in samples for label in s['domain_labels'])),
        sample_sha256=digest(path.read_text(encoding='utf-8')),
        annotation_status='unannotated',gold_approved=False,formal_gold_rows=0,
        guarantees=['approved public literature only','document file hash binding','literal chunk text snapshot',
            'exact normalized duplicates removed','sampled near-duplicates grouped at shingle Jaccard >= 0.85',
            'source file groups isolated across splits','no embeddings or production facts modified'],
        limitations=['near-duplicate detection is heuristic, not a proof of zero semantic overlap',
            'no parse/OCR or language metadata available for reliable population stratification',
            'labels require annotation and adjudication before formal gold publication'],
        selected_documents=selected,rejected_documents=rejected)
    (args.output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('selected_documents','rejected_documents')},ensure_ascii=False))


if __name__=='__main__':
    main()
