"""Offline, truthful status/report artifacts; never synthesizes missing model results."""
from pathlib import Path
from collections import Counter
import html,json,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_kg_acceptance_v1 import OUT,verify_freeze,shared_budget_path
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_budget import Budget
from framework.knowledge_graph.acceptance_metrics import threshold_proposal
from framework.knowledge_graph.acceptance_data import assert_isolation,digest

def load(path,default=None):return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def main():
    verify_freeze();selection=read(OUT/'pool/selection.jsonl');assert_isolation(selection)
    manifest=load(OUT/'pool/selection-manifest.json');audit=load(OUT/'pool/isolation-audit.json')
    stability=load(OUT/'stability/report.json',dict(original_reference_unchanged=True,relabel_attempted=0,relabel_protocol_complete=0,adjudicated=0,unresolved=100))
    qa=load(OUT/'qa/packet-status.json');budget=Budget(shared_budget_path()).summary();policy=load(OUT/'remote-policy.json')
    qa_actual=load(OUT/'qa/reference-status.json',{}).get('validated_questions',0)
    labeled={p:load(OUT/p/'reference-status.json',{}).get('adjudicated',0) for p in ('calibration','test')}
    report=dict(status='inconclusive',date='2026-10-28',purpose='internal release acceptance, AI silver only',
        model=load(OUT/'run-config.json')['model'],run_directory=OUT.name,
        development_frozen=True,original_reference_unchanged=stability['original_reference_unchanged'],
        sampled_chunks=len(selection),selected_document_groups=manifest['selected_document_groups'],counts=manifest['counts'],
        isolation_audit=audit,stability=dict(attempted=stability['relabel_attempted'],protocol_complete=stability['relabel_protocol_complete'],adjudicated=stability['adjudicated'],unresolved=stability['unresolved']),
        actual_reference_samples=labeled,qa=dict(planned=100,prepared_jobs=len(read(OUT/'qa/generation-jobs.jsonl')),validated=qa_actual),
        calibration_completed=False,thresholds_confirmed=False,final_test_executed=False,final_acceptance='inconclusive',
        remote_calls_suspended=bool(policy and policy.get('suspended_by_user')),budget=budget,background_requests=budget['inflight'],
        blockers=['cloud calls suspended by user; last recorded provider response HTTP 402','stability phase cannot reserve further work within its remaining cap',
            'source arbitrations and new reference labels incomplete','QA generation and independent source review not run','isolated frozen embeddings and candidate-generated graph snapshot not yet built',
            'no real calibration results for threshold setting','user confirmation of calibrated thresholds still required'],
        expert_certified=False,production_approved=False,certified_training_data_blindness=False)
    write(OUT/'progress.json',report)
    proposal=threshold_proposal(dict(status='not_run',supports={},reason='provider unavailable; no independently adjudicated new calibration reference'))
    proposal.update(actionable_for_approval=False,notes=proposal['notes']+['Numbers are illustrative discussion anchors only, not a calibration-backed recommendation. Wait for actual pilot before asking for approval.'])
    write(OUT/'threshold-proposal.json',proposal)
    write(OUT/'final-acceptance-report.json',dict(status='inconclusive',executed=False,reason='no confirmed thresholds or complete references',actual_model_results=None,expert_certified=False,production_approved=False))
    checks=dict(development_hashes_verified=True,selection_hash_verified=sha(OUT/'pool/selection.jsonl')==manifest['selection_sha256'],
        corpus_hash_verified=sha(OUT/'pool/corpus-snapshot.jsonl')==manifest['corpus_sha256'],
        same_document_group_isolated=True,selected_near_duplicate_audit_passed=audit['status']=='pass',
        source_inputs_match_selection=True,qa_job_quotas_verified=True,cloud_suspended=report['remote_calls_suspended'],inflight_requests=budget['inflight'])
    for part in ('calibration','test'):
        sources=read(OUT/part/'samples.jsonl');inputs=read(OUT/part/'inputs.jsonl')
        expected=[r for r in selection if r['partition']==part]
        assert sources==expected and len(sources)==len(inputs)
        for s,v in zip(sources,inputs):
            assert s['sample_id']==v['sample_id'] and v['blocks'][0]['text']==s['text'] and v['blocks'][0]['text_sha256']==s['text_sha256']
            assert all(b['text_sha256']==digest(b['text']) for b in v['blocks'])
    jobs=read(OUT/'qa/generation-jobs.jsonl');source_lookup={r['sample_id']:r for r in selection}
    assert len(jobs)==100 and len({j['id'] for j in jobs})==100
    assert Counter(j['partition'] for j in jobs)=={'calibration':20,'test':80}
    assert Counter(j['kind'] for j in jobs)=={'answerable':60,'insufficient':20,'false_premise':10,'beyond_evidence':10}
    assert sum(j['multihop'] for j in jobs)==20
    assert all(source_lookup[sid]['partition']==j['partition'] for j in jobs for sid in j['source_ids'])
    assert all(v for k,v in checks.items() if k!='inflight_requests') and checks['inflight_requests']==0
    write(OUT/'offline-verification.json',dict(status='pass',checks=checks,meaning='offline contract/data checks only; not acceptance quality'))
    artifacts=[OUT/'development-freeze.json',OUT/'run-config.json',OUT/'pool/selection.jsonl',OUT/'pool/corpus-snapshot.jsonl',OUT/'pool/isolation-audit.json',OUT/'qa/generation-jobs.jsonl']
    code=[ROOT/'framework/knowledge_graph'/name for name in ('acceptance_data.py','acceptance_metrics.py','acceptance_retrieval.py','acceptance_remote.py')]
    write(OUT/'implementation-manifest.json',dict(files=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in artifacts+code],
        change_policy='preserve existing development reference; new source artifacts immutable; code revisions separately recorded',status='offline_prepared_not_acceptance_approved'))
    e=lambda x:html.escape(str(x),quote=True)
    cards=[]
    comparison_path=OUT/'stability/comparison.jsonl'
    for c in read(comparison_path) if comparison_path.exists() else []:
        cards.append(f"<tr><td>{c['index']+1}</td><td>{e(c['sample_id'])}</td><td>{'完整' if c['relabel_structurally_complete'] else '失败或部分'}</td><td>{e(c['errors'])}</td><td>未裁决</td></tr>")
    samples=[]
    for r in selection:
        samples.append(f"<details><summary>{e(r['track'])} / {e(r['partition'])} · 文档{r['document_id']} · {e(r['sample_id'])}</summary><p>{e(r['document_title'])}</p><pre>{e(r['text'])}</pre></details>")
    page="""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>内部验收基准 v1 · 离线进展</title><style>body{font:16px/1.6 system-ui;max-width:1180px;margin:30px auto;padding:0 18px;color:#193045;background:#f5f7fa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e9eff5;padding:12px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd5df;padding:7px;text-align:left}details{background:white;padding:10px;margin:10px 0;border:1px solid #ccd5df}summary{cursor:pointer}.status{background:#fff0cf;padding:18px}</style><h1>内部版本验收基准 v1</h1><p class='status'>状态：证据不足，尚未验收。云端已按用户要求暂停；以下是离线准备与已有失败记录，不是正式质量结果。</p>"""
    inspection=ROOT/'artifacts/knowledge_platform/acceptance-v1/review-inspection-20261028/index.html'
    if inspection.exists():
        from os.path import relpath
        link=relpath(inspection,OUT).replace('\\','/')
        page+=f"<p><a href='{e(link)}'>查看来源、取样与旧模型复标错误的检查报告（已发现文档尾部抽样缺口）</a></p>"
    page+=f"<h2>完成范围与待办</h2><pre>{e(json.dumps(report,ensure_ascii=False,indent=2))}</pre><h2>100条盲复标记录</h2><p>{stability['relabel_protocol_complete']}条完整通过协议校验，不能当100条完整复标成功；仲裁完成{stability['adjudicated']}条。原始候选清单一致性不能当准确率。</p><table><tr><th>序号</th><th>样本</th><th>协议</th><th>错误</th><th>裁决</th></tr>{''.join(cards)}</table><h2>500条来源快照</h2><p>代表性300、挑战200。这里只展示原文，尚无新银标。源文本全部转义；无外部资源。</p>{''.join(samples)}</html>"
    (OUT/'review.html').write_text(page,encoding='utf-8')
    print(json.dumps(dict(status=report['status'],samples=len(selection),qa_jobs=len(jobs),qa_validated=qa_actual,cloud_suspended=report['remote_calls_suspended'],inflight=budget['inflight']),ensure_ascii=False))

if __name__=='__main__':main()
