"""Read-only metadata review packets; no model calls and no automatic labeling."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,SOURCE,dump,lines,readlines
from framework.knowledge_graph.benchmark_rebuild import sha256_file

DEST=OUT/'metadata-review-preparation'


def current_qualification(documents):
    from dotenv import load_dotenv
    from sqlalchemy import create_engine,text,bindparam
    load_dotenv(ROOT/'.env')
    from framework.config import Config
    engine=create_engine(Config.SQLALCHEMY_DATABASE_URI,connect_args={'connect_timeout':5})
    try:
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            stmt=text('SELECT id,file_hash,status,review_status,visibility_scope,processing_stage FROM kb_document WHERE id IN :ids').bindparams(bindparam('ids',expanding=True))
            rows={r.id:dict(r._mapping) for r in conn.execute(stmt,dict(ids=[d['id'] for d in documents]))}
    finally:engine.dispose()
    result={}
    for d in documents:
        r=rows.get(d['id'])
        result[d['id']]=bool(r and r['file_hash']==d['file_hash'] and r['status']==1 and
            r['review_status']=='approved' and r['visibility_scope']=='public' and r['processing_stage']=='completed')
    return result


def page_sections(page_number,text):
    raw=text.splitlines(keepends=True)
    # Include title/cover, footer, and identifier neighborhoods. No claim that
    # this window is the complete paper or the complete language distribution.
    wanted=set(range(min(80,len(raw))))|set(range(max(0,len(raw)-20),len(raw)))
    for i,value in enumerate(raw):
        if re.search(r'10\.\d{4,9}/|\b(?:GB|NY|HJ|LY|DB\d{2})\s*[/／-]?\s*T?\s*\d',value,re.I):
            wanted.update(j for j in (i-1,i,i+1) if 0<=j<len(raw))
    offset=0;result=[]
    for i,value in enumerate(raw):
        if i in wanted:
            for start in range(0,len(value),700):
                quote=value[start:start+700]
                result.append(dict(id=f'page{page_number}:line{i}:part{start//700}',kind='pdf_page_text',
                    page=page_number,start=offset+start,end=offset+start+len(quote),text=quote,
                    page_text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()))
        offset+=len(value)
    return result


def main():
    import fitz
    pool=readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl')
    docs=[d for d in pool if d['source_paths'] and d['chunk_status']=='verified' and
        d['exposure_status']=='no_exposure_found_in_audited_records' and not d['identity_or_duplicate_candidate_pending']]
    qualification=current_qualification(docs)
    packets=[];failures=[]
    for d in docs:
        if not qualification[d['id']]:
            failures.append(dict(document_id=d['id'],reason='current_qualification_or_hash_changed'));continue
        paths=[SOURCE/p for p in d['source_paths']]
        original=next((p for p in paths if p.is_file() and sha256_file(p)==d['file_hash']),None)
        if original is None:
            failures.append(dict(document_id=d['id'],reason='source_file_bytes_changed_or_missing'));continue
        sections=[]
        try:
            with fitz.open(original) as pdf:
                for i in range(min(2,len(pdf))):sections.extend(page_sections(i+1,pdf[i].get_text()))
                pages=len(pdf)
        except Exception as exc:
            failures.append(dict(document_id=d['id'],reason='pdf_read_'+type(exc).__name__));continue
        chunks=readlines(OUT/f"audit/chunks/{d['id']}.jsonl")
        positions=sorted({0,len(chunks)//2,len(chunks)-1})
        for position in positions:
            c=chunks[position];quote=c['text'][:450]
            sections.append(dict(id='stored_chunk:'+str(c['chunk_index']),kind='stored_chunk_excerpt',
                sample_id=c['sample_id'],page=c['page'],start=0,end=len(quote),text=quote,
                full_chunk_text_sha256=c['text_sha256']))
        packet=dict(document_id=d['id'],file_sha256=d['file_hash'],
            isolation_group=d['isolation_group'],filename_hint=d['doc_name'],filename_is_unverified_hint=True,
            sections=sections,profile_scope='first_two_pdf_page_windows_and_three_stored_chunk_prefixes',
            pdf_pages=pages,pdf_parser_version=fitz.VersionBind,
            source_topic_directories=sorted({p.split('/')[0] for p in d['source_paths']}),
            original_database_language=d['language'],current_public_approved_completed_verified=True,
            prepared_only=True,identity_verified_by_model=False,
            visual_review_required_if_no_readable_pdf_identity=not any(s['kind']=='pdf_page_text' and len(s['text'].strip())>5 for s in sections))
        packets.append(packet)
    lines(DEST/'source-packets.jsonl',packets)
    lines(DEST/'read-or-qualification-failures.jsonl',failures)
    report=dict(status='prepared_no_model_judgments',candidate_documents=len(docs),prepared_documents=len(packets),
        current_qualification_verified=sum(qualification.values()),failures=len(failures),
        pdf_text_identity_windows_empty=sum(p['visual_review_required_if_no_readable_pdf_identity'] for p in packets),
        language_labels_generated=0,verified_doi_labels_generated=0,cloud_calls=0,production_writes=False,
        source_images_not_sent=True,original_files_unchanged=True,
        source_packet_sha256=sha256_file(DEST/'source-packets.jsonl'),
        caution='windows are metadata evidence; not complete-document parsing quality certification; no quality-based sample exclusion')
    dump(DEST/'manifest.json',report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
