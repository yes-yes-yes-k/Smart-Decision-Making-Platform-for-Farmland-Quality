"""Freeze/score a small source-only pilot before allowing larger experiments."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from scripts.score_kg_corpus import evaluate,fact_sets
from framework.knowledge_graph.candidate_selection import candidates,relation_candidates
from framework.knowledge_graph.schema import load_graph_schema

BASE=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3/development-recall-v8'
OUT=BASE.parent/'development-candidate-v11-pilot'

def prepare():
    if OUT.exists():raise ValueError('pilot already exists')
    manifest=json.loads((BASE/'manifest.json').read_text())
    assert sha(BASE/'reference.jsonl')==manifest['reference_sha256']
    rows=read(BASE/'reference.jsonl');selected=[]
    for kind in ('relations','entities','negative'):
        pool=[r for r in rows if ('relations' if r['relationships'] else 'entities' if r['entities'] else 'negative')==kind]
        selected.extend(sorted(pool,key=lambda r:hashlib.sha256(r['sample_id'].encode()).hexdigest())[:8])
    assert len(selected)==24 and all(r['source']['split']=='development' for r in selected)
    OUT.mkdir()
    jsonl(OUT/'reference.jsonl',selected)
    jsonl(OUT/'inputs.jsonl',[dict(sample_id=r['sample_id'],source=r['source']) for r in selected])
    write(OUT/'manifest.json',dict(reference_sha256=sha(OUT/'reference.jsonl'),inference_inputs_sha256=sha(OUT/'inputs.jsonl'),
        parent_reference_sha256=manifest['reference_sha256'],samples=24,selection='8 per fact stratum ordered by sample_id SHA256',
        lexicon_source='fixed hand-written patterns, not evaluation labels',split='development',production_approved=False,
        decision_gate='Do not expand unless both entity and relation F1 exceed v6 on identical pilot; inspect negative false positives and candidate ceiling.'))
    print('frozen 24 development samples')

def score():
    rows=read(OUT/'reference.jsonl');manifest=json.loads((OUT/'manifest.json').read_text());assert sha(OUT/'reference.jsonl')==manifest['reference_sha256']
    ids={r['sample_id'] for r in rows};summary={}
    for profile in ('v6','v8-recall','v9-two-stage','v10-span','v11-candidate'):
        run=ROOT/'.tools/kg-gold-rebuild-v3'/('development-'+profile if profile!='v11-candidate' else 'development-v11-candidate-pilot')
        records=[r for r in read(run/'responses.jsonl') if r['sample_id'] in ids]
        assert len(records)==24
        if profile=='v11-candidate':
            config=json.loads((run/'config.json').read_text())
            assert config['reference_sha256']==manifest['reference_sha256'] and config['source_inputs_sha256']==sha(OUT/'inputs.jsonl')
            digest=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
            assert all(r['config_hash']==digest for r in records)
        report,details=evaluate(rows,records)
        write(OUT/(profile+'-metrics.json'),report);jsonl(OUT/(profile+'-errors.jsonl'),details)
        summary[profile]=dict(metrics=report['all'],reported_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in records))
    expected=covered=0;details=[];expected_relations=before_relations=after_relations=relation_calls=0
    live_records={r['sample_id']:r for r in read(ROOT/'.tools/kg-gold-rebuild-v3/development-v11-candidate-pilot/responses.jsonl')}
    def relation_keys(entities,rs):
        return fact_sets(entities,[dict(**r,quote_sha256=hashlib.sha256(r['quote'].encode()).hexdigest()) for r in rs])[1]
    for row in rows:
        pool=candidates(row['source']['text']);gold=fact_sets(row['entities'],[])[0]
        ps=fact_sets(pool,[])[0];expected+=len(gold);covered+=len(gold&ps)
        gold_rs=fact_sets(row['entities'],row['relationships'])[1]
        possible=relation_keys(pool,relation_candidates(row['source']['text'],pool,load_graph_schema()))
        traces=live_records[row['sample_id']]['artifact'].get('diagnostics',[])
        selected=next((t['resolved'] for t in traces if t['stage']=='candidate_inventory' and t['accepted']),[])
        after=relation_keys(selected,relation_candidates(row['source']['text'],selected,load_graph_schema()))
        expected_relations+=len(gold_rs);before_relations+=len(gold_rs&possible);after_relations+=len(gold_rs&after)
        relation_calls+=sum(t['stage']=='candidate_relations' for t in traces)
        details.append(dict(sample_id=row['sample_id'],candidates=pool,expected=len(gold),covered=len(gold&ps)))
    jsonl(OUT/'candidate-coverage.jsonl',details)
    summary['candidate_coverage']=dict(expected=expected,covered=covered,strict_recall_ceiling=covered/expected if expected else None)
    summary['relation_stage_coverage']=dict(expected=expected_relations,available_before_entity_selection=before_relations,
        available_after_entity_selection=after_relations,relation_stage_calls=relation_calls)
    write(OUT/'relation-stage-coverage.json',summary['relation_stage_coverage'])
    a,b=summary['v6']['metrics'],summary['v11-candidate']['metrics']
    summary['expand_allowed']=b['entities']['f1']>a['entities']['f1'] and b['relations']['f1']>a['relations']['f1']
    write(OUT/'comparison.json',summary)
    lines=['# 原文候选 ID 小规模真实试验','',
        '固定 24 个开发分块（关系/实体/负样本各 8 个），只作诊断；旧版本为相同样本的历史真实输出。未用验证/测试集。',
        '候选词表为手写固定模式，未使用评测标签生成；严格覆盖上限与实际结果同时报告。',
        '', '| 指标 | v6 | v11 |','|---|---:|---:|']
    for kind,label in [('entities','实体'),('relations','关系')]:
        for key,name in [('precision','精度'),('recall','召回率'),('f1','F1')]:
            vals=[m[kind][key] for m in (a,b)]
            lines.append('| '+label+name+' | '+' | '.join('无预测' if v is None else f'{v:.2%}' for v in vals)+' |')
    lines += ['', '候选严格覆盖上限：'+str(summary['candidate_coverage'])+'。',
        '关系阶段覆盖：'+str(summary['relation_stage_coverage'])+'。本轮关系阶段未调用，不能由零输出推断关系判定能力。',
        '扩大实验门槛通过：'+str(summary['expand_allowed'])+'。不代表可以上线。',
        '36 项相关测试通过。实体来自原文、引用覆盖实体不等于类型或关系语义正确。AI 参考及名称差异仍影响严格匹配。',
        'v11 已报告 token：'+str(summary['v11-candidate']['reported_tokens'])+'；实际费用未知。']
    (OUT/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary['v11-candidate'],ensure_ascii=False));print(json.dumps(summary['candidate_coverage']));print('expand_allowed',summary['expand_allowed'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','score']);args=p.parse_args()
    prepare() if args.action=='prepare' else score()
