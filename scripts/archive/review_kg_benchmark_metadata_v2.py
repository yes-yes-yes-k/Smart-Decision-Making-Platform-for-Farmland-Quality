"""Same metadata evidence, short section IDs; provenance remains local and exact."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.review_kg_benchmark_metadata as first
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,readlines
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/source-metadata-review-v2'


def schema():
    def enum(v):return dict(type='string',enum=v)
    ids=dict(type='array',items=dict(type='string',pattern=r'^s(0|[1-9][0-9]*)$'))
    props=dict(identity_status=enum(['verified','requires_visual','unknown']),source_kind=enum(['academic_paper','standard','method_guideline','other','unknown']),
        title_ids=ids,identifier_kind=enum(['doi','standard_number','not_found_in_windows','unknown']),identifier_ids=ids,
        identity_reason=dict(type='string'),language=enum(['zh','en','mixed','unknown']),language_ids=ids,language_reason=dict(type='string'),
        body_profile=enum(['readable','partial','unreadable','unknown']),body_quality_ids=ids,quality_reason=dict(type='string'))
    return dict(type='json_schema',json_schema=dict(name='metadata_short_source_ids',strict=True,
        schema=dict(type='object',properties=props,required=list(props),additionalProperties=False)))


def check(packet,raw,unused):
    mapped=dict(raw)
    mapping=packet['short_id_mapping']
    for key in ['title_ids','identifier_ids','language_ids','body_quality_ids']:
        if any(i not in mapping for i in raw[key]):raise ValueError('unknown_short_evidence_id')
        mapped[key]=[mapping[i] for i in raw[key]]
    sections={s['id']:s for s in packet['sections']}
    if any(sections[i]['kind']!='pdf_page_text' for i in mapped['title_ids']+mapped['identifier_ids']):raise ValueError('identity_requires_pdf_evidence')
    if any(sections[i]['kind']!='stored_chunk_excerpt' for i in mapped['body_quality_ids']):raise ValueError('profile_requires_stored_chunks')
    return dict(first.check(packet,mapped,unused),transport='short_section_ids_provenance_local_no_text_removed')


async def run(limit):
    engine.RUN=RUN
    auth=OUT/'execution/project-budget-authorization.json';allocation=OUT/'execution/phase-allocation.json'
    engine.Budget=lambda path,**ignored:AuthorizedBudget(path,authorization=auth,allocation=allocation)
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000)
    complete={}
    for p in (first.RUN/'proposals').glob('*.json'):
        row=json.loads(p.read_text(encoding='utf-8'))
        if row['state']=='protocol_valid':complete[int(row['id'].split(':')[1])]=sha256_file(p)
    packets=[p for p in readlines(OUT/'metadata-review-preparation/source-packets.jsonl') if p['document_id'] not in complete]
    pool={d['id']:d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl')}
    if not all(current_qualification([pool[p['document_id']] for p in packets]).values()):raise ValueError('source_qualification_changed')
    jobs=[]
    for p in packets:
        mapping={'s'+str(i):s['id'] for i,s in enumerate(p['sections'])}
        visible=[dict(id='s'+str(i),kind=s['kind'],page=s['page'],text=s['text']) for i,s in enumerate(p['sections'])]
        packet=dict(p,short_id_mapping=mapping)
        source=dict(document_id=p['document_id'],filename_hint=p['filename_hint'],filename_is_unverified_hint=True,sections=visible,profile_scope=p['profile_scope'])
        jobs.append(dict(id='metadata-v2:'+str(p['document_id']),phase='source_metadata',packet=packet,
            options=dict(messages=[dict(role='system',content=first.INSTRUCTION+'\n证据编号使用显示的s0/s1等，不生成新编号。'),
                dict(role='user',content=json.dumps(source,ensure_ascii=False))],max_tokens=1536,response_format=schema())))
    paths=[Path(__file__),ROOT/'scripts/review_kg_benchmark_metadata.py',OUT/'metadata-review-preparation/manifest.json']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        task='metadata_only_all_source_text_preserved',previous_completed_responses_retained=complete,
        source_document_count=len(jobs),global_token_limit=10000000,global_request_limit=5000,concurrency=2,
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in paths])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('metadata_v2_config_frozen')
    if not path.exists():dump(path,config)
    engine.validate_proposal=check
    print(json.dumps(await engine.execute(jobs if limit is None else jobs[:limit],config)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);a=parser.parse_args()
    if a.limit is not None and a.limit<=0:raise ValueError('positive_limit_required')
    asyncio.run(run(a.limit))
