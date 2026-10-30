"""Assemble every frozen sample into a reviewable, explicitly provisional set."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def facts(annotation):
    entities={(r['type'],r['name'].casefold()) for r in annotation.get('entities',[])}
    relations={(r['source'].casefold(),r['relation_type'],r['target'].casefold()) for r in annotation.get('relationships',[])}
    return entities,relations


def assemble(samples,first,second):
    from framework.knowledge_graph.schema import load_graph_schema
    from scripts.annotate_kg_gold_corpus import validate_annotation
    schema=load_graph_schema()
    rows=[]
    for source in samples:
        if source.get('text_sha256') and hashlib.sha256(source['text'].encode()).hexdigest()!=source['text_sha256']:
            raise ValueError('source snapshot checksum mismatch')
        sid=source['sample_id'];a=first.get(sid);b=second.get(sid)
        reasons=[]
        if not a or not b:
            reasons.append('missing_annotation_or_review')
        if a and b and facts(a)!=facts(b):
            reasons.append('two_pass_label_disagreement')
        proposal=b or a or dict(entities=[],relationships=[],validation_errors=['unannotated'])
        if proposal.get('validation_errors'):
            reasons.append('invalid_or_dropped_candidate_labels')
        # Rebind the final proposal to the frozen source, not to a model claim.
        clean=validate_annotation(source,dict(entities=proposal.get('entities',[]),relationships=[
            {k:r[k] for k in ('source','target','relation_type','quote')} for r in proposal.get('relationships',[])]),schema)
        if clean['validation_errors']:
            reasons.append('final_source_validation_failed')
        if clean.get('disposition')=='no_schema_facts':
            reasons.append('no_fact_decision_requires_adjudication')
        rows.append(dict(schema='kg-corpus-reference-v3',sample_id=sid,source=source,
            proposal_sha256=hashlib.sha256(json.dumps(clean,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            first_pass=a,second_pass=b,proposal=clean,review_reasons=reasons,
            review_priority=(100 if 'final_source_validation_failed' in reasons or 'missing_annotation_or_review' in reasons else
                90 if 'invalid_or_dropped_candidate_labels' in reasons else 80 if 'two_pass_label_disagreement' in reasons else
                40 if 'no_fact_decision_requires_adjudication' in reasons else 20),
            review_status='needs_adjudication',independent_human_review=False,gold_approved=False))
    return rows


def render_review(rows,path):
    payload=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
    html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>金标 v3 原文复核</title>
<style>body{font:16px system-ui;margin:24px;background:#f5f6f8;color:#172333}header,section{background:white;padding:18px;margin:12px 0;border-radius:9px}button,input,select{padding:9px;margin:4px}pre{white-space:pre-wrap;line-height:1.7;max-height:55vh;overflow:auto}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.fact{padding:10px;border-bottom:1px solid #ddd}blockquote{white-space:pre-wrap;color:#526071}#note{color:#91400b}@media(max-width:900px){.grid{display:block}}</style>
<header><h1>金标 v3 原文复核</h1><p>1000 个来源样本；模型预标注与复核均不等于正式金标。请核对原文、遗漏和无事实判断。所有决定仅保存在本浏览器，导出后才能交回项目。</p>
<input id="actor" placeholder="复核人姓名或标识"><select id="split"><option value="">全部集合</option><option>development</option><option>validation</option><option>test</option></select><select id="filter"><option value="all">全部样本</option><option value="pending">未处理</option><option value="disagree">两轮标签分歧</option><option value="errors">校验问题</option></select><button id="export">导出复核决定</button><p id="status"></p></header>
<section><button id="prev">上一条</button><button id="next">下一条</button><span id="number"></span><h2 id="title"></h2><p id="meta"></p><p id="note"></p><div class="grid"><div><h3>原始分块</h3><pre id="source"></pre></div><div><h3>复核稿标签</h3><div id="labels"></div><details><summary>第一轮标签</summary><pre id="first"></pre></details></div></div><input id="comment" placeholder="复核意见"><button id="accept">接受复核稿</button><button id="reject">退回修订</button></section>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent), key='kg-gold-v3-'+data[0].source.text_sha256;
let decisions=JSON.parse(localStorage.getItem(key)||'{}'),index=0,visible=[];const el=id=>document.getElementById(id);
function refresh(){visible=data.filter(r=>(!el('split').value||r.source.split===el('split').value)&&(el('filter').value!=='pending'||!decisions[r.sample_id])&&(el('filter').value!=='disagree'||r.review_reasons.includes('two_pass_label_disagreement'))&&(el('filter').value!=='errors'||r.review_priority>=90));index=Math.min(index,Math.max(0,visible.length-1));show()}
function show(){el('status').textContent=`已处理 ${Object.keys(decisions).length} / ${data.length}，正式金标仍需导入校验`;if(!visible.length){el('title').textContent='当前筛选无样本';el('accept').disabled=true;el('reject').disabled=true;return}const r=visible[index],s=r.source;el('number').textContent=`${index+1} / ${visible.length}`;el('title').textContent=s.document_title;el('meta').textContent=`${s.split} · 文档 ${s.document_id} · 页 ${s.page} · 分块 ${s.chunk_index} · ${r.sample_id}`;el('source').textContent=s.text;el('note').textContent=r.review_reasons.join('；');el('labels').replaceChildren();let p=document.createElement('p');p.textContent=r.proposal.entities.map(e=>`${e.name} (${e.type})`).join('；')||'无实体';el('labels').append(p);for(const f of r.proposal.relationships){let d=document.createElement('div');d.className='fact';d.textContent=`${f.source} → ${f.relation_type} → ${f.target}`;let q=document.createElement('blockquote');q.textContent=f.quote;d.append(q);el('labels').append(d)}el('first').textContent=JSON.stringify(r.first_pass,null,2);el('comment').value=decisions[r.sample_id]?.note||'';el('accept').disabled=r.review_priority>=90;el('reject').disabled=false;}
function decide(decision){const r=visible[index],actor=el('actor').value.trim();if(!r||!actor){alert('请填写复核人标识');return}decisions[r.sample_id]={sample_id:r.sample_id,text_sha256:r.source.text_sha256,proposal_sha256:r.proposal_sha256,reviewer:actor,decision,note:el('comment').value,reviewed_at:new Date().toISOString()};localStorage.setItem(key,JSON.stringify(decisions));if(el('filter').value!=='pending')index=Math.min(index+1,visible.length-1);refresh()}
el('accept').onclick=()=>decide('accept');el('reject').onclick=()=>decide('revise');el('prev').onclick=()=>{index=Math.max(0,index-1);show()};el('next').onclick=()=>{index=Math.min(visible.length-1,index+1);show()};el('filter').onchange=el('split').onchange=()=>{index=0;refresh()};el('export').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({schema:'kg-gold-adjudications-v3',decisions:Object.values(decisions)},null,2)],{type:'application/json'}));a.download='kg-gold-v3-adjudications.json';a.click();URL.revokeObjectURL(a.href)};refresh();
</script></html>'''
    path.write_text(html.replace('PAYLOAD',payload),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--corpus',type=Path,required=True)
    parser.add_argument('--first-pass',type=Path,required=True)
    parser.add_argument('--second-pass',type=Path,required=True)
    args=parser.parse_args()
    def read(path):
        return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    samples=read(args.corpus/'samples.jsonl')
    source_manifest=json.loads((args.corpus/'manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256((args.corpus/'samples.jsonl').read_bytes()).hexdigest()!=source_manifest['sample_sha256']:
        raise ValueError('frozen corpus checksum mismatch')
    first={r['sample_id']:r for r in read(args.first_pass/'annotations.jsonl')}
    second={r['sample_id']:r for r in read(args.second_pass/'annotations.jsonl')}
    if (set(first)|set(second)) - {s['sample_id'] for s in samples}:
        raise ValueError('annotation sample is outside frozen corpus')
    rows=assemble(samples,first,second)
    target=args.corpus/'candidate-reference.jsonl'
    target.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8',newline='\n')
    render_review(sorted(rows,key=lambda r:(-r['review_priority'],r['sample_id'])),args.corpus/'review.html')
    manifest=dict(schema='kg-reference-rebuild-status-v3',sample_count=len(rows),
        document_count=len({r['source']['document_id'] for r in rows}),
        disposition_counts=dict(Counter(r['proposal'].get('disposition','invalid') for r in rows)),
        review_reason_counts=dict(Counter(reason for r in rows for reason in r['review_reasons'])),
        entities=sum(len(r['proposal']['entities']) for r in rows),relations=sum(len(r['proposal']['relationships']) for r in rows),
        candidate_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),formal_gold_rows=0,
        first_pass_sha256=hashlib.sha256((args.first_pass/'annotations.jsonl').read_bytes()).hexdigest(),
        second_pass_sha256=hashlib.sha256((args.second_pass/'annotations.jsonl').read_bytes()).hexdigest(),
        production_approved=False,independent_human_review=False,
        warning='Two-pass annotations use the same SiliconFlow model as the evaluated provider; not independent gold labels.')
    (args.corpus/'reference-status.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':
    main()
