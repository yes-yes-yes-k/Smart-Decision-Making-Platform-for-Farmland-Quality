"""Current source, sampling and reference audit view; frozen labels stay intact."""
from collections import Counter
from pathlib import Path
import html
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,SOURCE,dump,readlines,budget_snapshot


def main():
    rows=readlines(OUT/'dataset-v1/samples.jsonl')
    docs={r['document_id']:r for r in readlines(OUT/'execution/source-pool-v2/documents.jsonl')}
    sources={r['document_id']:r for r in readlines(OUT/'dataset-v1/source-files.jsonl')}
    results={};reports={}
    release_issues={};release_reports={};released={};frozen_calibration={};frozen_report=None
    frozen_test={};frozen_test_report=None
    semantic_path=OUT/'semantic-quality-audit-v1/report.json'
    semantic=json.loads(semantic_path.read_text(encoding='utf-8')) if semantic_path.exists() else None
    semantic_hold=bool(semantic and semantic.get('release_hold'))
    if (OUT/'test-silver-v1/manifest.json').exists():
        frozen_test={r['sample_id']:r for r in readlines(OUT/'test-silver-v1/references.jsonl')}
        frozen_test_report=json.loads((OUT/'test-silver-v1/report.json').read_text(encoding='utf-8'))
    if (OUT/'calibration-silver-v1/manifest.json').exists():
        frozen_calibration={r['sample_id']:r for r in readlines(OUT/'calibration-silver-v1/references.jsonl')}
        frozen_report=json.loads((OUT/'calibration-silver-v1/report.json').read_text(encoding='utf-8'))
    for part in ['calibration','test']:
        folder=OUT/'references-v1'/part
        if (folder/'items.jsonl').exists():results.update({r['sample_id']:r for r in readlines(folder/'items.jsonl')})
        if (folder/'report.json').exists():reports[part]=json.loads((folder/'report.json').read_text(encoding='utf-8'))
        release=OUT/'reference-release-v1'/part
        if (release/'requires-adjudication.jsonl').exists():release_issues.update({r['sample_id']:r for r in readlines(release/'requires-adjudication.jsonl')})
        if (release/'report.json').exists():release_reports[part]=json.loads((release/'report.json').read_text(encoding='utf-8'))
        if (release/'references.jsonl').exists():released.update({r['sample_id']:r for r in readlines(release/'references.jsonl')})
    e=lambda s:html.escape(str(s),quote=True)
    summary=dict(status='inconclusive',membership='frozen',samples=len(rows),document_groups=len({r['isolation_group'] for r in rows}),
        partitions=dict(Counter(r['track']+':'+r['partition'] for r in rows)),raw_reference_reports=reports,release_gate_reports=release_reports,
        frozen_calibration_reference=frozen_report,
        frozen_final_reference=frozen_test_report,
        semantic_quality_audit=semantic,semantic_release_hold=semantic_hold,
        shared_budget=budget_snapshot(),source_pool=json.loads((OUT/'execution/source-pool-v2/report.json').read_text(encoding='utf-8')),
        source_kind_unknown_retained=True,parsing_quality_unknown_or_unreadable_retained=True,
        formal_backend_acceptance_not_run=True,expert_certified=False)
    dump(OUT/'dataset-v1/current-progress.json',summary)
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>重建评测集：来源、分区与参考</title><style>body{font:15px system-ui;margin:28px;max-width:1400px;color:#263246}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{border-top:1px solid #ccd3df;padding:12px}summary{cursor:pointer}.note{background:#fff3d3;padding:16px}</style><h1>重建评测集：来源、分区与参考</h1><p class="note">清单已冻结，标签正在建设。此页为生成时快照，不能把协议有效或AI银标就绪当作正式后端通过。保留未知与失败项；原文、题名和旧标签均未覆盖。文档类型/解析质量为窗口审计，未认证全文或专家金标。</p><pre>'+e(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>'
    if semantic_hold:
        page=page.replace('<h1>重建评测集：来源、分区与参考</h1>','<h1>重建评测集：来源、分区与参考</h1><p class="note"><strong>语义质量未通过，已停止调用与冻结。</strong>校准100条虽已保存冻结，但发现残词与类型错误，暂仅作开发诊断。所有标签和原始响应保留，下面的必要跨度检查不能解释为语义通过。<a href="../semantic-quality-audit-v1/review.html">查看逐条失败证据</a></p>')
    for r in rows:
        d=docs[r['document_id']];result=results.get(r['sample_id'],dict(status='not_started',reference_ready=False))
        if r['sample_id'] in frozen_calibration:
            result=dict(result,original_status=result['status'],status='frozen_calibration_AI_silver',reference_ready=True,
                release_reference=frozen_calibration[r['sample_id']])
        elif r['sample_id'] in frozen_test:
            result=dict(result,original_status=result['status'],status='frozen_final_AI_silver',reference_ready=True,
                release_reference=frozen_test[r['sample_id']])
        elif r['sample_id'] in release_issues:
            result=dict(result,status='release_gate_requires_adjudication',reference_ready=False,release_gate=release_issues[r['sample_id']]['release_gate'])
        elif r['sample_id'] in released:
            result=dict(result,original_status=result['status'],status='source_reviewed_necessary_evidence_checks_passed',
                reference_ready=True,release_reference=released[r['sample_id']])
        elif result.get('reference_ready'):
            result=dict(result,status='release_gate_pending',reference_ready=False)
        if semantic_hold:
            result=dict(result,mechanical_status=result['status'],mechanical_reference_ready=result.get('reference_ready',False),
                status='semantic_revalidation_required:'+result['status'],reference_ready=False,
                formal_reference_use_blocked=True)
        url=(SOURCE/sources[r['document_id']]['source_relative_path']).as_uri()+'#page='+str(r['page'])
        page+='<details><summary>'+e(' | '.join([r['sample_id'],r['track'],r['partition'],result['status']]))+'</summary>'
        page+='<p><a href="'+e(url)+'">打开原文件对应页</a></p><pre>'+e(json.dumps(dict(
            document_id=r['document_id'],isolation_group=r['isolation_group'],page=r['page'],position_quartile=r['position_quartile'],
            stratum=r['stratum'],selection_rule=r['selection_rule'],group_inclusion_probability=r.get('group_inclusion_probability'),
            weight_scope=r['weight_scope'],source_metadata=d),ensure_ascii=False,indent=2))+'</pre>'
        page+='<h3>冻结输入题名</h3><pre>'+e(r['document_title'])+'</pre><h3>冻结正文</h3><pre>'+e(r['text'])+'</pre><h3>参考构建状态</h3><pre>'+e(json.dumps(result,ensure_ascii=False,indent=2))+'</pre></details>'
    (OUT/'dataset-v1/review.html').write_text(page+'</html>',encoding='utf-8')
    print(json.dumps(dict(samples=len(rows),raw_ready=sum(r.get('reference_ready',False) for r in results.values()),release_gate_reports=release_reports,budget=summary['shared_budget']),ensure_ascii=False))


if __name__=='__main__':main()
