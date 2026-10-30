"""Fresh synthetic metadata controls; no corpus relabeling or semantic retry."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.review_kg_benchmark_metadata as original
from scripts.rebuild_kg_extraction_benchmark import OUT,dump
from framework.knowledge_graph.benchmark_budget_policy import AuthorizedBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/metadata-contract-controls-v1'
CONTRACT='''字段判定规则（必须按来源内容，文件名不是证据）：
source_kind: academic_paper=报告研究方法/结果的学术论文；standard=明确带标准编号及标准规范的文件；method_guideline=没有正式标准编号的操作指南；other=其他可识别文档；unknown=身份窗口不足以分类。不能把论文一律设unknown或standard。
body_profile仅评价提供的stored_chunk_excerpt：readable=文字可理解且无明显乱码/损坏；partial=部分文字可理解但有明确乱码或断字损坏；unreadable=全为乱码无法理解；unknown=没有正文窗口或材料不足以判定。正常截断的段落前缀不等于损坏；不能仅因窗口不是全文就选unknown。
language: zh=所见可理解文本为中文；en=英文；mixed=同时有中英文文本；unknown=没有可理解语言证据。
identity_status: verified=有实际PDF题名且可识别身份；requires_visual=PDF文本缺失/乱码需看图；unknown=其他无法确定。
identifier_kind: doi=当前论文DOI；standard_number=当前标准主编号；not_found_in_windows=可读身份窗口中未找到；unknown=身份窗口不可靠。不要引用被代替旧版本或参考文献编号。
输出字段和枚举见下方JSON Schema；每项理由应与选择相符。'''


def cases():
    data=[
        ('paper-en','Research paper: Soil carbon under compost\nMethods and results\nDOI: 10.1234/soil.2026','Compost increased soil carbon in a field experiment.',('academic_paper','en','readable','verified','doi')),
        ('paper-zh','研究论文：堆肥对土壤有机碳的影响\n研究方法与结果','本研究测定了堆肥施用后土壤有机碳的变化。',('academic_paper','zh','readable','verified','not_found_in_windows')),
        ('standard','中华人民共和国国家标准\nGB 99999—2026\n土壤检测规范','本标准规定土壤样品检测的技术要求。',('standard','zh','readable','verified','standard_number')),
        ('guide','土壤采样操作指南\n实验室内部操作文件，不是国家或行业标准','按照本指南在田间采集土壤样品并记录位置。',('method_guideline','zh','readable','verified','not_found_in_windows')),
        ('memo','Office meeting memorandum\nDiscussion of the stationery budget','The office will purchase pens next month.',('other','en','readable','verified','not_found_in_windows')),
        ('scan','','�\x00�\x00�',('unknown','unknown','unreadable','requires_visual','unknown')),
        ('partial','Research article: Soil nitrogen\nMaterials and methods','Soil nitrogen was measured. �\x00�\x00� [text layer damaged]',('academic_paper','en','partial','verified','not_found_in_windows')),
        ('misleading-name','中华人民共和国行业标准\nNY/T 99998—2026\n土壤检测技术规范','本标准适用于土壤检测工作。',('standard','zh','readable','verified','standard_number')),
    ]
    rows=[]
    for name,pdf,body,expected in data:
        sections=[]
        if pdf:sections.append(dict(id='p0',kind='pdf_page_text',page=1,start=0,end=len(pdf),text=pdf))
        sections.append(dict(id='b0',kind='stored_chunk_excerpt',page=2,start=0,end=len(body),text=body))
        rows.append(dict(id=name,packet=dict(document_id=name,file_sha256=engine.digest(sections),
            sections=sections,profile_scope='synthetic_control_only'),expected=expected))
    return rows


async def run():
    engine.RUN=RUN
    engine.Budget=lambda path,**ignored:AuthorizedBudget(path,authorization=OUT/'execution/project-budget-authorization.json',allocation=OUT/'execution/phase-allocation.json')
    engine.limits=lambda:dict(stability=2200000,total=10000000,requests=5000)
    engine.validate_proposal=original.check
    jobs=[]
    for c in cases():
        p=c['packet'];schema=original.schema_for(p)
        source=dict(sections=p['sections'],filename_hint='research-paper.pdf' if c['id']=='misleading-name' else 'synthetic.pdf',filename_is_unverified_hint=True)
        jobs.append(dict(id='metadata-control:'+c['id'],phase='metadata_controls',packet=p,
            options=dict(messages=[dict(role='system',content=original.INSTRUCTION+'\n'+CONTRACT+'\nJSON_SCHEMA\n'+json.dumps(schema['json_schema']['schema'],ensure_ascii=False)),
                dict(role='user',content=json.dumps(source,ensure_ascii=False))],max_tokens=1536,response_format=schema)))
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        synthetic_only=True,semantic_retries=0,corpus_reannotation=False,jobs={j['id']:engine.digest(j) for j in jobs},
        files=[dict(path=Path(__file__).relative_to(ROOT).as_posix(),sha256=sha256_file(Path(__file__)))])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('control_config_frozen')
    if not path.exists():dump(path,config)
    result=await engine.execute(jobs,config)
    fields=['source_kind','language','body_profile','identity_status','identifier_kind'];out=[]
    for c,j in zip(cases(),jobs):
        r=json.loads((RUN/'proposals'/(engine.digest(j['id'])+'.json')).read_text(encoding='utf-8'))
        m=r.get('protocol',{}).get('metadata',{});actual=tuple(m.get(k) for k in fields)
        out.append(dict(id=c['id'],state=r['state'],expected=dict(zip(fields,c['expected'])),actual=dict(zip(fields,actual)),
            exact=r['state']=='protocol_valid' and actual==c['expected']))
    dump(RUN/'report.json',dict(status='pass' if all(r['exact'] for r in out) else 'fail',
        scope='synthetic_metadata_field_contract_only',cases=out,budget=result['budget'],expert_certified=False,
        bulk_corpus_resume_authorized_by_this_test=False))
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
