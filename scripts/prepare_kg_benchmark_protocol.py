"""Prepare source-only pilot/control packets. No remote execution or silver labels."""
from pathlib import Path
import html
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,SOURCE,dump,lines,readlines
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema,validate_proposal


def controls(handbook):
    """Synthetic development-only boundary checks, never acceptance examples."""
    definitions=[
        ('reagent_not_measure','采用盐酸消解土样，使用离心机分离。','方法',[],[],
         '实验试剂和仪器不属于治理措施。'),
        ('medium_boundary','籽粒Cd含量降低，土壤Cd含量未变化。','结果',
         [('i','indicator','chunk','土壤Cd含量',0)],[],
         '籽粒指标不混入土壤指标；降低不自动支持治理效果。'),
        ('algorithm_not_indicator','模型RMSE降低，地图预测精度提高。','制图',[],[],
         '算法精度不是土壤质量指标。'),
        ('instrument_not_indicator','电导池常数为1.0，检查电极。','方法',[],[],
         '仪器参数不属于土壤指标。'),
        ('standard_two_mentions','依据GB/T 123—2020《土壤检测规程》实施。','规范性引用',
         [('s1','standard','chunk','GB/T 123—2020',0),('s2','standard','chunk','土壤检测规程',0)],[],
         '编号与全称分别标；引用本身不证明测定哪项指标。'),
        ('title_is_separate','本文件规定了土壤pH的测定。','GB/T 123—2020',
         [('s','standard','document_title','GB/T 123—2020',0),('i','indicator','chunk','土壤pH',0)],
         [('prescribes_measurement','s','i','normative','本文件规定了土壤pH的测定。')],
         '题名仅用于身份，关系断言必须有正文证据。'),
        ('ocr_no_repair','本实验测定土壈pH。','方法',
         [('i','indicator','chunk','土壈pH',0)],[],
         '可识别OCR表面形式逐字保存，不生成原文不存在的土壤pH。'),
        ('positive_addresses','施用石灰缓解了土壤酸化。','田间结果',
         [('m','measure','chunk','施用石灰',0),('o','obstacle','chunk','土壤酸化',0)],
         [('addresses','m','o','asserted','施用石灰缓解了土壤酸化。')],
         '真实田间干预到障碍的有向关系。'),
        ('negative_effect','试验施用石灰，但未缓解土壤酸化。','田间结果',
         [('m','measure','chunk','施用石灰',0),('o','obstacle','chunk','土壤酸化',0)],
         [('addresses','m','o','negated','试验施用石灰，但未缓解土壤酸化。')],
         '否定必须保留，主肯定关系指标不计该关系为正例。'),
        ('hypothetical_effect','计划施用石灰以缓解土壤酸化，尚未实施。','方案',
         [('m','measure','chunk','施用石灰',0),('o','obstacle','chunk','土壤酸化',0)],
         [('addresses','m','o','hypothetical','计划施用石灰以缓解土壤酸化，尚未实施。')],
         '目的和假设不是已实现效果。'),
        ('occurrence_zero_based','测定土壤pH；再次测定土壤pH。','重复测定',
         [('i1','indicator','chunk','土壤pH',0),('i2','indicator','chunk','土壤pH',1)],[],
         '两处真实mention的序号为0和1，主表面清单去重。'),
        ('material_not_assumed_measure','将生物炭作为实验室吸附剂用于溶液试验。','水溶液实验',[],[],
         '不凭材料名推断田间施用，也不把溶液实验当土壤治理。'),
    ]
    packets,keys=[],[]
    def fragment(packet,block,quote,occ):
        text=next(b['text'] for b in packet['blocks'] if b['block_id']==block)
        start=-len(quote)
        for _ in range(occ+1):
            start=text.index(quote,start+len(quote))
        return dict(block_id=block,text=quote,start=start,end=start+len(quote),occurrence=occ)
    for name,text,title,entities,relations,rationale in definitions:
        packet=source_packet(dict(sample_id='control-v2:'+name,text=text,document_title=title),handbook)
        proposal=dict(entities=[],relations=[],normalization=[],task_masks={
            'entities':'applicable','relations':'applicable','normalization':'applicable'})
        for eid,kind,block,quote,occ in entities:
            proposal['entities'].append(dict(id=eid,type=kind,**fragment(packet,block,quote,occ)))
        for kind,src,tgt,modal,quote in relations:
            evidence=[dict(**fragment(packet,'chunk',quote,0),role='assertion')]
            title_entities=[e for e in proposal['entities'] if e['block_id']=='document_title']
            for e in title_entities:
                evidence.append(dict(**{k:e[k] for k in ['block_id','text','start','end','occurrence']},role='identity'))
            proposal['relations'].append(dict(type=kind,source_id=src,target_id=tgt,
                modality=modal,conditions=[],evidence=evidence))
        check=validate_proposal(packet,proposal,load_schema(ROOT))
        if not check['protocol_complete']:
            raise ValueError('invalid_control_key:'+name+':'+str(check['errors']))
        packets.append(packet)
        keys.append(dict(sample_id=packet['sample_id'],expected=proposal,
            rationale=rationale,synthetic=True,acceptance_eligible=False,
            normalization_policy='unknown_unless_visible_equivalence',
            limitations='author_defined_boundary_control_not_independent_semantic_validation'))
    return packets,keys


