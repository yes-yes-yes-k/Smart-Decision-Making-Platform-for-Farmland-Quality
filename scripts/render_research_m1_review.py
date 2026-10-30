"""Local audit of the captured real product flow, not a live permission cache."""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_research_m1_pilot import OUT


def main():
    if (OUT/"completion-manifest-v1.json").exists():
        raise ValueError("M1_review_frozen_verify_manifest_or_use_new_version")
    report = json.loads((OUT/"product-pilot-v2.json").read_text(encoding="utf-8"))
    selection = json.loads((OUT/"selection.json").read_text(encoding="utf-8"))
    report["selection"] = selection
    payload = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M1文献证据对照试点</title>
<style>body{font:16px/1.6 system-ui;max-width:1300px;margin:32px auto;padding:16px;color:#233044;background:#f7f9fc}section{background:white;border:1px solid #dce3ed;padding:18px;margin:14px 0;border-radius:10px}.notice{background:#fff0c9;padding:16px}select{padding:10px;width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{border:1px solid #dce3ed;padding:8px;text-align:left;vertical-align:top}summary{cursor:pointer}h2{font-size:20px}</style>
<h1>M1：十篇真实文献证据对照</h1>
<p class="notice">这是隔离产品实例的审计快照，不是在线服务，也不是已确认知识发布。来源重解析均通过，但自动抽取仅有2条记录通过精确原文校验；空结果和被拒收选择保留为覆盖缺口，不能解释为论文没有相关效应。图谱未配置，本页不宣称GraphRAG收益。</p>
<p id="summary"></p><select id="select"></select><section><h2 id="title"></h2><pre id="coverage"></pre></section>
<section><h2>原文检索结果与页码</h2><div id="search"></div></section>
<section><h2>研究记录对照（待审）</h2><p>未知不是任意条件；相反或不同条件的结论不自动合并。结果值保持原文，不做效应汇总。</p><div id="comparison"></div></section>
<details><summary>全部十篇与抽取缺口</summary><pre id="diagnostics"></pre></details>
<details><summary>两篇有可用记录的合并对照</summary><pre id="combined"></pre></details>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent),sel=document.getElementById('select');
const names=Object.fromEntries(data.selection.documents.map(d=>[d.id,d.title||d.name]));
document.getElementById('summary').textContent=`捕获时间：${data.captured_at_utc}；10篇／1306块原件重解析一致；发布新增断言：0。重新访问产品API时会再次检查当前来源、权限和版本，本地快照本身不会随来源变化自动更新。`;
data.documents.forEach((d,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${d.document_id} · ${d.stratum} · ${names[d.document_id]}`;sel.append(o)});
document.getElementById('diagnostics').textContent=JSON.stringify(data.record_compilation,null,2);
document.getElementById('combined').textContent=JSON.stringify(data.combined_comparison.result,null,2);
function show(){const d=data.documents[+sel.value];document.getElementById('title').textContent=names[d.document_id];const diag=data.record_compilation.documents.find(v=>v.document_id===d.document_id);document.getElementById('coverage').textContent=JSON.stringify({来源层:d.stratum,上下文核对:d.context_matches,抽取:diag,产品任务状态:d.comparison.state},null,2);const search=document.getElementById('search');search.replaceChildren();d.search.sources.forEach(s=>{const det=document.createElement('details'),sum=document.createElement('summary'),p=document.createElement('pre');sum.textContent=`页${s.page} · 分块${s.chunk_index} · 文献${s.document_id}`;p.textContent=s.text;det.append(sum,p);search.append(det)});const out=document.getElementById('comparison');out.replaceChildren();const rows=d.comparison.result.rows;if(!rows.length){out.textContent='当前没有通过原文校验且匹配本次请求的研究记录；仍可查看上述原文。此处不作无效应结论。';return}rows.forEach(r=>{const table=document.createElement('table');Object.entries(r.fields).forEach(([name,value])=>{const tr=document.createElement('tr'),k=document.createElement('th'),v=document.createElement('td');k.textContent=name;v.textContent=value.value===null?'未知':value.value;if(value.evidence){const p=document.createElement('small');p.style.display='block';p.textContent=`原文：页${value.evidence.page}／块${value.evidence.chunk_index}／字符${value.evidence.span_start}–${value.evidence.span_end}`;v.append(p)}tr.append(k,v);table.append(tr)});out.append(table)})}sel.onchange=show;show();</script></html>'''.replace("PAYLOAD", payload)
    (OUT/"review.html").write_bytes(page.encode("utf-8"))
    print(json.dumps({"review": str(OUT/"review.html"), "papers": len(report["documents"]), "external_assets": 0}))


if __name__ == "__main__":
    main()
