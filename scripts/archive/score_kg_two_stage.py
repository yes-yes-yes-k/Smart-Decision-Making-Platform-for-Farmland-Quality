"""Compare frozen development v9 predictions with prior v6/v8; never mutate references."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha,decompose
from scripts.score_kg_corpus import evaluate,normalize


def main():
    base=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3/development-recall-v8'
    out=base.parent/'development-two-stage-v9';out.mkdir(exist_ok=True)
    manifest=json.loads((base/'manifest.json').read_text())
    assert sha(base/'reference.jsonl')==manifest['reference_sha256']
    rows=read(base/'reference.jsonl')
    assert len(rows)==180 and all(r['source']['split']=='development' for r in rows)
    all_records={};summary={}
    for profile in ('v6','v8-recall','v9-two-stage'):
        run=ROOT/'.tools/kg-gold-rebuild-v3'/('development-'+profile)
        config=json.loads((run/'config.json').read_text())
        assert config['reference_sha256']==manifest['reference_sha256']
        assert config['source_inputs_sha256']==sha(base/'inputs.jsonl')
        config_hash=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        records=read(run/'responses.jsonl');all_records[profile]=records
        assert all(r['config_hash']==config_hash for r in records)
        assert {r['sample_id'] for r in rows}=={r['sample_id'] for r in records}
        metrics,details=evaluate(rows,records)
        diagnosis,errors=decompose(rows,records)
        write(out/(profile+'-metrics.json'),metrics)
        jsonl(out/(profile+'-errors.jsonl'),errors)
        summary[profile]=dict(metrics=metrics['all'],decomposition=diagnosis,
            failures=dict(Counter(r.get('code') for r in records if r['state']=='failed')),
            validation_failure_details=dict(Counter((r.get('diagnostics') or [{}])[-1].get('error',r.get('code'))
                for r in records if r['state']=='failed')),
            total_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in records))
    traces=Counter();quotes=[]
    for record in all_records['v9-two-stage']:
        trace=record.get('artifact',{}).get('diagnostics',record.get('diagnostics')) or []
        for t in trace:
            traces[t['stage']+'_attempts']+=1
            if not t['accepted']:traces[t['stage']+'_rejected']+=1
        if record['state']!='completed':continue
        artifact=record['artifact'];accepted=[t for t in trace if t['accepted']]
        raw=json.loads(accepted[-1]['content'])
        raw_es={(e['type'],normalize(e['name'])) for e in raw['entities']}
        final_es={(e['entity_type'],normalize(e['title'])) for e in artifact['entities']}
        traces['entities_changed_in_conversion']+=len(raw_es-final_es)
        for r in artifact['relationships']:
            quotes.append(len(r['quote']))
            assert r['source'].casefold() in r['quote'].casefold() and r['target'].casefold() in r['quote'].casefold()
    summary['v9_diagnostics']=dict(traces=traces,quotes=len(quotes),max_quote_characters=max(quotes,default=0),
        mean_quote_characters=sum(quotes)/len(quotes) if quotes else None,
        lexical_validation_is_not_semantic_certification=True)
    common=set.intersection(*({r['sample_id'] for r in records if r['state']=='completed'} for records in all_records.values()))
    summary['all_three_successful']={p:evaluate([r for r in rows if r['sample_id'] in common],
        [r for r in records if r['sample_id'] in common])[0]['all'] for p,records in all_records.items()}
    write(out/'comparison.json',summary)
    lines=['# 两阶段 v9 开发集真实实验','',
        '使用同一冻结的 180 个开发集分块；v6/v8 为前一轮已完成真实结果，v9 为本轮新请求。并非同时随机交错的实验，存在远程服务波动。',
        '样本为三类各 60 个的诊断性分层集，不代表全库；金标仍为 AI 审核参考。验证集和测试集未使用。','',
        '| 指标 | v6 | v8-recall | v9-two-stage |','|---|---:|---:|---:|']
    for kind,label in [('entities','实体'),('relations','关系'),('exact_evidence','精确证据')]:
        for metric,name in [('precision','精度'),('recall','召回'),('f1','F1')]:
            vals=[f"{summary[p]['metrics'][kind][metric]:.2%}" if summary[p]['metrics'][kind][metric] is not None else '无预测' for p in all_records]
            lines.append('| '+label+name+' | '+' | '.join(vals)+' |')
    for key,label in [('failed_requests','失败数'),('correct_negative_samples','60 个负样本中正确数')]:
        lines.append('| '+label+' | '+' | '.join(str(summary[p]['metrics'][key]) for p in all_records)+' |')
    lines.extend(['','两阶段均保留最多两次修复；第二阶段失败时整个请求计为失败，第一阶段输出保留在追踪中但不冒充成功结果。',
        '关系引用必须为原文连续子串、同时出现两个端点、最长 800 字符；这只验证来源和词面，不保证语义正确或达到最短引用。',
        'v9 要求实体名称逐字出现，可能加重规范名/别名不匹配，严格评分未做答案导向的别名修正。精确证据按参考引用全文哈希匹配，其他同样正确的引用边界也可能记为未匹配。',
        '生产默认保持 v6。产物结构和来源校验不等于无缓存重复调用一致性通过。',
        '', 'v9 已报告 token：'+str(summary['v9-two-stage']['total_tokens'])+'；实际费用未知，失败请求可能有未报告用量。'])
    (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({p:summary[p] for p in ('v9-two-stage','v9_diagnostics')},ensure_ascii=False))

if __name__=='__main__':main()
