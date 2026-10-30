"""Apply explicitly source-reviewed identity edges, preserve original audit."""
from collections import Counter
from pathlib import Path
import html
import json
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from framework.knowledge_graph.acceptance_data import Groups

DEST=OUT/'execution/source-review-r1'


def literal_evidence(i,pattern):
    record=json.loads((DEST/f'{i}.json').read_text(encoding='utf-8'))
    for p in record['first_pages']:
        match=re.search(pattern,p['text'])
        if match:
            return dict(document_id=i,file_sha256=record['file_sha256'],page=p['page'],
                quote=match.group(),start=match.start(),end=match.end(),
                extraction_file=(DEST/f'{i}.json').relative_to(ROOT).as_posix())
    raise ValueError('identity_proof_not_in_source:'+str(i))


def main():
    original=readlines(OUT/'audit/document-pool.jsonl')
    pool={d['id']:d for d in original}
    pairs=[(208,460,'same_paper_doi',r'10\.1038/s41467-026-76609-x',r'10\.1038/s41467-026-76609-x'),
           (421,1136,'same_paper_doi',r'10\.1016/j\.envint\.2021\.106749',r'10\.1016/j\.envint\.2021\.106749'),
           (474,657,'same_standard_different_publication_copy',r'HJ\s*649-2013',r'HJ\s*649—2013'),
           (476,659,'same_standard_different_publication_copy',r'HJ\s*889-2017',r'HJ\s*889—2017'),
           (478,527,'same_standard_identity',r'4980—2025',r'4980—2025'),
           (933,957,'same_standard_revision_family',r'GB2762—2025',r'GB2762—2022')]
    edges=[]
    for a,b,reason,pa,pb in pairs:
        edges.append(dict(a=a,b=b,decision='merge_isolation_group',reason=reason,
            evidence=[literal_evidence(a,pa),literal_evidence(b,pb)],
            reviewer='Codex_AI_source_review',expert_certified=False))
    image=DEST/'699-page1.png'
    if not image.is_file():raise ValueError('scanned_cover_visual_proof_missing')
    edges.append(dict(a=699,b=963,decision='merge_isolation_group',reason='same_standard_scan_and_text_copy',
        evidence=[dict(document_id=699,file_sha256=pool[699]['file_hash'],page=1,
            visual_read='GB 36600—2018；土壤环境质量 建设用地土壤污染风险管控标准（试行）',
            image_path=image.relative_to(ROOT).as_posix(),image_sha256=sha256_file(image)),
            literal_evidence(963,r'GB36600—2018')],reviewer='Codex_AI_visual_source_review',expert_certified=False))
    # Do not merge arbitrary high-similarity documents or common-titled standards.
    groups=Groups(pool)
    for d in original:groups.union(d['id'],d['isolation_group'])
    for edge in edges:groups.union(edge['a'],edge['b'])
    read_ids={int(p.stem) for p in DEST.glob('*.json') if p.stem.isdigit()}
    exposed={groups.find(d['id']) for d in original if d['exposure_status']=='known_recorded_input_exposure' or d['id'] in read_ids}
    pending=readlines(OUT/'audit/near-duplicate-review.jsonl')
    pending=[r for r in pending if groups.find(r['a'])!=groups.find(r['b'])]
    pending_ids={i for r in pending for i in [r['a'],r['b']]}
    for r in readlines(OUT/'audit/exact-content-review.jsonl')+readlines(OUT/'audit/title-identity-review.jsonl'):
        if len({groups.find(i) for i in r['document_ids']})>1:pending_ids.update(r['document_ids'])
    pending_groups={groups.find(i) for i in pending_ids}
    refined=[]
    for d in original:
        group=groups.find(d['id'])
        refined.append(dict(d,isolation_group=group,
            exposure_status='known_recorded_input_or_source_read_exposure' if group in exposed else d['exposure_status'],
            identity_or_duplicate_candidate_pending=group in pending_groups,
            final_eligible=False,final_blockers=['metadata_protocol_reference_pending']+
                (['known_exposure_propagated_to_identity_group'] if group in exposed else [])+
                (['near_duplicate_or_shared_content_review_pending'] if group in pending_groups else [])))
    lines(DEST/'confirmed-identity-edges.jsonl',edges)
    lines(DEST/'document-pool-refined.jsonl',refined)
    lines(DEST/'near-duplicate-pending.jsonl',pending)
    dump(DEST/'source-read-exposure.json',dict(document_ids=sorted(read_ids),
        purpose='identity_and_source_quality_review',
        conservatively_excluded_from_final_pool=True,expert_certified=False))
    observations=[dict(document_id=575,language='zh',scope='visually_reviewed_cover',
        source_image=(DEST/'575-page1.png').relative_to(ROOT).as_posix(),
        finding='readable_Chinese_cover_but_extracted_text_is_glyph_substitution_noise',
        parse_quality='corrupted_on_reviewed_cover',
        invalidates_old_english_script_language_hint=True),
        dict(document_id=478,finding='filename_acidification_title_differs_from_actual_standard_cover',
        verified_cover_title='土壤主要性状指标分级',scope='cover_identity_only',
        normalization_must_not_use_filename_as_verified_title=True)]
    lines(DEST/'source-quality-observations.jsonl',observations)
    usable=[d for d in refined if d['source_paths'] and d['chunk_status']=='verified' and
            groups.find(d['id']) not in exposed and groups.find(d['id']) not in pending_groups]
    report=dict(status='partial_identity_review_not_final_pool_certification',
        confirmed_identity_edges=len(edges),identity_groups=len({groups.find(i) for i in pool}),
        near_duplicate_pairs_remaining=len(pending),source_read_documents=len(read_ids),
        groups_with_recorded_exposure=len(exposed),pending_content_review_groups=len(pending_groups),
        provisionally_available_documents=len(usable),provisionally_available_groups=len({d['isolation_group'] for d in usable}),
        provisional_kinds=dict(Counter(d['document_kind'] for d in usable)),
        metadata_fully_verified=False,final_eligible_documents=0,
        all_exposure_propagated=True,expert_certified=False,cloud_calls=0)
    dump(DEST/'report.json',report)
    e=lambda x:html.escape(str(x),quote=True)
    content='<!doctype html><html lang="zh"><meta charset="utf-8"><title>来源身份复核</title><style>body{font:15px system-ui;margin:30px;max-width:1200px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>来源身份复核</h1><p>确认边仅用于保守隔离，不等于专家认证或全文语义去重完成；新阅读来源全部登记曝光。</p><pre>'+e(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>'
    for edge in edges:content+='<h2>'+e(str(edge['a'])+' / '+str(edge['b']))+'</h2><pre>'+e(json.dumps(edge,ensure_ascii=False,indent=2))+'</pre>'
    content+='<h2>解析质量观察</h2><pre>'+e(json.dumps(observations,ensure_ascii=False,indent=2))+'</pre></html>'
    (DEST/'review.html').write_text(content,encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
