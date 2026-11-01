"""Development-only error decomposition and frozen paired recall experiment."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.score_kg_corpus import evaluate, prediction, fact_sets, normalize

BASE = ROOT/'artifacts/knowledge_platform/gold-rebuild-v3'
OUT = BASE/'development-recall-v8'

def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def jsonl(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def decompose(rows, records):
    by_id = {r['sample_id']:r for r in records}
    counts = Counter(); details = []; groups = {}
    for row in rows:
        if not row['evaluation_eligible']:
            counts['excluded_source_quality'] += 1
            continue
        record = by_id[row['sample_id']]
        pe, pr = prediction(record, row['source'])
        ge, gr, _ = fact_sets(row['entities'], row['relationships'])
        ep, rp, _ = fact_sets(pe, pr)
        bucket = 'request_failed' if record['state'] != 'completed' else (
            'empty_prediction_on_positive' if ge and not ep else
            'partial_entity_coverage' if ge-ep else 'entities_covered')
        counts[bucket] += 1
        missing_relations = Counter()
        for st,s,k,tt,t in gr-rp:
            missing_relations['missing_endpoint' if (st,s) not in ep or (tt,t) not in ep else 'endpoints_present_relation_missing'] += 1
        counts.update(missing_relations)
        text = normalize(row['source']['text'])
        absent = sum(name not in text for kind,name in ge-ep)
        counts['missed_entity_name_not_literal_in_chunk'] += absent
        item = dict(sample_id=row['sample_id'], index=row['index'], bucket=bucket,
            document_kind=row['source']['document_kind'], disposition=row['disposition'],
            missed_entities=sorted(ge-ep), extra_entities=sorted(ep-ge),
            missed_relations=sorted(gr-rp), relation_failure_modes=dict(missing_relations),
            missed_entity_name_not_literal_in_chunk=absent)
        details.append(item)
        for key in (row['source']['document_kind'], row['disposition']):
            group = groups.setdefault(key, Counter())
            group['samples'] += 1; group['entity_fn'] += len(ge-ep); group['relation_fn'] += len(gr-rp)
            group[bucket] += 1
    return dict(counts=dict(counts), groups=groups,
        limitation='Historical v6 has no raw-response trace: stage attribution is not established by final outputs. Nonliteral names may be aliases or document context, not necessarily model omissions.'), details

def prepare():
    OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists():
        raise ValueError('experiment already frozen')
    parent=json.loads((BASE/'codex-reference.manifest.json').read_text(encoding='utf-8'))
    if sha(BASE/'codex-reference.jsonl') != parent['reference_sha256']:
        raise ValueError('parent reference checksum mismatch')
    rows = [r for r in read(BASE/'codex-reference.jsonl') if r['source']['split']=='development']
    old = read(ROOT/'.tools/kg-gold-rebuild-v3/graphrag-v6-codex-final/responses.jsonl')
    diagnosis, details = decompose(rows, old)
    write(OUT/'baseline-decomposition.json', diagnosis)
    jsonl(OUT/'baseline-errors.jsonl', details)
    selected=[]
    for disposition in ('relations','entities_only','no_facts'):
        # Actual disposition vocabulary is retained; selection below uses facts directly.
        pool=[r for r in rows if r['evaluation_eligible'] and (
            ('relations' if r['relationships'] else 'entities_only' if r['entities'] else 'no_facts')==disposition)]
        selected.extend(sorted(pool,key=lambda r:hashlib.sha256(r['sample_id'].encode()).hexdigest())[:60])
    selected.sort(key=lambda r:r['sample_id'])
    jsonl(OUT/'reference.jsonl',selected)
    jsonl(OUT/'inputs.jsonl',[dict(sample_id=r['sample_id'],source=r['source']) for r in selected])
    write(OUT/'manifest.json',dict(reference_sha256=sha(OUT/'reference.jsonl'),
        inference_inputs_sha256=sha(OUT/'inputs.jsonl'), parent_reference_sha256=sha(BASE/'codex-reference.jsonl'),
        sample_count=len(selected), split='development', selection='up to 60 per relation/entity-only/negative stratum, SHA256 sample_id order',
        population_representative=False, validation_or_test_used=False,
        acceptance='Report precision, recall, F1, negative accuracy, failures and token cost for BOTH profiles; no production promotion.'))
    print(json.dumps(dict(samples=len(selected), diagnosis=diagnosis),ensure_ascii=False))

def compare():
    rows=read(OUT/'reference.jsonl'); manifest=json.loads((OUT/'manifest.json').read_text())
    assert sha(OUT/'reference.jsonl')==manifest['reference_sha256']
    assert all(r['source']['split']=='development' for r in rows)
    summary={}; all_records={}
    for profile in ('v6','v8-recall'):
        run=ROOT/'.tools/kg-gold-rebuild-v3'/('development-'+profile)
        records=read(run/'responses.jsonl')
        all_records[profile]=records
        config=json.loads((run/'config.json').read_text())
        assert config['source_inputs_sha256']==sha(OUT/'inputs.jsonl')
        assert config['reference_sha256']==manifest['reference_sha256']
        config_hash=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        assert all(r['config_hash']==config_hash for r in records)
        assert {r['sample_id'] for r in rows}=={r['sample_id'] for r in records}
        report,details=evaluate(rows,records)
        diagnosis,diagnostic_rows=decompose(rows,records)
        write(OUT/(profile+'-decomposition.json'),diagnosis)
        jsonl(OUT/(profile+'-decomposition-errors.jsonl'),diagnostic_rows)
        write(OUT/(profile+'-scores.json'), report)
        jsonl(OUT/(profile+'-errors.jsonl'),details)
        trace_counts=Counter()
        for record in records:
            trace=record.get('artifact',{}).get('diagnostics',record.get('diagnostics')) or []
            trace_counts['attempts']+=len(trace)
            trace_counts['rejected_attempts']+=sum(not t['accepted'] for t in trace)
            accepted=[t for t in trace if t['accepted']]
            if accepted and record['state']=='completed':
                raw=json.loads(accepted[-1]['content'])
                artifact=record['artifact']
                trace_counts['accepted_raw_entities']+=len(raw['entities'])
                trace_counts['final_entities']+=len(artifact['entities'])
                trace_counts['accepted_raw_relations']+=len(raw['relationships'])
                trace_counts['final_relations']+=len(artifact['relationships'])
                trace_counts['accepted_empty_outputs']+=not raw['entities'] and not raw['relationships']
                raw_es={(e['type'],normalize(e['name'])) for e in raw['entities']}
                final_es={(e['entity_type'],normalize(e['title'])) for e in artifact['entities']}
                raw_rs={(normalize(r['source']),r['relation_type'],normalize(r['target'])) for r in raw['relationships']}
                final_rs={(normalize(r['source']),r['relation_type'],normalize(r['target'])) for r in artifact['relationships']}
                trace_counts['entities_changed_or_lost_in_conversion']+=len(raw_es-final_es)
                trace_counts['relations_changed_or_lost_in_conversion']+=len(raw_rs-final_rs)
        summary[profile]=dict(metrics=report['all'],trace=dict(trace_counts),
            decomposition=diagnosis,
            failure_codes=dict(Counter(r.get('code') for r in records if r['state']=='failed')),
            total_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in records),
            progress=json.loads((run/'progress.json').read_text()))
    successful_ids=set.intersection(*({r['sample_id'] for r in records if r['state']=='completed'} for records in all_records.values()))
    paired_rows=[r for r in rows if r['sample_id'] in successful_ids]
    summary['both_successful_supplementary']={profile:evaluate(paired_rows,
        [r for r in records if r['sample_id'] in successful_ids])[0]['all']
        for profile,records in all_records.items()}
    write(OUT/'comparison.json',summary)
    a=summary['v6'];b=summary['v8-recall']
    lines=['# v6 / v8 开发集真实对照结果','',
        '固定 180 个开发集分块：关系、仅实体、无事实各 60 个。诊断性分层样本，不代表总体；验证集和测试集未使用。',
        '', '| 指标 | v6 同期重跑 | v8-recall |','|---|---:|---:|']
    for kind,label in [('entities','实体'),('relations','关系')]:
        for metric,name in [('precision','精度'),('recall','召回率'),('f1','F1')]:
            lines.append(f"| {label}{name} | {a['metrics'][kind][metric]:.2%} | {b['metrics'][kind][metric]:.2%} |")
    for key,label in [('failed_requests','失败请求'),('correct_negative_samples','60 个负样本中正确数')]:
        lines.append(f"| {label} | {a['metrics'][key]} | {b['metrics'][key]} |")
    lines.append(f"| 已报告 token | {a['total_tokens']} | {b['total_tokens']} |")
    lines.extend(['','## 阶段定位',''])
    for profile in ('v6','v8-recall'):
        item=summary[profile];t=item['trace'];d=item['decomposition']['counts']
        lines.append(f"- {profile}：正样本空输出 {d.get('empty_prediction_on_positive',0)}；校验拒绝尝试 {t['rejected_attempts']}；通过校验的实体 {t['accepted_raw_entities']} → 最终 {t['final_entities']}，关系 {t['accepted_raw_relations']} → 最终 {t['final_relations']}；规范化后转换丢失/变化实体 {t['entities_changed_or_lost_in_conversion']}、关系 {t['relations_changed_or_lost_in_conversion']}。")
    lines.extend(['','## 解释限制','',
        '主指标将失败请求计为漏抽；comparison.json 另附两版均成功的相同样本结果。原始响应及校验追踪保留在 .tools/kg-gold-rebuild-v3/development-*。',
        '参考答案为 Codex AI 审核，尚无独立专家认证；名称别名、文档上下文差异及参考遗漏仍会影响严格匹配。模型温度为 0 不等于远程服务确定性，当前为单轮配对实验，不宣称统计显著。',
        '证据仍是全分块引用，未解决精准短句；未修改参考答案、未调整生产默认、未发布图谱。Token 为服务端已报告值，连接失败可能另有未报告用量，实际费用未知。',
        '验证：阶段追踪与错误分解等 23 项测试通过；真实产物适配检查见两份 *-artifact-validation.json。该检查不等同无缓存重复调用一致性。'])
    lines.extend(['','## 本轮决策','',
        'v8 提高实体覆盖，但关系精度、召回率和 F1 均下降，因此拒绝替换生产默认。成功请求中转换前后规范化实体/关系均未丢失，问题重点位于模型输出、语义/名称匹配及失败校验，而非 GraphRAG 记录解析。',
        '共同成功的 173 个分块中，实体召回率 14.85% → 30.23%，关系召回率 11.64% → 10.96%，关系精度 37.78% → 24.62%。剔除网络失败后，关系质量下降趋势仍存在。',
        '建议下一轮在开发集实现独立的实体枚举和关系判定两阶段流程，要求显式原文支持，先控制 addresses 等关系误报；冻结实验版本后再考虑验证集。不要继续以泛化“尽量多抽”提示替代类型与证据约束。'])
    (OUT/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','compare'])
    args=p.parse_args()
    prepare() if args.action=='prepare' else compare()
