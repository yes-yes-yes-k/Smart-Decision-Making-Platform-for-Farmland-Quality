"""Source-scoped QA generation/review job packets; drafts never become references by default."""
import argparse,asyncio,json,sys
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_kg_acceptance_v1 import OUT,verify_freeze,shared_budget_path
from scripts.experiment_kg_recall import read,write,jsonl
from framework.knowledge_graph.acceptance_data import digest,validate_qa
from framework.knowledge_graph.acceptance_budget import Budget
from framework.knowledge_graph.acceptance_remote import run_jobs
from framework.knowledge_graph.annotation_protocol_r4 import response_schema,object_schema
from framework.knowledge_graph.silver_adjudication import literal_fragment
from framework.knowledge_graph.evaluation_v4 import digest as text_digest

def schema():
    ev=object_schema(dict(sample_id=dict(type='string'),text=dict(type='string'),occurrence=dict(type='integer',minimum=0)))
    return response_schema('qa_reference_draft',dict(question=dict(type='string'),answerability=dict(type='string',enum=['answerable','insufficient','false_premise','beyond_evidence']),
        answer_points=dict(type='array',items=dict(type='string')),rationale=dict(type='string'),evidence=dict(type='array',items=ev),
        applicability=dict(type='string'),forbidden_inferences=dict(type='array',items=dict(type='string')),missing_or_invalid_premise=dict(type='string'),multihop=dict(type='boolean')))

def prepare():
    verify_freeze();rows=read(OUT/'pool/selection.jsonl');directory=OUT/'qa';directory.mkdir(exist_ok=True)
    jobs=[]
    for part,multiple in [('calibration',1),('test',4)]:
        bygroup=defaultdict(list)
        for r in rows:
            if r['partition']==part:bygroup[r['isolation_group']].append(r)
        ordered=sorted(bygroup,key=lambda g:digest('qa:'+str(g)))
        specs=[('answerable',False)]*(8*multiple)+[('answerable',True)]*(4*multiple)+[('insufficient',False)]*(4*multiple)+[('false_premise',False)]*(2*multiple)+[('beyond_evidence',False)]*(2*multiple)
        for i,(kind,multi) in enumerate(specs):
            candidates=[g for g in ordered if not multi or len(bygroup[g])>=2]
            if not candidates:raise ValueError('insufficient_multiblock_sources')
            group=candidates[i%len(candidates)];cs=sorted(bygroup[group],key=lambda r:digest(f"qa:{i}:{r['sample_id']}"))[:3]
            source=[dict(sample_id=c['sample_id'],document_title=c['document_title'],text=c['text']) for c in cs]
            prompt=f'仅依据所给原文设计一道自然语言验收问题，类型必须为{kind}，multihop必须为{multi}。答案写要点，不照抄整段。多跳题必须组合至少两块信息才可回答，不能只是拼接两个无关小问题。所有事实及依据必须有逐字原文片段。不可回答题须在问题中写清“仅依据指定文段”的证据边界，并说明缺少的条件或证据；不能用图谱无边、缺关键词或常识判不存在。false_premise须有原文支持的纠错依据。不得声称整篇文献或全库都无答案。提供适用条件和禁止推断。不要输出原文以外的外部知识。\n指定文段：'+json.dumps(source,ensure_ascii=False)
            jobs.append(dict(id=f'qa:{part}:{i:03}',phase='qa_reference',partition=part,kind=kind,multihop=multi,
                source_ids=[c['sample_id'] for c in cs],prompt=prompt,format=schema(),max_tokens=2048))
    path=directory/'generation-jobs.jsonl'
    if path.exists() and read(path)!=jobs:raise ValueError('qa_generation_packet_changed')
    if not path.exists():jsonl(path,jobs)
    write(directory/'packet-status.json',dict(planned_questions=100,calibration=20,test=80,planned_answerable=60,planned_multihop=20,planned_unanswerable=40,
        actual_validated_questions=0,status='prepared_not_generated',reference_frozen=False,
        insufficient_evidence_scope='explicitly bounded to specified source excerpts; not a claim of absence from entire corpus'))
    print('Prepared 100 source-bound QA generation jobs (not 100 validated questions)',flush=True)

