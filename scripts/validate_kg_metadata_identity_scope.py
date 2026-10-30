"""Fresh controls clarify source identity versus bibliography completeness."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.validate_kg_metadata_contract as prior
import scripts.review_kg_benchmark_metadata as original
import scripts.run_kg_benchmark_pilot as engine
from scripts.rebuild_kg_extraction_benchmark import OUT,dump
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/metadata-identity-scope-controls-v1'
CLARIFICATION='''identity_status只回答：当前哈希已绑定的PDF身份窗口中，实际题名能否直接读出。
verified=有可直接读出的当前文献题名并有title_ids证据；不要求作者/期刊/DOI完整，不保证世界范围唯一身份，也不是专家认证。
requires_visual=PDF身份窗口没有题名文本或题名乱码，需要看图；unknown=其他原因无法判断。
不得因正文窗口损坏、缺少作者/DOI或全文未提供而将可读PDF题名判为requires_visual。题名不能靠正文或文件名补写。
source_kind依据可见文档的明确类型判断；未知身份窗口配上普通正文句子，不能证明是论文或标准。
identifier_ids只选当前主编号，不能选“代替”后的旧编号或参考文献DOI。'''


def cases():
    specs=[
        ('title-readable-body-broken','Research article: Moisture buffering under mulch in upland red soil', '�\x00�\x00�',('academic_paper','en','unreadable','verified','not_found_in_windows')),
        ('short-title-no-authors','研究论文：稻田土壤水分响应','试验记录了土壤水分随降水变化的过程。',('academic_paper','zh','readable','verified','not_found_in_windows')),
        ('missing-title-body-readable','', '本次观测记录土壤温度变化。',('unknown','zh','readable','requires_visual','unknown')),
        ('main-number-not-replaced','国家标准\nGB 88888—2026\n土壤监测规范\n代替 GB 88888—2010','本标准规定监测要求。',('standard','zh','readable','verified','standard_number')),
    ]
    rows=[]
    for ident,pdf,body,expected in specs:
        sections=[]
        if pdf:sections.append(dict(id='p0',kind='pdf_page_text',page=1,start=0,end=len(pdf),text=pdf))
        sections.append(dict(id='b0',kind='stored_chunk_excerpt',page=2,start=0,end=len(body),text=body))
        rows.append(dict(id=ident,packet=dict(document_id=ident,file_sha256=engine.digest(sections),sections=sections,profile_scope='synthetic_only'),expected=expected))
    # Separate the main/replaced identifier evidence to make a literal choice possible.
    p=rows[-1]['packet'];text=p['sections'][0]['text'];cut=text.index('代替')
    p['sections']=[dict(id='p0',kind='pdf_page_text',page=1,start=0,end=cut,text=text[:cut]),
        dict(id='p1',kind='pdf_page_text',page=1,start=cut,end=len(text),text=text[cut:]),p['sections'][-1]]
    p['file_sha256']=engine.digest(p['sections'])
    return rows


async def run():
    engine.RUN=RUN
    engine.Budget=lambda path,**ignored:AuthorizedBudget(path,authorization=OUT/'execution/project-budget-authorization.json',allocation=OUT/'execution/phase-allocation.json')
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000)
    engine.validate_proposal=original.check
    jobs=[]
    for c in cases():
        p=c['packet'];fmt=original.schema_for(p)
        jobs.append(dict(id='metadata-scope:'+c['id'],phase='metadata_controls',packet=p,options=dict(
            messages=[dict(role='system',content=original.INSTRUCTION+'\n'+prior.CONTRACT+'\n'+CLARIFICATION+'\nJSON_SCHEMA\n'+json.dumps(fmt['json_schema']['schema'],ensure_ascii=False)),
                dict(role='user',content=json.dumps(dict(sections=p['sections']),ensure_ascii=False))],
            max_tokens=1536,response_format=fmt)))
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',synthetic_only=True,
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=Path(__file__).relative_to(ROOT).as_posix(),sha256=sha256_file(Path(__file__))),
        dict(path=Path(prior.__file__).relative_to(ROOT).as_posix(),sha256=sha256_file(Path(prior.__file__)))])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('scope_control_config_frozen')
    if not path.exists():dump(path,config)
    result=await engine.execute(jobs,config)
    fields=['source_kind','language','body_profile','identity_status','identifier_kind'];rows=[]
    for c,j in zip(cases(),jobs):
        r=json.loads((RUN/'proposals'/(engine.digest(j['id'])+'.json')).read_text(encoding='utf-8'))
        m=r.get('protocol',{}).get('metadata',{});actual=tuple(m.get(k) for k in fields)
        no_replaced=c['id']!='main-number-not-replaced' or m.get('identifier_ids')==['p0']
        rows.append(dict(id=c['id'],expected=dict(zip(fields,c['expected'])),actual=dict(zip(fields,actual)),
            main_identifier_only=no_replaced,exact=r['state']=='protocol_valid' and actual==c['expected'] and no_replaced))
    dump(RUN/'report.json',dict(status='pass' if all(r['exact'] for r in rows) else 'fail',scope='metadata_identity_scope_controls_only',
        cases=rows,budget=result['budget'],expert_certified=False,prior_control_failure_retained=True))
    print(json.dumps(rows,ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
