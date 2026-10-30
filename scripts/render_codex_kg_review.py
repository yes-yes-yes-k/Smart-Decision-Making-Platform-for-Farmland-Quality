"""Read-only browser view of frozen Codex decisions (no model-consensus approval)."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    directory=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3'
    data=[json.loads(x) for x in (directory/'codex-reference.jsonl').read_text(encoding='utf-8').splitlines()]
    encoded=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Codex 逐条审核记录</title>
<style>body{font:16px/1.7 system-ui;margin:28px auto;max-width:1120px;padding:0 24px;color:#172b3a;background:#f6f8fa}button,input,select{font:inherit;padding:7px;margin:5px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;border:1px solid #d4dbe0;border-radius:8px}aside{background:#e8f1f5;padding:18px}h2{margin-bottom:0}#reason{background:#fff7df;padding:16px}label{display:inline-block}</style>
<h1>Codex 逐条审核记录</h1><aside>1,000 条均已直接核对原文。审核者：Codex（AI 智能体）；不是专家人工认证。32 条来源信息不足，保留审计但不评分。原模型提案页面继续保留。
<br><a href="graphrag-v6-codex-report.json">真实 GraphRAG 评测报告（运行中时为阶段数据）</a> · <a href="codex-reference.manifest.json">冻结参考集清单</a> · <a href="review.html">原模型提案</a></aside>
<label>筛选 <select id="filter"><option value="all">全部</option><option value="relations">有关系</option><option value="negative">无本体事实</option><option value="unknown">来源不足</option></select></label>
<label>集合 <select id="split"><option value="all">全部</option><option>development</option><option>validation</option><option>test</option></select></label>
<label>搜索 <input id="search" placeholder="文献、实体或审核理由"></label><p><button id="prev">上一条</button><span id="count"></span><button id="next">下一条</button></p>
<h2 id="title"></h2><p id="meta"></p><p id="reason"></p><h3>原文</h3><pre id="source"></pre><h3>审核后实体</h3><pre id="entities"></pre><h3>审核后关系及证据</h3><pre id="relations"></pre><p id="audit"></p>
<script id="data" type="application/json">'''+encoded+'''</script><script>
const rows=JSON.parse(document.getElementById('data').textContent);let filtered=rows,index=0;
const el=id=>document.getElementById(id);
function show(){const r=filtered[index];el('count').textContent=filtered.length?`${index+1} / ${filtered.length}`:'0 / 0';el('prev').disabled=index===0;el('next').disabled=index>=filtered.length-1;if(!r){for(const id of ['title','meta','reason','source','entities','relations','audit'])el(id).textContent='';return;}
el('title').textContent=`第 ${r.index+1} 条 · ${r.source.document_title}`;
el('meta').textContent=`${r.source.split} · 文献 ${r.source.document_id} · 页 ${r.source.page} · 分块 ${r.source.chunk_index} · ${r.evaluation_eligible?'可评分':'来源不足，不评分'}`;
el('reason').textContent=r.adjudication.reason+(r.evaluation_eligible?'':'\n'+r.source_quality);
el('source').textContent=r.source.text;el('entities').textContent=r.entities.map(e=>`${e.name} [${e.type}]`).join('\n')||'无匹配本体实体';
el('relations').textContent=r.relationships.map(e=>`${e.source} — ${e.relation_type} → ${e.target}\n证据 [${e.span_start}, ${e.span_end})：${e.quote}`).join('\n\n')||'无可确认关系';
el('audit').textContent=`审核者 Codex / ai_agent · ${r.adjudication.reviewed_at} · 原文 SHA256 ${r.source.text_sha256}`;}
function apply(){const q=el('search').value.toLowerCase();filtered=rows.filter(r=>(el('split').value==='all'||r.source.split===el('split').value)&&(el('filter').value==='all'||(el('filter').value==='relations'&&r.relationships.length)||(el('filter').value==='negative'&&r.evaluation_eligible&&!r.entities.length)||(el('filter').value==='unknown'&&!r.evaluation_eligible))&&(!q||JSON.stringify([r.source.document_title,r.entities,r.adjudication.reason]).toLowerCase().includes(q)));index=0;show();}
for(const id of ['filter','split','search'])el(id).addEventListener('input',apply);el('prev').onclick=()=>{index=Math.max(0,index-1);show();};el('next').onclick=()=>{index=Math.min(filtered.length-1,index+1);show();};show();
</script></html>'''
    # Keep JS newline escapes literal in this Python-generated page.
    html=html.replace("?'':'\n'", "?'':'\\n'").replace(".join('\n')", ".join('\\n')").replace(".join('\n\n')", ".join('\\n\\n')")
    (directory/'codex-review.html').write_text(html,encoding='utf-8')
    original=directory/'review.html'
    text=original.read_text(encoding='utf-8')
    banner='<p id="codex-progress">Codex 已逐条审核 1,000 / 1,000，参考集已冻结，32 条来源不足单列。<a href="codex-review.html">查看逐条修订、理由与证据</a>。审核者为 AI 智能体，非专家人工认证；真实评测见审核记录页。</p>'
    original.write_text(re.sub(r'<p id="codex-progress">.*?</p>',banner,text,count=1),encoding='utf-8')
    print('Rendered codex-review.html; original proposals preserved')


if __name__=='__main__':
    main()
