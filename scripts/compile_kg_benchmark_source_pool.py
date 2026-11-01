"""Compile auditable source eligibility; low parsing quality is never a filter."""
from collections import Counter,defaultdict
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines
from scripts.report_kg_benchmark_metadata import identifier_candidates
from framework.knowledge_graph.benchmark_rebuild import standard_family,sha256_file
from framework.knowledge_graph.acceptance_data import Groups,normalized

DEST=OUT/'execution/source-pool-v2'


def expanded_identifier(packet,metadata):
    selected=set(metadata.get('identifier_ids',[]));sections=packet['sections'];chosen=set()
    for index,s in enumerate(sections):
        if s['id'] in selected:
            for near in sections[max(0,index-2):index+3]:
                if near['kind']=='pdf_page_text' and near['page']==s['page']:chosen.add(near['id'])
    candidates=identifier_candidates(metadata.get('identifier_kind'),[s for s in sections if s['id'] in chosen])
    spans=[s for s in sections if s['id'] in selected]
    return [c for c in candidates if any(e['page']==s['page'] and e['start']<s['end'] and s['start']<e['end']
        for e in c['evidence'] for s in spans)]


def main():
    docs=readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl');byid={d['id']:d for d in docs}
    packets={p['document_id']:p for p in readlines(OUT/'metadata-review-preparation/source-packets.jsonl')}
    audits={r['document_id']:r for r in readlines(OUT/'execution/metadata-audit/items.jsonl')}
    visual={r['document_id']:r for r in readlines(OUT/'execution/cover-visual-review-v1/decisions.jsonl')}
    profiles={}
    for path in (OUT/'execution/source-profile-adjudication-v1/proposals').glob('*.json'):
        r=json.loads(path.read_text(encoding='utf-8'));profiles[int(r['id'].split(':')[1])]=dict(r,path=path.relative_to(ROOT).as_posix(),sha256=sha256_file(path))
    compiled=[]
    for i,p in packets.items():
        audit=audits.get(i,{});m=audit.get('metadata',{});profile=profiles.get(i)
        effective=dict(source_kind='unknown',language=m.get('language','unknown'),body_profile='unknown')
        if profile and profile['state']=='protocol_valid':
            effective={k:profile['protocol']['profile'][k] for k in effective}
        elif any('/'+name+'/proposals/' in audit.get('proposal_path','') for name in ['source-metadata-review-v4-pilot','source-metadata-review-v5']):
            effective={k:m.get(k,'unknown') for k in effective}
        if i in visual:effective['source_kind']=visual[i]['source_kind']
        proof=None;identifier=None;kind=None;blockers=[]
        if i in visual:
            proof=dict(channel='AI_visual_cover',decision=visual[i]);identifier=visual[i]['identifier'];kind=visual[i]['identifier_kind']
        elif m.get('identity_status')=='verified' and m.get('title_ids') and audit.get('source_text_provenance_verified'):
            candidates=expanded_identifier(p,m)
            if len(candidates)==1:
                identifier=candidates[0]['value'];kind=m['identifier_kind'];proof=dict(channel='AI_selected_PDF_text',identifier_evidence=candidates[0])
            elif m.get('identifier_kind') in ['not_found_in_windows','unknown'] and byid[i]['document_kind']=='academic_paper':
                proof=dict(channel='AI_selected_title_only',doi_not_certified=True)
            else:blockers.append('primary_identifier_not_resolved')
        else:blockers.append('source_identity_not_resolved')
        compiled.append(dict(document_id=i,file_sha256=p['file_sha256'],identity_proof=proof,
            identifier=identifier,identifier_kind=kind,profile=effective,
            profile_adjudication_path=profile['path'] if profile else None,
            profile_adjudication_state=profile['state'] if profile else 'not_required_or_not_available',
            metadata_audit_path=audit.get('proposal_path'),topic_source_folders=p['source_topic_directories'],
            profile_scope=p['profile_scope'],blockers=blockers,expert_certified=False))
    groups=Groups(byid)
    for d in docs:groups.union(d['id'],d['isolation_group'])
    index={};edges=[]
    for r in compiled:
        if not r['identifier']:continue
        key=(r['identifier_kind'],r['identifier'].strip().lower() if r['identifier_kind']=='doi' else standard_family(r['identifier']))
        if key in index:
            other=index[key];groups.union(other,r['document_id']);edges.append(dict(a=other,b=r['document_id'],kind=key[0],value=key[1],basis='source_bound_primary_identifiers'))
        else:index[key]=r['document_id']
    # Candidate-only matches to the historical pool cannot certify identity.
    # Quarantine both sides instead of silently treating historical evidence as verified.
    potential=[]
    historical_hints=readlines(OUT/'audit/metadata-review-candidates.jsonl')
    for h in historical_hints:
        for c in h.get('candidates',[]):
            if c['kind'] not in ['doi','standard_number']:continue
            key=(c['kind'],c['value'].strip().lower() if c['kind']=='doi' else standard_family(c['value']))
            other=index.get(key)
            if other is not None and groups.find(other)!=groups.find(h['document_id']):
                potential.append(dict(a=other,b=h['document_id'],kind=key[0],value=key[1],status='unverified_historical_identity_collision_quarantined'))
    exposed={groups.find(d['id']) for d in docs if d['exposure_status'].startswith('known_')}
    pending={groups.find(d['id']) for d in docs if d['identity_or_duplicate_candidate_pending']}
    pending.update(groups.find(r[k]) for r in potential for k in ['a','b'])
    # Title-only references still receive a conservative title-vs-filename collision check.
    for r in compiled:
        m=audits.get(r['document_id'],{}).get('metadata',{});title=normalized(m.get('verified_title_source_text',''))
        if len(title)<25:continue
        for d in docs:
            if groups.find(d['id'])!=groups.find(r['document_id']) and title in normalized(d['doc_name']):
                pending.update([groups.find(d['id']),groups.find(r['document_id'])])
                potential.append(dict(a=r['document_id'],b=d['id'],kind='source_title_in_other_filename',value=title,status='quarantined_not_certified'))
    for r in compiled:
        group=groups.find(r['document_id']);r['isolation_group']=group
        if group in exposed:r['blockers'].append('historical_exposure_in_identity_group')
        if group in pending:r['blockers'].append('identity_or_near_duplicate_pending')
        r['sampling_eligible']=not r['blockers']
        r['exposure_status']=byid[r['document_id']]['exposure_status'];r['certified_unexposed']=False
        r['quality_based_exclusion']=False
    lines(DEST/'documents.jsonl',compiled);lines(DEST/'verified-identity-edges.jsonl',edges);lines(DEST/'quarantined-collisions.jsonl',potential)
    eligible=[r for r in compiled if r['sampling_eligible']]
    report=dict(status='source_pool_compiled_not_final_reference',documents=len(compiled),eligible_documents=len(eligible),
        eligible_groups=len({r['isolation_group'] for r in eligible}),
        blockers=dict(Counter(b for r in compiled for b in r['blockers'])),
        kinds=dict(Counter(r['profile']['source_kind'] for r in eligible)),
        qualities=dict(Counter(r['profile']['body_profile'] for r in eligible)),
        identity_edges=len(edges),quarantined_collision_records=len(potential),
        unknown_profile_fields_retained_as_sampling_strata=True,quality_filter_used=False,
        exposure_claim='no_exposure_found_in_audited_local_records_not_certified_training_blind',expert_certified=False)
    dump(DEST/'report.json',report);print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
