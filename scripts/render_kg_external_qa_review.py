"""Render a local, source-linked QA audit page from saved real predictions."""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_kg_external_qa_pilot_v2 import RUN, OUT, read
from framework.knowledge_graph.external_qa_evaluation import source_retrieval


def main():
    from framework.knowledge_graph.external_benchmark_freeze import require_mutable
    require_mutable(OUT, RUN/"review.html")
    records = []
    for dataset in ("qasper", "multihop_rag"):
        base = RUN/dataset
        questions = read(base/"inputs/questions.jsonl")
        docs = read(base/"inputs/documents.jsonl")
        blocks = {(doc["id"], block["id"]): block for doc in docs for block in doc["blocks"]}
        ref_path = OUT/("references/qasper/train.references.jsonl" if dataset == "qasper" else "references/multihop-v2/calibration.references.jsonl")
        refs = {row["id"]: row for row in read(ref_path)}
        arms = {}
        for arm in ("vector", "graphrag"):
            arms[arm] = {}
            predictions = base/arm/"predictions.jsonl"
            if not predictions.exists():
                continue
            judgments = base/arm/"semantic-v1/judgments.jsonl"
            judged = {row["question_id"]: row for row in read(judgments)} if judgments.exists() else {}
            for row in read(predictions):
                retrieved, errors = source_retrieval(row, blocks)
                arms[arm][row["question_id"]] = {"prediction": row, "resolved_sources": retrieved, "invalid_sources": errors,
                                                "judgment": judged.get(row["question_id"], {"state": "not_judged"})}
        for question in questions:
            records.append({"dataset": dataset, **question, "reference": refs[question["id"]],
                            "arms": {name: values.get(question["id"], {"state": "missing_prediction"}) for name, values in arms.items()}})
    payload = json.dumps(records, ensure_ascii=False).replace("<", "\\u003c")
    page = '''<!doctype html><meta charset="utf-8"><title>外部问答试跑来源审核</title>
<style>body{font:16px system-ui;max-width:1300px;margin:32px auto;padding:12px;color:#203047}select{padding:10px;width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f8;padding:16px}article{display:grid;grid-template-columns:1fr 1fr;gap:20px}section{min-width:0}summary{cursor:pointer;padding:8px}a{color:#2463b5}</style>
<h1>外部问答试跑：来源与回答审核</h1><p>26 道非最终题；同模型语义复核，不构成专家认证或正式验收。正文与元数据指针均保留，缺失结果不会从分母排除。</p>
<p><a href="../../review.html">返回外部评测总览</a></p><select id="pick"></select><h2 id="question"></h2><details><summary>原生参考（只用于评分，不输入生成）</summary><pre id="reference"></pre></details><article id="arms"></article>
<script id="data" type="application/json">PAYLOAD</script><script>
const rows=JSON.parse(document.getElementById('data').textContent),pick=document.getElementById('pick');
rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${i+1}. ${r.dataset} — ${r.question}`;pick.append(o)});
function show(){const r=rows[+pick.value];document.getElementById('question').textContent=r.question;document.getElementById('reference').textContent=JSON.stringify(r.reference,null,2);const root=document.getElementById('arms');root.replaceChildren();Object.entries(r.arms).forEach(([name,value])=>{const s=document.createElement('section'),h=document.createElement('h2');h.textContent=name;s.append(h);for(const [title,data] of [['模型回答',value.prediction||value],['独立语义复核',value.judgment],['检索原文及位置',value.resolved_sources],['来源错误',value.invalid_sources]]){const d=document.createElement('details'),t=document.createElement('summary'),p=document.createElement('pre');d.open=title==='模型回答';t.textContent=title;p.textContent=JSON.stringify(data,null,2);d.append(t,p);s.append(d)}root.append(s)})}pick.onchange=show;show();</script>'''.replace("PAYLOAD", payload)
    path = RUN/"review.html"
    path.write_bytes(page.encode("utf-8"))
    print(json.dumps({"path": str(path), "questions": len(records), "external_network_dependencies": 0}))


if __name__ == "__main__":
    main()
