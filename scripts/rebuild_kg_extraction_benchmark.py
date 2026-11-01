"""Offline rebuild stage 1: immutable source/DB/vector audit, no model imports.

Resume reuses only hash-bound completed document checkpoints from this run.
Use --verify for historical and current artifact integrity without database I/O.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
import html
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.knowledge_graph.benchmark_rebuild import (
    sha256_file, reconcile, identity_components, language_hint,
    draft_representative)
from framework.knowledge_graph.acceptance_inspection import source_flags

OUT = ROOT / 'artifacts/knowledge_platform/extraction-benchmark-v2'
SOURCE = Path(r'D:\17417\Documents\知识库文献')
OLD = ROOT / 'artifacts/knowledge_platform/acceptance-v1'


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tmp.replace(path)


def lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False)+'\n')
    tmp.replace(path)


def readlines(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def budget_snapshot():
    path = OLD / 'budget.sqlite3'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as conn:
        rows = conn.execute('SELECT phase,reserved,charged,state FROM attempts').fetchall()
    phases = {p: sum(c if c is not None else r for pp,r,c,s in rows if pp == p)
              for p,_,_,_ in rows}
    return dict(path=str(path.relative_to(ROOT)), requests=len(rows),
        tokens_charged_or_reserved=sum(phases.values()), by_phase=phases,
        inflight=sum(s == 'inflight' for _,_,_,s in rows), reset=False,
        actual_billed_usage_not_inferred=True)


def freeze_history():
    destination = OUT / 'governance/history-freeze.json'
    if destination.exists():
        verify_history()
        return
    targets = set()
    for directory in [ROOT/'artifacts/minimal_kg',
                      ROOT/'artifacts/knowledge_platform/gold-rebuild-v3',
                      ROOT/'artifacts/knowledge_platform/gold-v4/silver-v1',
                      OLD, ROOT/'artifacts/knowledge_platform/acceptance-v1-v41flash']:
        if directory.is_dir():
            targets.update(p for p in directory.rglob('*')
                           if p.is_file() and p.suffix in {'.json', '.jsonl', '.html', '.md'})
    dump(destination, dict(created_at=datetime.now(UTC).isoformat(),
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p))
               for p in sorted(targets)],
        legacy_status='historical_diagnostic_not_formal_acceptance',
        reason='superseded_reference_boundaries_sampling_and_unresolved_adjudication',
        original_labels_and_scores_preserved=True))
    dump(OUT/'governance/checkpoint.json', dict(
        stage='offline_source_audit', remote_calls_suspended=True,
        original_evaluation_paused=True, automatic_resume=False,
        provider_last_known_status='402_account_balance_insufficient_not_reprobed',
        model='deepseek-ai/DeepSeek-V4.1-Flash', budget=budget_snapshot(),
        new_cloud_calls=0, final_acceptance_status='inconclusive',
        thresholds_confirmed=False))


def verify_history():
    value = json.loads((OUT/'governance/history-freeze.json').read_text(encoding='utf-8'))
    for entry in value['files']:
        if sha256_file(ROOT/entry['path']) != entry['sha256']:
            raise ValueError('historical_file_changed:'+entry['path'])
    return len(value['files'])


def source_inventory():
    path = OUT/'audit/source-files.jsonl'
    if path.exists():
        rows = readlines(path)
        for r in rows:
            p = SOURCE/r['path']
            if not p.is_file() or p.stat().st_size != r['size_bytes'] or sha256_file(p) != r['sha256']:
                raise ValueError('source_snapshot_changed:'+r['path'])
        if {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file()} != {r['path'] for r in rows}:
            raise ValueError('source_directory_membership_changed')
        return rows
    manifest = {r['path'].replace('\\','/'): r for r in
                readlines(SOURCE/'_kb_ingestion_manifest_20261022.jsonl')}
    def one(p):
        stat = p.stat()
        relative = p.relative_to(SOURCE).as_posix()
        h = sha256_file(p)
        after = p.stat()
        if (stat.st_size,stat.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
            raise ValueError('source_changed_during_hash:'+relative)
        hint = manifest.get(relative, {})
        return dict(path=relative,sha256=h,size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,extension=p.suffix.lower(),
            topic_directory=relative.split('/')[0],
            manifest_kind=hint.get('document_kind'),
            manifest_title=hint.get('title'),
            manifest_metadata_verified=False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, sorted(p for p in SOURCE.rglob('*') if p.is_file())))
    lines(path, rows)
    return rows


def database_snapshot():
    path = OUT/'audit/database-documents.jsonl'
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text
    load_dotenv(ROOT/'.env')
    from framework.config import Config
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI,connect_args={'connect_timeout':5})
    try:
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            rows = [dict(r._mapping) for r in conn.execute(text('''SELECT
                id,doc_name,file_path,file_type,file_hash,chunk_count,status,
                visibility_scope,review_status,processing_stage,document_kind,
                title,language,doi_normalized,standard_number_normalized,
                bibliographic_metadata,provenance_metadata,parse_metadata
                FROM kb_document ORDER BY id'''))]
    finally:
        engine.dispose()
    if path.exists() and readlines(path) != rows:
        raise ValueError('database_snapshot_changed_start_new_audit_version')
    if not path.exists():
        lines(path, rows)
    return rows, Config


def historical_exposure():
    """Conservative recorded input exposure; inventory-only files excluded."""
    ids, hashes, evidence = set(), set(), []
    roots = [ROOT/'artifacts/knowledge_platform/gold-v4',
             ROOT/'artifacts/knowledge_platform/gold-rebuild-v3',
             OLD, ROOT/'artifacts/minimal_kg']
    names = ('reference','visible-input','samples','selection','adjudication')
    ignored = ('candidate','corpus-snapshot','diagnostic','review-inspection',
               'evaluation-design','candidate-retention','candidate-v11')
    def walk(x, localids, localhashes):
        if isinstance(x,dict):
            for k,v in x.items():
                if k == 'document_id' and type(v) is int:
                    localids.add(v)
                if k in ('file_sha256','content_sha256') and isinstance(v,str) and len(v)==64:
                    localhashes.add(v)
                if isinstance(v,(dict,list)):
                    walk(v,localids,localhashes)
        elif isinstance(x,list):
            for v in x:
                walk(v,localids,localhashes)
    for directory in roots:
        for p in sorted(directory.rglob('*.jsonl')):
            relative = p.relative_to(ROOT).as_posix()
            if not any(n in p.name for n in names) or any(n in relative for n in ignored):
                continue
            localids, localhashes = set(), set()
            walk(readlines(p),localids,localhashes)
            if localids or localhashes:
                ids.update(localids); hashes.update(localhashes)
                evidence.append(dict(path=relative,sha256=sha256_file(p),
                    document_ids=sorted(localids),file_hashes=sorted(localhashes),
                    interpretation='conservative_recorded_input_exposure_not_proof_of_tuning'))
    return ids,hashes,evidence


def chunk_audit(documents, matches, groups, config):
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    reader = WorkerPublishedChunkReader(config.CHROMA_PERSIST_DIR)
    matched = {r['document_id']:r['source_paths'] for r in matches}
    upload = Path(config.UPLOAD_FOLDER)
    if not upload.is_absolute():
        upload = ROOT/upload
    audits = []
    directory = OUT/'audit/chunks'
    directory.mkdir(parents=True,exist_ok=True)
    for n,d in enumerate(documents):
        checkpoint = directory/f"{d['id']}.json"
        if checkpoint.exists():
            record = json.loads(checkpoint.read_text(encoding='utf-8'))
            if record['file_sha256'] != d['file_hash'] or record['expected_chunks'] != d['chunk_count']:
                raise ValueError('stale_document_checkpoint')
            if record['status']=='verified' and sha256_file(directory/f"{d['id']}.jsonl") != record['chunk_snapshot_sha256']:
                raise ValueError('chunk_checkpoint_bytes_changed')
            audits.append(record)
            continue
        eligible = (d['status']==1 and d['visibility_scope']=='public' and
                    d['review_status']=='approved' and d['processing_stage']=='completed' and
                    bool(d['file_hash']) and (d['chunk_count'] or 0)>0)
        record = dict(document_id=d['id'],isolation_group=groups[d['id']],
            file_sha256=d['file_hash'],expected_chunks=d['chunk_count'],
            public_approved_completed=eligible,source_paths=matched[d['id']],
            source_directory_hash_bound=bool(matched[d['id']]),
            status='not_eligible',reasons=[],diagnostic_flags={},chunks=0)
        if eligible:
            original = Path(d['file_path'])
            candidates = [original] if original.is_absolute() else [ROOT/original,upload/original]
            found = sorted(set(p.resolve() for p in candidates if p.is_file()))
            record['database_original_file_hash_verified'] = bool(found) and all(sha256_file(p)==d['file_hash'] for p in found)
            try:
                rows = reader.read_published_chunks(document_id=d['id'],
                    content_sha256=d['file_hash'],expected_count=d['chunk_count'])
                if len(rows) != d['chunk_count']:
                    raise ValueError('chunk_count_mismatch')
                rows.sort(key=lambda c:c['metadata'].get('chunk_index',-1))
                indices = [r['metadata'].get('chunk_index') for r in rows]
                if indices != list(range(d['chunk_count'])):
                    raise ValueError('chunk_indices_not_contiguous_unique_zero_based')
                frozen, flags = [], Counter()
                for c in rows:
                    m,t = c['metadata'],c['content']
                    if not isinstance(t,str) or type(m.get('page')) is not int or m['page']<=0:
                        raise ValueError('invalid_text_or_page')
                    quality = source_flags(t)
                    flags.update(quality)
                    index=m['chunk_index']
                    text_hash=__import__('hashlib').sha256(t.encode('utf-8')).hexdigest()
                    frozen.append(dict(sample_id=f"rebuild-v2:{d['id']}:{index}:{text_hash[:12]}",
                        document_id=d['id'],isolation_group=groups[d['id']],
                        file_sha256=d['file_hash'],text_sha256=text_hash,text=t,
                        document_title=d['title'] or d['doc_name'],
                        chunk_index=index,page=m['page'],quality_flags=quality,
                        position_quartile=min(3,index*4//d['chunk_count'])))
                lines(directory/f"{d['id']}.jsonl",frozen)
                record.update(status='verified',chunks=len(frozen),
                    chunk_snapshot_sha256=sha256_file(directory/f"{d['id']}.jsonl"),
                    diagnostic_flags=dict(flags),
                    language_hint=language_hint(' '.join(r['text'] for r in frozen[:5])),
                    language_hint_verified=False,parser_version=(d['parse_metadata'] or {}).get('parser_version','unknown'))
            except Exception as exc:
                record.update(status='blocked',reasons=[str(exc) if isinstance(exc,ValueError) else type(exc).__name__])
        dump(checkpoint,record)
        audits.append(record)
        if (n+1)%50==0:
            print(json.dumps(dict(documents_checked=n+1,total=len(documents),
                verified=sum(r['status']=='verified' for r in audits))),flush=True)
    lines(OUT/'audit/chunk-audit.jsonl',audits)
    return audits


def render(report, audit, documents, files):
    byid={d['id']:d for d in documents}
    e=lambda x:html.escape(str(x),quote=True)
    cards=[]
    for a in audit:
        d=byid[a['document_id']]
        links=' '.join(f'<a href="{e((SOURCE/p).as_uri())}">{e(p)}</a>' for p in a['source_paths'])
        cards.append(f"<tr><td>{d['id']}</td><td>{e(d['title'] or d['doc_name'])}</td>"
            f"<td>{e(a['status'])}</td><td>{a['chunks']}/{a['expected_chunks']}</td>"
            f"<td>{e(a.get('language_hint','unknown'))}</td><td>{e(a['diagnostic_flags'])}</td><td>{links}</td></tr>")
    content='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>抽取基准 v2 来源审计</title>
<style>body{font:15px system-ui;margin:30px;color:#243047}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left;vertical-align:top}pre{white-space:pre-wrap}a{overflow-wrap:anywhere}</style>
<h1>抽取基准 v2：来源对账</h1><p>离线审计；旧基准仅供历史诊断。语言与质量线索未经语义确认；尚未形成新参考或正式验收分区。</p>
<p><a href="../protocol/annotation-handbook.md">标注手册草案</a> · <a href="../protocol/pilot-review.html">10条开发来源</a> · <a href="identity-review.html">身份与近重复待核实</a> · <a href="../sampling/draft-report.json">取样草案报告</a> · <a href="report.json">审计报告 JSON</a></p>'''
    content+='<pre>'+e(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>'
    content+='<table><thead><tr><th>ID</th><th>文档</th><th>分块检查</th><th>实读/预期</th><th>语言线索</th><th>质量线索（非排除）</th><th>源文件</th></tr></thead><tbody>'+''.join(cards)+'</tbody></table></html>'
    (OUT/'audit/review.html').write_text(content,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify:
        count=verify_history()
        freeze=json.loads((OUT/'audit/artifact-manifest.json').read_text(encoding='utf-8'))
        for row in freeze['files']:
            if sha256_file(OUT/row['path'])!=row['sha256']:
                raise ValueError('new_artifact_changed:'+row['path'])
        protocol=OUT/'protocol/manifest.json'
        if protocol.exists():
            for row in json.loads(protocol.read_text(encoding='utf-8'))['files']:
                if sha256_file(ROOT/row['path'])!=row['sha256']:
                    raise ValueError('protocol_artifact_changed:'+row['path'])
        before=json.loads((OUT/'governance/checkpoint.json').read_text(encoding='utf-8'))['budget']
        current=budget_snapshot()
        if current!=before:
            authorization=OUT/'execution/remote-authorization.json'
            if not authorization.exists() or json.loads(authorization.read_text(encoding='utf-8')).get('resumed_by')!='user':
                raise ValueError('shared_budget_changed_without_user_resume')
            with sqlite3.connect((OLD/'budget.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as conn:
                prefix=conn.execute('SELECT phase,reserved,charged,state FROM attempts WHERE id<=?',(before['requests'],)).fetchall()
            old_phases={p:sum(c if c is not None else r for pp,r,c,s in prefix if pp==p) for p,_,_,_ in prefix}
            if len(prefix)!=before['requests'] or old_phases!=before['by_phase'] or current['requests']<before['requests']:
                raise ValueError('historical_ledger_prefix_changed_or_reset')
            approval=OUT/'execution/pilot-r1/budget-approval.json'
            limit=1_000_000
            if approval.exists():
                a=json.loads(approval.read_text(encoding='utf-8'))
                if a.get('approved_by')=='user' and a.get('stability_tokens')==2_000_000 and a.get('total_tokens')==10_000_000 and a.get('requests')==5000:
                    limit=2_000_000
            project_auth=OUT/'execution/project-budget-authorization.json'
            allocation=OUT/'execution/phase-allocation.json'
            if project_auth.exists() and allocation.exists():
                a=json.loads(project_auth.read_text(encoding='utf-8'))
                if a.get('approved_by')=='user' and a.get('automatic_phase_reallocation') is True and a.get('total_tokens')==10_000_000 and a.get('requests')==5000:
                    limit=json.loads(allocation.read_text(encoding='utf-8'))['stability']
                    if not (2_000_000<=limit<=10_000_000):raise ValueError('invalid_phase_allocation')
            if current['tokens_charged_or_reserved']>10_000_000 or current['requests']>5000 or current['by_phase'].get('stability',0)>limit:
                raise ValueError('authorized_shared_budget_exceeded')
        print(json.dumps(dict(historical_files_unchanged=count,new_artifacts_verified=len(freeze['files']),
            new_attempts_after_user_resume=current['requests']-before['requests'],
            historical_ledger_prefix_preserved=True)))
        return
    freeze_history()
    files=source_inventory()
    print(json.dumps(dict(source_files=len(files),source_pdfs=sum(r['extension']=='.pdf' for r in files))),flush=True)
    documents,config=database_snapshot()
    matches,unmatched=reconcile(files,documents)
    lines(OUT/'audit/source-to-database.jsonl',matches)
    lines(OUT/'audit/source-files-unmatched.jsonl',unmatched)
    groups,edges=identity_components(documents)
    lines(OUT/'audit/identity-edges.jsonl',edges)
    ids,hashes,evidence=historical_exposure()
    exposed_groups={groups[d['id']] for d in documents if d['id'] in ids or d['file_hash'] in hashes}
    dump(OUT/'audit/exposure-evidence.json',dict(files=evidence,
        scope='recorded_selected_inputs_and_references_only_not_exhaustive',
        unknown_external_exposure=True,certified_unexposed=False))
    audits=chunk_audit(documents,matches,groups,config)
    enriched=[]
    identity_path=OUT/'audit/identity-review-report.json'
    identity_review=json.loads(identity_path.read_text(encoding='utf-8')) if identity_path.exists() else None
    duplicate_pending=set(identity_review['pending_document_ids']) if identity_review else set()
    for d,a in zip(documents,audits):
        enriched.append(dict(d,isolation_group=groups[d['id']],
            exposure_status='known_recorded_input_exposure' if groups[d['id']] in exposed_groups else 'no_exposure_found_in_audited_records',
            certified_unexposed=False,exposure_scope_complete=False,
            parse_quality=(d['parse_metadata'] or {}).get('quality','unknown'),
            source_paths=a['source_paths'],chunk_status=a['status'],
            language_hint=a.get('language_hint','unknown'),
            identity_or_duplicate_candidate_pending=d['id'] in duplicate_pending,
            final_eligible=False,final_blockers=['identity_metadata_and_near_duplicate_review_pending',
                'annotation_protocol_and_reference_not_validated']+
                (['specific_identity_or_content_duplicate_candidate_pending'] if d['id'] in duplicate_pending else [])+
                (['known_recorded_input_exposure'] if groups[d['id']] in exposed_groups else [])+
                ([] if a['source_directory_hash_bound'] else ['source_directory_unmatched'])+
                ([] if a['status']=='verified' else ['chunk_not_verified'])))
    lines(OUT/'audit/document-pool.jsonl',enriched)
    # Sampling is deliberately a diagnostic draft, never a final partition.
    usable=[d for d in enriched if d['chunk_status']=='verified' and d['source_paths'] and groups[d['id']] not in exposed_groups]
    chunks=[]
    for d in usable:
        chunks.extend(readlines(OUT/f"audit/chunks/{d['id']}.jsonl"))
    draft,sampling=draft_representative(usable,chunks,'extraction-benchmark-v2-20261028')
    lines(OUT/'sampling/representative-draft.jsonl',draft)
    dump(OUT/'sampling/draft-report.json',dict(sampling,pool_documents=len(usable),
        challenge_not_selected=True,reason='pending_protocol_and_near_duplicate_review',
        final_dataset_not_frozen=True))
    byhash=Counter(f['sha256'] for f in files if f['extension']=='.pdf')
    report=dict(status='inconclusive',stage='offline_source_audit_completed_not_reference_ready',
        created_at=datetime.now(UTC).isoformat(),source_directory=str(SOURCE),
        source_files=len(files),extensions=dict(Counter(f['extension'] for f in files)),
        pdfs=sum(byhash.values()),unique_pdf_byte_hashes=len(byhash),
        duplicate_pdf_byte_copies=sum(n-1 for n in byhash.values()),
        database_documents=len(documents),database_kinds=dict(Counter(d['document_kind'] for d in documents)),
        database_documents_matched_to_source=sum(bool(r['source_paths']) for r in matches),
        source_matched_document_kinds=dict(Counter(d['document_kind'] for d in enriched if d['source_paths'])),
        database_documents_unmatched=sum(not r['source_paths'] for r in matches),
        source_pdf_files_unmatched=sum(r['extension']=='.pdf' for r in unmatched),
        chunk_status=dict(Counter(a['status'] for a in audits)),
        verified_chunks=sum(a['chunks'] for a in audits),
        database_original_files_verified=sum(a.get('database_original_file_hash_verified',False) for a in audits),
        identity_groups=len(set(groups.values())),identity_edges=len(edges),
        known_exposed_groups=len(exposed_groups),
        draft_pool_documents=len(usable),formal_final_eligible_documents=0,
        language_metadata_known=sum(bool(d['language']) for d in documents),
        doi_metadata_known=sum(bool(d['doi_normalized']) for d in documents),
        standard_number_metadata_known=sum(bool(d['standard_number_normalized']) for d in documents),
        identity_duplicate_review_candidates=identity_review,
        unresolved=['bibliographic_identity_and_revision_verification','semantic_near_duplicate_audit',
            'verified_language_and_parse_quality','pilot_annotation_and_adjudication',
            'new_reference_labels','user_confirmed_thresholds'],
        original_files_modified=False,production_writes=False,cloud_calls=0,
        shared_budget=budget_snapshot(),history_files_unchanged=verify_history())
    dump(OUT/'audit/report.json',report)
    render(report,audits,documents,files)
    targets=[p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json']
    dump(OUT/'audit/artifact-manifest.json',dict(files=[dict(path=p.relative_to(OUT).as_posix(),sha256=sha256_file(p)) for p in sorted(targets)]))
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
