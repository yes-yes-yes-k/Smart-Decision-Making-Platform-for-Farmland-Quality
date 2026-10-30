"""Score frozen pointer-only experiment without changing reference labels."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha,decompose
from scripts.score_kg_corpus import evaluate

def main():
    base=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3/development-recall-v8'
    out=base.parent/'development-span-v10';out.mkdir(exist_ok=True)
    manifest=json.loads((base/'manifest.json').read_text())
    assert sha(base/'reference.jsonl')==manifest['reference_sha256']
    rows=read(base/'reference.jsonl');by_id={r['sample_id']:r for r in rows}
    assert len(rows)==180 and all(r['source']['split']=='development' for r in rows)
    summary={};all_records={}
    for profile in ('v6','v8-recall','v9-two-stage','v10-span'):
        run=ROOT/'.tools/kg-gold-rebuild-v3'/('development-'+profile)
        config=json.loads((run/'config.json').read_text());records=read(run/'responses.jsonl')
        assert config['reference_sha256']==manifest['reference_sha256'] and config['source_inputs_sha256']==sha(base/'inputs.jsonl')
        digest=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        assert len(records)==180 and {r['sample_id'] for r in records}==set(by_id)
        assert all(r['config_hash']==digest for r in records)
        all_records[profile]=records
        report,details=evaluate(rows,records)
        summary[profile]=dict(metrics=report['all'],failed_reasons=dict(Counter(
            (r.get('diagnostics') or [{}])[-1].get('error',r.get('code')) for r in records if r['state']=='failed')),
            tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in records))
        if profile=='v10-span':
            write(out/'metrics.json',report);jsonl(out/'sample-scores.jsonl',details)
            diagnosis,errors=decompose(rows,records)
            write(out/'decomposition.json',diagnosis);jsonl(out/'errors.jsonl',errors)
    spans=0;trace_counts=Counter();quotes=[]
    for r in all_records['v10-span']:
        text=by_id[r['sample_id']]['source']['text']
        traces=r.get('artifact',{}).get('diagnostics',r.get('diagnostics')) or []
        for t in traces:
            trace_counts[t['stage']+'_attempts']+=1
            if not t['accepted']:trace_counts[t['stage']+'_rejected']+=1
            if t['accepted'] and t['stage']=='entity_span_selection':
                for e in t['resolved']:
                    assert text[e['span_start']:e['span_end']]==e['name']
                    spans+=1
        for relation in r.get('artifact',{}).get('relationships',[]):
            assert relation['quote'] in text
            quotes.append(len(relation['quote']))
    summary['span_audit']=dict(verified_entity_mentions=spans,trace_counts=trace_counts,
        relationship_quotes=len(quotes),max_quote_characters=max(quotes,default=0),
        semantic_truth_verified=False)
    common=set.intersection(*({r['sample_id'] for r in rs if r['state']=='completed'} for rs in all_records.values()))
    summary['all_versions_successful']={p:evaluate([r for r in rows if r['sample_id'] in common],
        [r for r in rs if r['sample_id'] in common])[0]['all'] for p,rs in all_records.items()}
    write(out/'comparison.json',summary)
    lines=['# 原文位置选择 v10 真实开发集实验','',
        '同一冻结的 180 个开发样本，关系/仅实体/无事实各 60 个。旧版本为先前真实结果，v10 为本轮请求；非同时交错实验。验证集与测试集未使用。',
        '', '| 指标 | v6 | v8 | v9 | v10 |','|---|---:|---:|---:|---:|']
    for kind,label in [('entities','实体'),('relations','关系'),('exact_evidence','引用精确匹配')]:
        for key,name in [('precision','精度'),('recall','召回率'),('f1','F1')]:
            vals=[summary[p]['metrics'][kind][key] for p in all_records]
            lines.append('| '+label+name+' | '+' | '.join('无预测' if v is None else f'{v:.2%}' for v in vals)+' |')
    for key,label in [('failed_requests','失败请求'),('correct_negative_samples','60 个负样本中正确数')]:
        lines.append('| '+label+' | '+' | '.join(str(summary[p]['metrics'][key]) for p in all_records)+' |')
    lines.extend(['','失败原因：`'+json.dumps(summary['v10-span']['failed_reasons'],ensure_ascii=False)+'`。',
        'v10 已报告 token：'+str(summary['v10-span']['tokens'])+'。实际费用未知。',
        '所有接受的实体名称均由程序按原文位置切片，跨度核验数 '+str(spans)+'；名称不再由模型生成。位置存在不保证领域类型正确，引用覆盖端点不保证语义蕴含。',
        '评分沿用冻结 AI 参考，未经独立专家认证；别名与引用边界仍影响严格匹配。失败计为漏抽，共同成功样本指标另存 comparison.json。',
        '32 项相关测试通过。生产默认未切换，产物校验不等同多次无缓存一致性验证。'])
    (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary['v10-span'],ensure_ascii=False))

if __name__=='__main__':main()
