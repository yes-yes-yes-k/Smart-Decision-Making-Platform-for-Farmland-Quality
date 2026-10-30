"""Offline vocabulary coverage and no-deletion audit on isolated development documents."""
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import BASE,read,write,jsonl,sha
from scripts.score_kg_corpus import fact_sets,scores,normalize
from framework.knowledge_graph.candidate_inventory import build_vocabulary,inventory,apply_review
from framework.knowledge_graph.candidate_selection import candidates,relation_candidates
from framework.knowledge_graph.schema import load_graph_schema

OUT=BASE/'candidate-retention-v12'

def main():
    if OUT.exists():raise ValueError('frozen audit already exists')
    parent=json.loads((BASE/'codex-reference.manifest.json').read_text())
    assert sha(BASE/'codex-reference.jsonl')==parent['reference_sha256']
    dev=[r for r in read(BASE/'codex-reference.jsonl') if r['source']['split']=='development' and r['evaluation_eligible']]
    prior=read(BASE/'development-candidate-v11-pilot/reference.jsonl')
    excluded={r['source']['leakage_group'] for r in prior};probe=[]
    import hashlib
    for disposition in ('relations','entities','negative'):
        pool=sorted([r for r in dev if r['source']['leakage_group'] not in excluded and
            ('relations' if r['relationships'] else 'entities' if r['entities'] else 'negative')==disposition],
            key=lambda r:hashlib.sha256(r['sample_id'].encode()).hexdigest())
        picked=0
        for row in pool:
            group=row['source']['leakage_group']
            if group in excluded:continue
            probe.append(row);excluded.add(group);picked+=1
            if picked==8:break
        if picked!=8:raise ValueError('insufficient independent probe documents')
    training=[r for r in dev if r['source']['leakage_group'] not in excluded]
    assert {r['source']['leakage_group'] for r in training}.isdisjoint(excluded)
    vocabulary=build_vocabulary(training,excluded)
    OUT.mkdir()
    jsonl(OUT/'training-reference.jsonl',training);jsonl(OUT/'probe-reference.jsonl',probe);jsonl(OUT/'vocabulary.jsonl',vocabulary)
    manifest=dict(parent_reference_sha256=parent['reference_sha256'],vocabulary_sha256=sha(OUT/'vocabulary.jsonl'),
        training_sha256=sha(OUT/'training-reference.jsonl'),probe_sha256=sha(OUT/'probe-reference.jsonl'),
        training_samples=len(training),training_groups=len({r['source']['leakage_group'] for r in training}),
        excluded_probe_and_prior_groups=sorted(excluded),probe_samples=len(probe),probe_groups=len({r['source']['leakage_group'] for r in probe}),
        vocabulary_terms=len(vocabulary),module_sha256=sha(ROOT/'framework/knowledge_graph/candidate_inventory.py'),
        protocol='fixed union of seed and source-literal training terms; no longest-span deletion; missing reviews => needs_review',
        reference_kind='AI-reviewed development labels used as supervised vocabulary training; not expert gold',
        evaluation_scope='development diagnostic only; document-group isolated within development, not untouched validation/test',
        production_approved=False,model_calls=0)
    write(OUT/'manifest.json',manifest)
    reports={};schema=load_graph_schema()
    for name,rows in [('prior_pilot',prior),('isolated_probe',probe)]:
        details=[];gold=set();seed=set();expanded=set();rel_gold=set();rel_seed=set();rel_expanded=set()
        negative_count=negative_nonempty_seed=negative_nonempty_expanded=0
        for row in rows:
            sid=row['sample_id'];text=row['source']['text'];old=candidates(text);new=inventory(text,vocabulary)
            reviewed=apply_review(new,[])
            assert len(reviewed)==len(new) and all(r['review_status']=='needs_review' for r in reviewed)
            assert all(text[r['span_start']:r['span_end']]==r['name'] for r in new)
            gs=fact_sets(row['entities'],row['relationships']);os=fact_sets(old,[])[0];ns=fact_sets(new,[])[0]
            gold.update((sid,*x) for x in gs[0]);seed.update((sid,*x) for x in os);expanded.update((sid,*x) for x in ns)
            rel_gold.update((sid,*x) for x in gs[1])
            for pool,target in [(old,rel_seed),(new,rel_expanded)]:
                by_id={r['id']:r for r in pool}
                for r in relation_candidates(text,pool,schema):
                    s,t=by_id[r['source_id']],by_id[r['target_id']]
                    target.add((sid,s['type'],normalize(s['name']),r['relation_type'],t['type'],normalize(t['name'])))
            if not row['entities'] and not row['relationships']:
                negative_count+=1;negative_nonempty_seed+=bool(old);negative_nonempty_expanded+=bool(new)
            details.append(dict(sample_id=sid,source_text_sha256=row['source']['text_sha256'],
                seed=old,expanded=reviewed,gold_count=len(gs[0]),seed_hits=len(gs[0]&os),expanded_hits=len(gs[0]&ns),
                confirmed_entities=[],candidate_deletions=0))
        jsonl(OUT/(name+'-candidates.jsonl'),details)
        reports[name]=dict(samples=len(rows),seed_candidate_metrics=scores(gold,seed),expanded_candidate_metrics=scores(gold,expanded),
            seed_relation_candidate_coverage=scores(rel_gold,rel_seed),expanded_relation_candidate_coverage=scores(rel_gold,rel_expanded),
            negative_samples=negative_count,negative_samples_with_seed_candidates=negative_nonempty_seed,
            negative_samples_with_expanded_candidates=negative_nonempty_expanded,candidate_deletions=0,
            all_unreviewed_candidates_preserved=True,confirmed_extraction_metrics=False)
    # Replay v11 omission decisions without deleting retained source candidates.
    records={r['sample_id']:r for r in read(ROOT/'.tools/kg-gold-rebuild-v3/development-v11-candidate-pilot/responses.jsonl')}
    deleted_gold=restored=0
    for row in prior:
        gs=fact_sets(row['entities'],[])[0];old=candidates(row['source']['text']);eligible=fact_sets(old,[])[0]
        trace=records[row['sample_id']]['artifact'].get('diagnostics',[])
        selected=next((t['resolved'] for t in trace if t['stage']=='candidate_inventory' and t['accepted']),[])
        chosen=fact_sets(selected,[])[0];missed=(gs&eligible)-chosen
        deleted_gold+=len(missed);restored+=len(missed & fact_sets(inventory(row['source']['text'],vocabulary),[])[0])
    reports['review_replay']=dict(v11_eligible_gold_candidates_omitted=deleted_gold,preserved_for_review=restored,
        restored_as_confirmed_entities=0,scope='candidate retention only, not final extraction recall')
    write(OUT/'report.json',reports)
    lines=['# 候选覆盖与无损保留审计','',
        f'训练 {len(training)} 个开发分块，构建 {len(vocabulary)} 个带来源术语；另选 24 个不同文档组开发探针。训练与两组探针文档组均隔离，未使用 validation/test。',
        '术语来自 AI 审核的开发标注，属于有监督训练；不是外部专家词表。以下为候选池指标，不能当成确认实体或最终抽取指标。','',
        '| 集合 | 原候选召回 | 扩展候选召回 | 原候选精度 | 扩展候选精度 |','|---|---:|---:|---:|---:|']
    for name in ('prior_pilot','isolated_probe'):
        a=reports[name]['seed_candidate_metrics'];b=reports[name]['expanded_candidate_metrics']
        lines.append(f"| {name} | {a['recall']:.2%} | {b['recall']:.2%} | {a['precision']:.2%} | {b['precision']:.2%} |")
    lines += ['', '误删重放：'+json.dumps(reports['review_replay'],ensure_ascii=False),
        '未作出明确审核决定的候选全部保留为 needs_review，不自动认定为正确实体。候选精度、负样本非空率和关系候选覆盖详见 report.json。',
        '此轮不调用模型、不写生产图谱。后续审核及关系判定必须同时报告候选保留率和语义质量。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(manifest=manifest,report=reports),ensure_ascii=False))

if __name__=='__main__':main()
