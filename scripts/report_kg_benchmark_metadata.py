"""Read-only metadata proposals and provenance audit; never certify a final pool."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import html
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,budget_snapshot
from framework.knowledge_graph.benchmark_rebuild import sha256_file,standard_family
from framework.knowledge_graph.benchmark_metadata_routing import route_metadata

DEST=OUT/'execution/metadata-audit'


def identifier_candidates(kind, sections):
    # Never join nonadjacent sections to invent a source identifier.
    pattern=(r'10\.\d{4,9}/[^\s<>"{}|\x00-\x1f]+' if kind=='doi' else
             r'(?i)\b(?:GB|NY|HJ|LY|SY|QX|LS|DB\s*\d{2,4}|TD|DZ|SL|CJ|JC|JT|NB|DL)\s*[/／]?\s*T?\s*\d{1,6}(?:\.\d+)*\s*[-—–]\s*(?:19|20)\d{2}')
    if kind not in ['doi','standard_number']:return []
    values=defaultdict(list)
    runs=[]
    for section in sorted(sections,key=lambda s:(s['page'],s['start'],s['end'])):
        if runs and runs[-1][-1]['page']==section['page'] and runs[-1][-1]['end']==section['start']:
            runs[-1].append(section)
        else:runs.append([section])
    for run in runs:
        text=''.join(s['text'] for s in run)
        # Width folding is a bibliographic identifier canonicalization only.
        # One-to-one characters preserve literal source offsets and raw quotes.
        view=''.join(chr(ord(c)-0xfee0) if 0xff01<=ord(c)<=0xff5e else c for c in text)
        for match in re.finditer(pattern,view):
            literal=match.group().rstrip('.,;:)')
            value=literal.casefold() if kind=='doi' else re.sub(r'\s+','',literal).replace('—','-').replace('–','-').replace('／','/')
            values[value].append(dict(section_id=run[0]['id'],section_ids=[s['id'] for s in run],page=run[0]['page'],quote=text[match.start():match.start()+len(literal)],
                start=run[0]['start']+match.start(),end=run[0]['start']+match.start()+len(literal)))
    return [dict(value=k,evidence=v) for k,v in sorted(values.items())]


def audit_proposal(packet, result, document):
    protocol=result.get('protocol',{});metadata=protocol.get('metadata',{})
    sections={s['id']:s for s in packet['sections']};flags=[]
    evidence=protocol.get('source_evidence',{})
    if result['state']!='protocol_valid':flags.append('model_or_protocol_failure')
    if metadata.get('file_sha256')!=packet['file_sha256']:flags.append('file_hash_not_bound')
    if metadata.get('identity_status')!='verified':flags.append('identity_requires_review')
    if metadata.get('source_kind') in [None,'unknown']:flags.append('source_kind_unresolved')
    elif metadata['source_kind']!=document['document_kind']:flags.append('source_kind_conflict')
    if metadata.get('language')=='unknown':flags.append('sampled_language_unknown')
    if metadata.get('body_profile')=='unknown':flags.append('sampled_quality_unknown')
    for field in ['title_ids','identifier_ids','language_ids','body_quality_ids']:
        selected=evidence.get(field,[])
        if metadata.get(field,[])!=[s.get('id') for s in selected]:flags.append('evidence_id_mismatch:'+field)
        for s in selected:
            if s!=sections.get(s.get('id')):flags.append('source_section_mismatch:'+field)
            if field in ['title_ids','identifier_ids'] and s.get('kind')!='pdf_page_text':flags.append('identity_not_pdf_evidence')
            if field=='body_quality_ids' and s.get('kind')!='stored_chunk_excerpt':flags.append('quality_not_body_evidence')
    candidates=identifier_candidates(metadata.get('identifier_kind'),evidence.get('identifier_ids',[]))
    if metadata.get('identifier_kind') in ['doi','standard_number'] and len(candidates)!=1:
        flags.append('identifier_ambiguous_or_not_literal')
    # Every model finding remains a proposal even if formatting/provenance pass.
    return dict(document_id=packet['document_id'],file_sha256=packet['file_sha256'],
        database_source_kind=document['document_kind'],model_state=result['state'],
        metadata=metadata,metadata_routing=route_metadata(packet,metadata),source_evidence=evidence,identifier_candidates=candidates,
        audit_flags=sorted(set(flags)),final_eligible=False,expert_certified=False,
        same_model_error_correlation=True,source_text_provenance_verified=not any(
            f.startswith(('file_hash','evidence_id','source_section','identity_not_pdf','quality_not_body')) for f in flags))


def main():
    packets=readlines(OUT/'metadata-review-preparation/source-packets.jsonl')
    pool={d['id']:d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl')}
    results={};duplicates=[];active=[]
    for name in ['source-metadata-review-v1','source-metadata-review-v2','source-metadata-review-v3','source-metadata-review-v4-pilot','source-metadata-review-v5']:
        folder=OUT/'execution'/name
        for p in (folder/'proposals').glob('*.json'):
            r=json.loads(p.read_text(encoding='utf-8'));i=int(r['id'].split(':')[1])
            if i in results:duplicates.append(i)
            results[i]=(r,p)
        state=folder/'run-state.json'
        if not state.exists():state=folder/'progress.json'
        if state.exists() and json.loads(state.read_text(encoding='utf-8')).get('runner_active'):active.append(name)
    rows=[]
    for packet in packets:
        i=packet['document_id']
        if i not in results:continue
        r,p=results[i];row=audit_proposal(packet,r,pool[i])
        row.update(proposal_path=p.relative_to(ROOT).as_posix(),proposal_sha256=sha256_file(p))
        rows.append(row)
    lines(DEST/'items.jsonl',rows)
    report=dict(status='inconclusive',generated_at=datetime.now(timezone.utc).isoformat(),
        intended_documents=len(packets),saved_documents=len(rows),pending_documents=len(packets)-len(rows),
        duplicate_document_attempt_records=duplicates,active_runs=active,
        model_states=dict(Counter(r['model_state'] for r in rows)),
        identity_statuses=dict(Counter(r['metadata'].get('identity_status','unresolved') for r in rows)),
        model_source_kinds=dict(Counter(r['metadata'].get('source_kind','unresolved') for r in rows)),
        audit_flags=dict(Counter(f for r in rows for f in r['audit_flags'])),
        no_final_qualification_assigned=True,automatic_quality_filtering=False,
        profile_scope='first_two_pdf_page_windows_and_three_stored_chunk_prefixes',
        full_document_quality_certified=False,expert_certified=False,shared_budget=budget_snapshot())
    dump(DEST/'report.json',report)
    esc=lambda v:html.escape(str(v),quote=True)
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>来源元数据核查</title><style>body{font:15px system-ui;margin:28px;max-width:1300px}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{border-top:1px solid #ccc;padding:12px}summary{cursor:pointer}</style><h1>来源元数据核查</h1><p>此页展示生成时快照。模型判断均为待审提议；类型冲突、身份未知和调用失败均保留，不据此挑选容易样本。窗口语言和质量不认证全文；暂不授予最终验收资格。</p><pre>'+esc(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>'
    for r in rows:
        page+='<details><summary>'+esc(str(r['document_id'])+' | '+str(r['metadata'].get('verified_title_source_text','未知标题'))+' | '+', '.join(r['audit_flags']))+'</summary><pre>'+esc(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>'
    (DEST/'review.html').write_text(page+'</html>',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