def main():
    directory=OUT/'protocol'
    directory.mkdir(parents=True,exist_ok=True)
    handbook_path=ROOT/'docs/knowledge-graph-extraction-benchmark-v2-handbook.md'
    handbook=handbook_path.read_text(encoding='utf-8')
    (directory/'annotation-handbook.md').write_text(handbook,encoding='utf-8')
    packets,keys=controls(handbook)
    lines(directory/'controls-inputs.jsonl',packets)
    lines(directory/'private-control-keys.jsonl',keys)
    # Use historically exposed development sources, not new final candidates.
    pool=readlines(OUT/'audit/document-pool.jsonl')
    old=readlines(ROOT/'artifacts/knowledge_platform/acceptance-v1/pool/selection.jsonl')
    documents={d['id']:d for d in pool if d['exposure_status']=='known_recorded_input_exposure' and d['source_paths']}
    available=[r for r in old if r['document_id'] in documents]
    chosen=[];used=set()
    priorities=['unmapped_pdf_glyph','long_concatenated_english_token','short_visible_text','table_layout',None]
    from framework.knowledge_graph.acceptance_inspection import source_flags
    for flag in priorities:
        for row in available:
            if row['document_id'] in used or (flag and flag not in source_flags(row['text'])):
                continue
            current_path=OUT/f"audit/chunks/{row['document_id']}.jsonl"
            if not current_path.exists():
                continue
            current=next((c for c in readlines(current_path) if c['chunk_index']==row['chunk_index'] and c['text_sha256']==row['text_sha256']),None)
            if current:
                chosen.append(current);used.add(row['document_id'])
            if len(chosen)==10 or (flag and len(chosen)>=priorities.index(flag)+1):
                break
        if len(chosen)==10:
            break
    lines(directory/'pilot-inputs.jsonl',[source_packet(r,handbook) for r in chosen])
    lines(directory/'pilot-source-map.jsonl',[dict(sample_id=r['sample_id'],document_id=r['document_id'],
        page=r['page'],chunk_index=r['chunk_index'],file_sha256=r['file_sha256'],
        source_paths=documents[r['document_id']]['source_paths'],
        use='historically_exposed_development_only') for r in chosen])
    e=lambda x:html.escape(str(x),quote=True)
    cards=[]
    for r in chosen:
        d=documents[r['document_id']]
        links=' '.join(f'<a href="{e((SOURCE/p).as_uri())}#page={r["page"]}">{e(p)} 第{r["page"]}页</a>' for p in d['source_paths'])
        cards.append(f'<section><h2>{e(r["sample_id"])}</h2><p>{links}</p><p>题名：{e(r["document_title"])}</p><pre>{e(r["text"])}</pre><p>状态：待独立双标与来源裁决。解析原文不作纠错。</p></section>')
    (directory/'pilot-review.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>v2 开发试标包</title><style>body{font:15px system-ui;margin:30px;max-width:1200px}pre{white-space:pre-wrap}section{border-top:1px solid #ccc;margin-top:30px}</style><h1>开发试标来源双视图</h1><p>源文件链接与实际输入并列；本页未含新模型答案。</p>'+''.join(cards)+'</html>',encoding='utf-8')
    tracked=[directory/'annotation-handbook.md',directory/'controls-inputs.jsonl',
        directory/'private-control-keys.jsonl',directory/'pilot-inputs.jsonl',
        directory/'pilot-source-map.jsonl',ROOT/'framework/knowledge_graph/benchmark_protocol.py',
        ROOT/'framework/knowledge_graph/schemas/minimal-cultivated-land-kg-schema-v1.json']
    dump(directory/'manifest.json',dict(status='draft_prepared_not_pilot_validated',
        actual_source_pilot_samples=len(chosen),controls=len(packets),model_requests=0,
        annotation_A_completed=0,annotation_B_completed=0,adjudications_completed=0,
        expert_certified=False,handbook_frozen_for_acceptance=False,
        answer_keys_excluded_from_model_packets=True,
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in tracked]))
    print(json.dumps(dict(pilot_sources=len(chosen),synthetic_controls=len(packets),
        control_keys_protocol_valid=True,model_requests=0)))


if __name__=='__main__':main()