async def generate():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env');verify_freeze();jobs=read(OUT/'qa/generation-jobs.jsonl');blocks={r['sample_id']:r for r in read(OUT/'pool/selection.jsonl')};groups={r['isolation_group']:r['partition'] for r in blocks.values()}
    def validate(job,a):
        if a['answerability']!=job['kind'] or a['multihop']!=job['multihop']:raise ValueError('qa_quota_or_kind_changed')
        if a['answerability']!='answerable' and '仅依据' not in a['question']:raise ValueError('unanswerability_needs_explicit_scope')
        evidence=[]
        for e in a['evidence']:
            if e['sample_id'] not in job['source_ids']:raise ValueError('qa_cites_unprovided_source')
            c=blocks[e['sample_id']];v=dict(sample_id=c['sample_id'],blocks=[dict(block_id='chunk',kind='chunk',text=c['text'],text_sha256=text_digest(c['text']))])
            f,audit=literal_fragment(v,'chunk',e['text'],e['occurrence']);evidence.append(dict(sample_id=c['sample_id'],text=f['text'],span_start=audit['span_start'],span_end=audit['span_end']))
        item=dict(a,id=job['id'],partition=job['partition'],evidence=evidence,source_scope_ids=job['source_ids'])
        return validate_qa(item,blocks,groups)
    result=await run_jobs(jobs,OUT/'qa/drafts',json.loads((OUT/'run-config.json').read_text(encoding='utf-8')),Budget(shared_budget_path()),validate)
    write(OUT/'qa/generation-run-state.json',result)

def review_jobs():
    jobs=[];drafts=[]
    blocks={r['sample_id']:r for r in read(OUT/'pool/selection.jsonl')}
    for p in sorted((OUT/'qa/drafts').glob('*.json')):
        r=json.loads(p.read_text(encoding='utf-8'))
        if r['state']!='completed':continue
        q=r['validated'];drafts.append(q)
        source=[dict(sample_id=sid,text=blocks[sid]['text']) for sid in q['source_scope_ids']]
        fmt=response_schema('qa_independent_review',dict(answerability_supported=dict(type='boolean'),answer_points_supported=dict(type='boolean'),evidence_sufficient=dict(type='boolean'),multihop_required=dict(type='boolean'),question_clear=dict(type='boolean'),reason=dict(type='string')))
        prompt='独立核验题目及答案，候选均可能错误。检查可答性、每个答案要点、引用证据、适用条件、禁止推断及题目是否清楚。若声明多跳，必须组合至少两个文段才能回答，不能只是两个问题拼接。不可答题只限明确指定文段，不得以图谱没有边推断；错误前提必须有原文纠错依据。无答案要点时answer_points_supported表示无错误断言。不要修改候选，不满足则明确false。\n原文：'+json.dumps(source,ensure_ascii=False)+'\n候选：'+json.dumps(q,ensure_ascii=False)
        jobs.append(dict(id='review:'+q['id'],phase='qa_reference_review',source_ids=q['source_scope_ids'],multihop=q['multihop'],prompt=prompt,format=fmt,max_tokens=1024))
    jsonl(OUT/'qa/review-jobs.jsonl',jobs);return jobs,drafts

async def review():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env');verify_freeze();jobs,drafts=review_jobs()
    def validate(job,answer):
        keys=('answerability_supported','answer_points_supported','evidence_sufficient','multihop_required','question_clear')
        if any(type(answer.get(k)) is not bool for k in keys) or not answer.get('reason'):raise ValueError('invalid_qa_review')
        return dict(answer,accepted=all(answer[k] for k in keys if k!='multihop_required') and (not job['multihop'] or answer['multihop_required']))
    result=await run_jobs(jobs,OUT/'qa/reviews',json.loads((OUT/'run-config.json').read_text(encoding='utf-8')),Budget(shared_budget_path()),validate)
    approved=[]
    for q in drafts:
        p=OUT/'qa/reviews'/(digest('review:'+q['id'])+'.json')
        if p.exists():
            r=json.loads(p.read_text(encoding='utf-8'))
            if r['state']=='completed' and r['validated']['accepted']:approved.append(q)
    jsonl(OUT/'qa/reference-proposals.jsonl',approved)
    write(OUT/'qa/reference-status.json',dict(status='pass' if len(approved)==100 else 'inconclusive',validated_questions=len(approved),target=100,
        partition_counts=Counter(q['partition'] for q in approved),answerability_counts=Counter(q['answerability'] for q in approved),
        multihop=sum(q['multihop'] for q in approved),reference_frozen=False,same_model_judge_bias=True,run=result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','generate','review']);a=p.parse_args()
    prepare() if a.command=='prepare' else asyncio.run(generate() if a.command=='generate' else review())
