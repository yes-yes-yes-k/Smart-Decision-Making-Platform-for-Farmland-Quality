"""Static source-and-decision review; no network assets or executable source text."""
import html
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read

OUT=ROOT/'artifacts/knowledge_platform/gold-v4/silver-v1'
def esc(x):return html.escape(str(x),quote=True)
def render():
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'));rows=read(OUT/'reference.jsonl');cards=[]
    for row in rows:
        a=row['annotation'];masks=a['eligibility_by_block'];mentions={m['id']:m for m in a['mentions']}
        masktext='；'.join(f"{bid}：实体{'可评' if v['mentions'] else '排除'} / 关系{'可评' if v['relations'] else '排除'}" for bid,v in masks.items())
        entityrows=''.join('<tr>'+''.join(f'<td>{esc(c)}</td>' for c in [m['id'],m['type'],m['fragment']['block_id'],m['fragment']['text'],f"[{m['fragment']['span_start']},{m['fragment']['span_end']})",m['canonical_name'] or 'unknown','可评' if masks[m['fragment']['block_id']]['mentions'] else '仅保留候选，不评分'])+'</tr>' for m in a['mentions'])
        relations=''.join(f"<li>{esc(mentions[r['source']]['fragment']['text'])} → {esc(r['relation_type'])} → {esc(mentions[r['target']]['fragment']['text'])} ({esc(r['modality'])})<blockquote>{'<hr>'.join(esc(e['text']) for e in r['evidence'])}</blockquote></li>" for r in a['relations'])
        sources=''.join(f"<h3>{esc(b['block_id'])}</h3><pre>{esc(b['text'])}</pre>" for b in row['visible_input']['blocks'])
        cards.append(f"<article id='s{row['index']}'><h2>#{row['index']+1} · {esc(a['sample_id'])}</h2><p class='mask'>{esc(masktext)}</p><p>{esc(a['quality']['reason'])}</p><p>{esc('；'.join(a['uncertainties']))}</p><details><summary>原文与题名（完整可见输入）</summary>{sources}</details><table><thead><tr><th>ID</th><th>类型</th><th>块</th><th>原文片段</th><th>零基位置</th><th>规范名</th><th>评分</th></tr></thead><tbody>{entityrows}</tbody></table><ul>{relations or '<li>无已确认关系</li>'}</ul></article>")
    page="""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>100条 AI 银标逐条裁决</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:30px auto;padding:0 20px;background:#f4f6f8;color:#182431}article{background:white;border:1px solid #ccd5dd;padding:22px;margin:24px 0;border-radius:8px}pre,blockquote{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f4;padding:14px}table{border-collapse:collapse;width:100%;font-size:14px;margin-top:18px}td,th{border:1px solid #ccd5dd;padding:6px;text-align:left;overflow-wrap:anywhere}.mask{color:#834600;font-weight:bold}a{margin:4px}summary{cursor:pointer}h2{font-size:18px}</style><h1>100条 AI 银标：原文裁决记录</h1><p>单一 Codex 裁决，已接触历史标签；非独立双标、专家金标或盲测。正文与题名分开评分；排除项不是正确负例。界面序号从1起，JSON index从0起，原文位置为零基半开区间。</p>"""
    page+=f"<pre>{esc(json.dumps(manifest['counts'],ensure_ascii=False,indent=2))}</pre><nav>"+''.join(f"<a href='#s{i}'>{i+1}</a>" for i in range(100))+'</nav>'+''.join(cards)+'</html>'
    (OUT/'review.html').write_text(page,encoding='utf-8')
    print('static review rendered: 100 source decisions')
if __name__=='__main__':render()
