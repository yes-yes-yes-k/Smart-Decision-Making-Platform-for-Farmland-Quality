"""Render the reviewed cultivated-land graph as a self-contained HTML file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>耕地质量知识图谱 v0.3</title>
<style>
  :root {
    --ink:#17372d; --muted:#64756f; --paper:#f6f7f2; --card:#fff;
    --indicator:#2878b5; --obstacle:#d85f48; --measure:#2f9662; --standard:#8a61b3;
    --line:#dfe6df; --shadow:0 10px 30px rgba(28,58,47,.09);
  }
  *{box-sizing:border-box} body{margin:0;background:var(--paper);color:var(--ink);font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif}
  header{padding:34px 40px 30px;background:linear-gradient(125deg,#123c31,#22634d 65%,#4b7750);color:white}
  header .eyebrow{font-size:13px;letter-spacing:.18em;opacity:.75} h1{margin:8px 0 10px;font-size:34px;font-weight:750}
  header p{margin:0;max-width:850px;color:#d9eee4;line-height:1.7}
  main{max-width:1560px;margin:auto;padding:26px 28px 56px}.section{margin-top:24px}
  .stats{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:14px;margin-top:-48px}
  .stat{background:rgba(255,255,255,.97);border:1px solid rgba(255,255,255,.75);border-radius:16px;padding:18px 20px;box-shadow:var(--shadow)}
  .stat b{display:block;font-size:28px}.stat span{font-size:13px;color:var(--muted)}
  .panel{background:var(--card);border:1px solid #e6ebe6;border-radius:18px;box-shadow:var(--shadow);overflow:hidden}
  .panel-title{display:flex;align-items:center;justify-content:space-between;padding:20px 22px 12px}.panel-title h2{margin:0;font-size:20px}.panel-title p{margin:4px 0 0;color:var(--muted);font-size:13px}
  .overview{padding:10px 22px 22px}.flow{display:grid;grid-template-columns:1fr 120px 1fr 120px 1fr 120px 1fr;align-items:center;gap:8px}
  .kind{border-radius:14px;padding:16px 12px;color:#fff;text-align:center;min-height:78px;display:grid;place-content:center;box-shadow:0 8px 18px rgba(20,50,40,.12)}
  .kind b{font-size:17px}.kind small{opacity:.8;margin-top:4px}.standard{background:var(--standard)}.indicator{background:var(--indicator)}.obstacle{background:var(--obstacle)}.measure{background:var(--measure)}
  .arrow{text-align:center;color:var(--muted);font-size:12px}.arrow strong{display:block;color:#3a5b4e;font-size:22px;line-height:1}.secondary-relations{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;color:var(--muted);font-size:12px}
  .relation-pill{border:1px solid var(--line);border-radius:999px;padding:6px 10px;background:#fafbf8}
  .workspace{display:grid;grid-template-columns:minmax(700px,1fr) 340px;min-height:790px;border-top:1px solid var(--line)}
  .graph-side{min-width:0;position:relative}.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line);background:#fbfcfa}
  input,select,button{font:inherit}input[type=search],select{border:1px solid #cfd9d2;border-radius:9px;background:white;padding:9px 11px;color:var(--ink)}
  input[type=search]{width:235px}.filter-group{display:flex;gap:6px;flex-wrap:wrap}.toggle{border:1px solid #d7dfd9;background:white;border-radius:999px;padding:7px 10px;cursor:pointer;font-size:12px}.toggle.off{opacity:.35}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
  button.action{border:0;border-radius:9px;padding:9px 12px;background:#245f4d;color:white;cursor:pointer}button.secondary{background:#edf3ef;color:#315a4c}
  .graph-wrap{height:720px;position:relative;background-image:radial-gradient(#dce5de 1px,transparent 1px);background-size:22px 22px;overflow:hidden}
  svg{width:100%;height:100%;display:block}.node{cursor:pointer}.node rect{stroke:white;stroke-width:2;filter:drop-shadow(0 4px 5px rgba(20,50,40,.12))}.node text{fill:white;font-size:12px;font-weight:650;pointer-events:none}.node.dim,.edge.dim{opacity:.07}.node.selected rect{stroke:#102e26;stroke-width:4}.node.match rect{stroke:#f4c64f;stroke-width:4}
  .edge{fill:none;stroke-width:1.7;opacity:.28;transition:opacity .15s,stroke-width .15s}.edge.active{opacity:.92;stroke-width:3}.edge-label{font-size:10px;fill:#334e44;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round;display:none}.edge-label.active{display:block}
  .lane-title{font-size:13px;font-weight:750;fill:#5f726a;letter-spacing:.08em}.lane-line{stroke:#d6ded8;stroke-dasharray:4 7}
  .detail{border-left:1px solid var(--line);background:#fcfdfa;padding:20px;overflow:auto;height:790px}.detail h3{margin:0 0 6px;font-size:20px}.detail .type{display:inline-block;color:white;border-radius:999px;padding:4px 9px;font-size:11px;margin-bottom:14px}.detail .hint{color:var(--muted);line-height:1.7;font-size:13px}
  .meta{font-size:12px;color:var(--muted);line-height:1.7}.rel-card{margin:11px 0;border:1px solid var(--line);border-radius:12px;padding:11px;background:white}.rel-card b{display:block;font-size:13px}.rel-card small{display:block;color:var(--muted);margin-top:3px}.evidence{margin-top:7px;padding-top:7px;border-top:1px dashed #d9e1db;font-size:11px;color:#586b64;line-height:1.5}
  .legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--muted)}.legend i{width:18px;height:3px;display:inline-block;vertical-align:middle;margin-right:4px}
  .empty{display:grid;place-items:center;height:100%;color:var(--muted);text-align:center;padding:30px}
  footer{color:var(--muted);font-size:12px;text-align:center;margin-top:22px;line-height:1.7}
  @media(max-width:1050px){.stats{grid-template-columns:repeat(2,1fr)}.flow{grid-template-columns:1fr}.arrow{transform:rotate(90deg);padding:8px}.workspace{grid-template-columns:1fr}.detail{border-left:0;border-top:1px solid var(--line);height:auto}.graph-wrap{height:680px}}
  @media(max-width:620px){header{padding:26px 20px 70px}main{padding:18px 12px}.stats{grid-template-columns:1fr 1fr}.stat{padding:14px}.stat b{font-size:23px}h1{font-size:27px}.panel-title{padding:16px}.overview{padding:8px 14px 18px}.workspace{min-height:0}.graph-wrap{height:610px}.toolbar{padding:10px}input[type=search]{width:100%}}
</style>
</head>
<body>
<header>
  <div class="eyebrow">CULTIVATED LAND KNOWLEDGE GRAPH</div>
  <h1>耕地质量知识图谱 v0.3</h1>
  <p>围绕“指标—障碍因素—改良措施—标准依据”构建的材料级核验图谱。箭头表示有正式文献证据支持的关系，点击任一实体可查看相邻关系及证据位置。</p>
</header>
<main>
  <section class="stats">
    <div class="stat"><b id="entityCount">—</b><span>正式实体</span></div>
    <div class="stat"><b id="relationCount">—</b><span>正式关系</span></div>
    <div class="stat"><b id="evidenceCount">—</b><span>关系证据</span></div>
    <div class="stat"><b id="documentCount">—</b><span>代表性资料</span></div>
  </section>

  <section class="section panel">
    <div class="panel-title"><div><h2>先看总体逻辑</h2><p>四类实体之间不是任意相连，而是受六类正式关系约束。</p></div></div>
    <div class="overview">
      <div class="flow">
        <div class="kind standard"><b>标准依据</b><small>5 个实体</small></div>
        <div class="arrow"><strong>→</strong>纳入指标<br>规定测定</div>
        <div class="kind indicator"><b>耕地质量指标</b><small>12 个实体</small></div>
        <div class="arrow"><strong>←</strong>障碍由指标表征</div>
        <div class="kind obstacle"><b>障碍因素</b><small>9 个实体</small></div>
        <div class="arrow"><strong>←</strong>措施针对障碍</div>
        <div class="kind measure"><b>改良措施</b><small>12 个实体</small></div>
      </div>
      <div class="secondary-relations">
        <span class="relation-pill">标准依据 → 障碍因素：作为判定依据</span>
        <span class="relation-pill">改良措施 → 指标：直接改善指标</span>
        <span class="relation-pill">每条关系均保留：文档、页码、原文证据</span>
      </div>
    </div>
  </section>

  <section class="section panel">
    <div class="panel-title">
      <div><h2>全部实体关系</h2><p>默认显示全图；点击节点聚焦其一跳关系，滚轮缩放、拖动画布。</p></div>
      <div class="legend" id="relationLegend"></div>
    </div>
    <div class="workspace">
      <div class="graph-side">
        <div class="toolbar">
          <input id="search" type="search" placeholder="搜索实体，如：土壤酸化">
          <div class="filter-group" id="typeFilters"></div>
          <select id="relationFilter"><option value="all">全部关系</option></select>
          <button class="action secondary" id="reset">重置视图</button>
          <button class="action" id="download">下载 SVG</button>
        </div>
        <div class="graph-wrap"><svg id="graph" viewBox="0 0 1460 760" aria-label="耕地质量知识图谱"></svg></div>
      </div>
      <aside class="detail" id="detail">
        <div class="empty"><div><b>选择一个实体</b><br><span class="hint">点击图中的实体，可查看别名、相邻关系、证据资料和页码。</span></div></div>
      </aside>
    </div>
  </section>
  <footer>数据来源：cultivated_land_minimal_graph_v0.3.json ｜ 图中关系均为材料级核验结果，不代表超出当前资料范围的普遍结论。</footer>
</main>
<script>
const GRAPH = __GRAPH_JSON__;
const TYPE = {
  standard:{label:'标准依据',color:'#8a61b3',x:165,width:300},
  indicator:{label:'质量指标',color:'#2878b5',x:565,width:190},
  obstacle:{label:'障碍因素',color:'#d85f48',x:930,width:190},
  measure:{label:'改良措施',color:'#2f9662',x:1290,width:190}
};
const REL = {
  addresses:{label:'针对改良',color:'#d8872f'},
  improves_indicator:{label:'改善指标',color:'#2e9c84'},
  characterized_by:{label:'指标表征',color:'#c94f63'},
  includes_indicator:{label:'纳入指标',color:'#6f6ac7'},
  prescribes_measurement:{label:'规定测定',color:'#3677a8'},
  assessment_basis:{label:'判定依据',color:'#9b6b45'}
};
const entityMap = new Map(GRAPH.entities.map(d=>[d.id,d]));
const typeCounts = Object.fromEntries(Object.keys(TYPE).map(t=>[t,GRAPH.entities.filter(e=>e.type===t).length]));
document.getElementById('entityCount').textContent=GRAPH.entities.length;
document.getElementById('relationCount').textContent=GRAPH.relations.length;
document.getElementById('evidenceCount').textContent=GRAPH.relations.reduce((n,r)=>n+(r.evidence||[]).length,0);
document.getElementById('documentCount').textContent=GRAPH.corpus.length;

const svg=document.getElementById('graph');
const NS='http://www.w3.org/2000/svg';
function el(tag,attrs={},text=''){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text)n.textContent=text;return n}
const defs=el('defs');
Object.entries(REL).forEach(([key,r])=>{const m=el('marker',{id:'arrow-'+key,viewBox:'0 0 10 10',refX:'8',refY:'5',markerWidth:'6',markerHeight:'6',orient:'auto-start-reverse'});m.appendChild(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:r.color}));defs.appendChild(m)});svg.appendChild(defs);
const root=el('g',{id:'viewport'});svg.appendChild(root);
const bg=el('rect',{x:0,y:0,width:1460,height:760,fill:'transparent'});root.appendChild(bg);
Object.entries(TYPE).forEach(([key,t])=>{root.appendChild(el('text',{x:t.x,y:25,'text-anchor':'middle',class:'lane-title'},`${t.label} · ${typeCounts[key]}`));root.appendChild(el('line',{x1:t.x,y1:38,x2:t.x,y2:735,class:'lane-line'}))});
const edgeLayer=el('g');const labelLayer=el('g');const nodeLayer=el('g');root.append(edgeLayer,labelLayer,nodeLayer);

const positions={};
Object.keys(TYPE).forEach(type=>{
  const items=GRAPH.entities.filter(e=>e.type===type).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN'));
  const top=58,bottom=720,step=(bottom-top)/Math.max(items.length-1,1);
  items.forEach((item,i)=>positions[item.id]={x:TYPE[type].x,y:top+i*step,w:TYPE[type].width,h:34});
});
function edgePath(r,i){const s=positions[r.source],t=positions[r.target];const sx=s.x+(t.x>s.x?s.w/2:-s.w/2),tx=t.x+(t.x>s.x?-t.w/2:t.w/2);const bend=Math.min(150,Math.abs(tx-sx)*.34);const c1=sx+(tx>sx?bend:-bend),c2=tx-(tx>sx?bend:-bend);return `M${sx},${s.y} C${c1},${s.y} ${c2},${t.y} ${tx},${t.y}`}
const edgeEls=new Map(),labelEls=new Map();
GRAPH.relations.forEach((r,i)=>{
  const info=REL[r.type]||{label:r.type,color:'#718078'};const d=edgePath(r,i);
  const path=el('path',{d,class:'edge','data-id':r.id,stroke:info.color,'marker-end':`url(#arrow-${r.type})`});path.appendChild(el('title',{},`${entityMap.get(r.source).name} —${info.label}→ ${entityMap.get(r.target).name}`));edgeLayer.appendChild(path);edgeEls.set(r.id,path);
  const p=path.getPointAtLength(path.getTotalLength()/2);const label=el('text',{x:p.x,y:p.y-4,'text-anchor':'middle',class:'edge-label'},info.label);labelLayer.appendChild(label);labelEls.set(r.id,label);
});
const nodeEls=new Map();
GRAPH.entities.forEach(e=>{const p=positions[e.id],g=el('g',{class:'node','data-id':e.id,transform:`translate(${p.x-p.w/2},${p.y-p.h/2})`});g.appendChild(el('rect',{width:p.w,height:p.h,rx:10,fill:TYPE[e.type].color}));const shown=e.name.length>20?e.name.slice(0,19)+'…':e.name;g.appendChild(el('text',{x:p.w/2,y:p.h/2+4,'text-anchor':'middle'},shown));g.appendChild(el('title',{},e.name));g.addEventListener('click',ev=>{ev.stopPropagation();selectNode(e.id)});nodeLayer.appendChild(g);nodeEls.set(e.id,g)});

const enabledTypes=new Set(Object.keys(TYPE));let relationFilter='all',selected=null,searchValue='';
function visibleRelation(r){return enabledTypes.has(entityMap.get(r.source).type)&&enabledTypes.has(entityMap.get(r.target).type)&&(relationFilter==='all'||r.type===relationFilter)}
function refresh(){
  const matching=new Set();if(searchValue){GRAPH.entities.forEach(e=>{const terms=[e.name,...(e.aliases||[]),...(e.retrieval_terms||[])].join(' ').toLowerCase();if(terms.includes(searchValue))matching.add(e.id)})}
  GRAPH.entities.forEach(e=>{const g=nodeEls.get(e.id);const allowed=enabledTypes.has(e.type);const focus=!selected||e.id===selected||GRAPH.relations.some(r=>(r.source===selected&&r.target===e.id)||(r.target===selected&&r.source===e.id));g.classList.toggle('dim',!allowed||(selected&&!focus));g.classList.toggle('selected',e.id===selected);g.classList.toggle('match',matching.has(e.id))});
  GRAPH.relations.forEach(r=>{const e=edgeEls.get(r.id),l=labelEls.get(r.id);const active=selected&&(r.source===selected||r.target===selected)&&visibleRelation(r);e.style.display=visibleRelation(r)?'':'none';l.style.display=visibleRelation(r)?'':'none';e.classList.toggle('active',!!active);e.classList.toggle('dim',!!selected&&!active);l.classList.toggle('active',!!active)});
}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function selectNode(id){selected=id;const e=entityMap.get(id),rels=GRAPH.relations.filter(r=>(r.source===id||r.target===id)&&visibleRelation(r));const aliases=(e.aliases||[]).filter(a=>a!==e.name);let html=`<span class="type" style="background:${TYPE[e.type].color}">${TYPE[e.type].label}</span><h3>${esc(e.name)}</h3><div class="meta">实体编号：${esc(e.id)}${aliases.length?'<br>别名：'+aliases.map(esc).join('、'):''}</div><h4>相邻关系（${rels.length}）</h4>`;
  if(!rels.length)html+='<p class="hint">当前筛选条件下没有相邻关系。</p>';
  rels.forEach(r=>{const isSource=r.source===id,other=entityMap.get(isSource?r.target:r.source),ri=REL[r.type]||{label:r.type};const arrow=isSource?`—${ri.label}→`:`←${ri.label}—`;const evidence=r.evidence||[];html+=`<div class="rel-card"><b>${esc(e.name)} ${arrow} ${esc(other.name)}</b><small>${esc(r.type)} · ${evidence.length} 条证据</small>`;evidence.slice(0,3).forEach(v=>{html+=`<div class="evidence">《${esc(v.document_title)}》第 ${esc(v.page??'—')} 页${v.quote?'：'+esc(v.quote.slice(0,90)):''}</div>`});if(evidence.length>3)html+=`<div class="evidence">另有 ${evidence.length-3} 条证据</div>`;html+='</div>'});document.getElementById('detail').innerHTML=html;refresh()}

const typeFilters=document.getElementById('typeFilters');Object.entries(TYPE).forEach(([key,t])=>{const b=document.createElement('button');b.className='toggle';b.innerHTML=`<span class="dot" style="background:${t.color}"></span>${t.label}`;b.onclick=()=>{enabledTypes.has(key)?enabledTypes.delete(key):enabledTypes.add(key);b.classList.toggle('off',!enabledTypes.has(key));if(selected&&!enabledTypes.has(entityMap.get(selected).type))selected=null;refresh()};typeFilters.appendChild(b)});
const rf=document.getElementById('relationFilter');Object.entries(REL).forEach(([key,r])=>{const o=document.createElement('option');o.value=key;o.textContent=`${r.label}（${GRAPH.relations.filter(x=>x.type===key).length}）`;rf.appendChild(o)});rf.onchange=()=>{relationFilter=rf.value;if(selected)selectNode(selected);else refresh()};
document.getElementById('relationLegend').innerHTML=Object.entries(REL).map(([k,r])=>`<span><i style="background:${r.color}"></i>${r.label}</span>`).join('');
document.getElementById('search').addEventListener('input',e=>{searchValue=e.target.value.trim().toLowerCase();refresh()});

let scale=1,tx=0,ty=0,panning=false,start=null;function applyTransform(){root.setAttribute('transform',`translate(${tx} ${ty}) scale(${scale})`)}
svg.addEventListener('wheel',e=>{e.preventDefault();const factor=e.deltaY<0?1.12:.89;scale=Math.max(.45,Math.min(2.6,scale*factor));applyTransform()},{passive:false});
svg.addEventListener('pointerdown',e=>{if(e.target.closest&&e.target.closest('.node'))return;panning=true;start={x:e.clientX-tx,y:e.clientY-ty};svg.setPointerCapture(e.pointerId)});svg.addEventListener('pointermove',e=>{if(!panning)return;tx=e.clientX-start.x;ty=e.clientY-start.y;applyTransform()});svg.addEventListener('pointerup',()=>panning=false);
bg.addEventListener('click',()=>{selected=null;document.getElementById('detail').innerHTML='<div class="empty"><div><b>选择一个实体</b><br><span class="hint">点击图中的实体，可查看别名、相邻关系、证据资料和页码。</span></div></div>';refresh()});
document.getElementById('reset').onclick=()=>{scale=1;tx=0;ty=0;selected=null;searchValue='';document.getElementById('search').value='';enabledTypes.clear();Object.keys(TYPE).forEach(x=>enabledTypes.add(x));document.querySelectorAll('.toggle').forEach(x=>x.classList.remove('off'));relationFilter='all';rf.value='all';applyTransform();refresh()};
document.getElementById('download').onclick=()=>{const clone=svg.cloneNode(true);clone.setAttribute('xmlns',NS);clone.setAttribute('width','1460');clone.setAttribute('height','760');const data=new XMLSerializer().serializeToString(clone);const blob=new Blob([data],{type:'image/svg+xml;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='耕地质量知识图谱_v0.3.svg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
refresh();
</script>
</body>
</html>'''


def render(graph_path: Path, output_path: Path) -> None:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    if graph.get("schema_version") != "minimal-cultivated-land-kg-v0.3":
        raise ValueError("仅支持 minimal-cultivated-land-kg-v0.3")
    graph_json = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    graph_json = graph_json.replace("</script", "<\\/script")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        HTML_TEMPLATE.replace("__GRAPH_JSON__", graph_json), encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--graph", type=Path,
        default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_kg_v03_visualization.html",
    )
    args = parser.parse_args()
    render(args.graph, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
