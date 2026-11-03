"""Display actual source-read failures without altering archived labels."""
import html
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines


def main():
    base=OUT/'semantic-quality-audit-v1';e=lambda x:html.escape(str(x),quote=True)
    report=json.loads((base/'report.json').read_text(encoding='utf-8'))
    references={r['sample_id']:r for r in readlines(base/'reviewed-reference-snapshots.jsonl')}
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>参考语义质量拦截</title><style>body{font:16px system-ui;margin:28px;max-width:1250px;color:#243047}pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:1px solid #c5cbd2;padding:20px 0}.alert{background:#ffe5df;padding:20px}h2{font-size:19px}</style><h1>参考语义质量拦截</h1><p class="alert">批次已停止；12条原文抽查中确认6条有问题，另3条需裁决。此抽查按关系有无选取，不能据此估计全体错误率。跨度合法、双标一致和软件测试通过均不保证实体或关系语义正确。校准冻结文件保持原样，暂限开发诊断；最终集不能发布验收通过。</p><p><a href="../dataset-v1/review.html">返回500条审核页</a></p><pre>'+e(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>'
    for row in readlines(base/'items.jsonl'):
        reference=references[row['sample_id']]
        page+='<article><h2>'+e(row['sample_id']+' | '+row['partition']+' | '+row['judgment'])+'</h2>'
        for finding in row['findings']:
            page+='<h3>'+e(finding['category'])+'</h3><p>'+e(finding['reason'])+'</p><pre>'+e(json.dumps(finding['source_spans'],ensure_ascii=False,indent=2))+'</pre>'
        for block in reference['visible_input']['blocks']:
            page+='<h3>原文 '+e(block['block_id'])+'</h3><pre>'+e(block['text'])+'</pre>'
        page+='<details><summary>原参考快照（保留，不改写）</summary><pre>'+e(json.dumps(reference['reference'],ensure_ascii=False,indent=2))+'</pre></details></article>'
    (base/'review.html').write_text(page+'</html>',encoding='utf-8')
    print('semantic_quality_failure_review_rendered',len(references))


if __name__=='__main__':main()
