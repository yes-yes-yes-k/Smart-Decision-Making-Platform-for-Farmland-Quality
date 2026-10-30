"""Current read-only progress, all frozen run dependencies and budget stop state."""
from collections import Counter
from pathlib import Path
import html
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,readlines,budget_snapshot,verify_history
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from scripts.report_kg_benchmark_pilot import signature


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    execution=OUT/'execution'
    keys={r['sample_id']:r for r in readlines(OUT/'protocol-r5/private-control-keys.jsonl')}
    reviews=[]
    for p in (execution/'pilot-r5-reference-review/proposals').glob('*.json'):
        r=load(p);sid=r['id'].removeprefix('review:');v=r.get('protocol',{})
        reviews.append(dict(sample_id=sid,state=r['state'],reference_ready=v.get('reference_ready',False),
            control=sid in keys,inventory_exact=signature(v.get('materialized_proposal',{}))==signature(keys[sid]['expected']) if sid in keys else None,
            masks_applicable=all(m['status']=='applicable' for m in v.get('source_reference_masks',[])) if v else False,
            unresolved=v.get('unresolved'),protocol_errors=v.get('errors')))
    controls=[r for r in reviews if r['control']]
    changes=[];checked=0
    for path in execution.rglob('run-config.json'):
        for file in load(path).get('files',[]):
            checked+=1
            if sha256_file(ROOT/file['path'])!=file['sha256']:
                changes.append(dict(run=str(path.relative_to(OUT)),path=file['path']))
    replay=load(execution/'pilot-r4-reference-replay-v2/report.json')
    strict=[]
    for p in (execution/'reference-schema-validation-r1/proposals').glob('*.json'):
        r=load(p);strict.append(dict(id=r['id'],state=r['state'],reference_ready=r.get('protocol',{}).get('reference_ready',False)))
    prior=load(execution/'source-review-r1/report.json')
    budget_stop=load(execution/'stability-budget-stop.json')
    auth_path=execution/'project-budget-authorization-v2.json'
    authorization=load(auth_path if auth_path.exists() else execution/'project-budget-authorization.json')
    comparison=load(execution/'full-index-three-stage-comparison/compiled-report.json')
    metadata=[]
    for name in ['source-metadata-review-v1','source-metadata-review-v2','source-metadata-review-v3','source-metadata-review-v4-pilot','source-metadata-review-v5']:
        folder=execution/name
        rows=[load(p) for p in (folder/'proposals').glob('*.json')]
        state_path=folder/'run-state.json'
        live_path=folder/'progress.json'
        state=load(state_path) if state_path.exists() else load(live_path) if live_path.exists() else {}
        metadata.append(dict(run=name,saved=len(rows),states=dict(Counter(r['state'] for r in rows)),
            identity_statuses=dict(Counter(r.get('protocol',{}).get('metadata',{}).get('identity_status','unresolved') for r in rows)),
            runner_active=state.get('runner_active',False)))
    # Profile only known returned usage; retry reservations remain separately
    # charged in the ledger and are never omitted from budget totals.
    profile={}
    for name in ['pilot-r4','pilot-r4-adjudication','pilot-r4-reference-review','pilot-r5','pilot-r5-reference-review']:
        rows=[load(p) for p in (execution/name/'proposals').glob('*.json')]
        sources=[r for r in rows if 'rebuild-v2:' in r['id'] and r.get('usage')]
        profile[name]=dict(source_responses_with_usage=len(sources),
            returned_tokens=sum(r['usage']['total_tokens'] for r in sources),
            returned_tokens_mean=(sum(r['usage']['total_tokens'] for r in sources)/len(sources)) if sources else None)
    running=any(r['runner_active'] for r in metadata)
    report=dict(status='inconclusive',date='2026-10-29',stage='source_metadata_review' if running else 'metadata_quality_review_checkpoint',
        api_available_confirmed=True,model='deepseek-ai/DeepSeek-V4.1-Flash',
        previous_ten_source_reference_drafts_ready=replay['real_source_drafts_ready'],
        previous_trial_not_formally_accepted=True,
        compact_three_stage=dict(reference_stage_count=3,all_original_characters_selectable=True,
            adopt_for_bulk=False,quality_status='fail_control_reference_comparison',
            primary_responses=len(list((execution/'pilot-r5/proposals').glob('*.json'))),
            control_reviews=len(controls),control_reference_ready=sum(r['reference_ready'] for r in controls),
            control_inventory_exact=sum(r['inventory_exact'] for r in controls),
            control_masks_applicable=sum(r['masks_applicable'] for r in controls),
            real_source_reviews_expected=2,real_source_reviews_ready=sum(r['reference_ready'] for r in reviews if not r['control'])),
        strict_schema_interface_controls=strict,
        source_identity_refinement=prior,
        metadata_preparation=load(OUT/'metadata-review-preparation/manifest.json')
            if (OUT/'metadata-review-preparation/manifest.json').exists() else None,
        historical_files_unchanged=verify_history(),run_dependencies_checked=checked,changed_dependencies=changes,
        legacy_ledger_prefix_retained=True,shared_budget=budget_snapshot(),historical_budget_stop=budget_stop,
        budget_authorization=authorization,full_index_three_stage=comparison,metadata_review=metadata,
        annotation_workflow=load(OUT/'annotation-workflow-v1.json'),
        known_usage_profile=profile,handbook_frozen_for_formal_reference=False,
        final_dataset_frozen=False,calibration_backend_runs=0,final_acceptance_runs=0,
        numeric_thresholds_confirmed=False,expert_certified=False,same_model_error_correlation=True,
        background_running=running,automatic_resume=False,
        next_comparison=dict(preflight='full-index-three-stage-comparison/preflight.json',
            prepared_not_executed=False,control_requests=14,real_source_requests=2,
            existing_A_B_reused=True,phase_budget_increase_requires_user_approval=False),
        pending=['verified_bibliographic_language_quality_metadata',
            'resolve_or_quarantine_remaining_duplicate_candidates',
            'freeze_document_isolated_calibration_and_final_manifests',
            'new_reference_labels_and_live_backend_calibration','user_confirmed_numeric_acceptance_thresholds'])
    if (OUT/'dataset-v1/manifest.json').exists():
        report.update(stage='frozen_membership_reference_construction',final_membership_frozen=True,
            final_dataset_reference_ready=False,source_pool=load(execution/'source-pool-v2/report.json'),
            frozen_sampling=load(OUT/'dataset-v1/sampling-report.json'),
            pending=['complete_reference_annotations_and_resolve_source_review_disagreements',
                'validate_relation_coverage_and_fixed_reference_masks','live_backend_calibration','user_confirmed_numeric_acceptance_thresholds'])
        if (OUT/'references-v1/calibration/report.json').exists():report['raw_calibration_reference_progress']=load(OUT/'references-v1/calibration/report.json')
        if (OUT/'reference-release-v1/calibration/report.json').exists():report['calibration_release_gate']=load(OUT/'reference-release-v1/calibration/report.json')
        if (OUT/'calibration-silver-v1/manifest.json').exists():report['frozen_calibration_reference']=load(OUT/'calibration-silver-v1/report.json')
        if (OUT/'references-v1/test/report.json').exists():report['final_reference_construction']=load(OUT/'references-v1/test/report.json')
        state_path=OUT/'references-v1/test/run-state.json'
        if state_path.exists():
            report['final_reference_runner_checkpoint']=load(state_path)
            report['background_running']=load(state_path).get('active',False)
            report['runner_checkpoint_is_not_live_process_certification']=True
        if (OUT/'test-silver-v1/manifest.json').exists():
            report.update(stage='frozen_AI_silver_references_pending_backend_calibration',
                final_dataset_reference_ready=True,frozen_final_reference=load(OUT/'test-silver-v1/report.json'),
                pending=['inspect_type_coverage_and_AI_reference_limitations','live_backend_calibration',
                    'user_confirmed_numeric_acceptance_thresholds'])
    semantic_path=OUT/'semantic-quality-audit-v1/report.json'
    semantic=load(semantic_path) if semantic_path.exists() else None
    if semantic and semantic.get('release_hold'):
        report.update(stage='semantic_reference_quality_hold',reference_quality_status='fail',
            semantic_quality_audit=semantic,final_dataset_reference_ready=False,
            frozen_calibration_use='development_diagnostic_only_pending_semantic_resolution',
            background_running=False,pending=['source_semantic_and_boundary_audit_of_current_drafts',
                'validate_versioned_dual_quote_and_coordinate_contract_on_fresh_controls',
                'resolve_correlated_semantic_errors_before_any_further_batch_or_freeze'])
    dump(execution/'progress.json',report)
    e=lambda x:html.escape(str(x),quote=True)
    links=[('旧来源审计','../audit/review.html'),('来源身份复核','source-review-r1/review.html'),
        ('四阶段试标与原文','pilot-r4/review.html'),('新三阶段试标与原文','pilot-r5/review.html'),
        ('10条AI银标草案','pilot-r4-reference-replay-v2/source-reference-drafts.jsonl'),
        ('预算预留停止详情','stability-budget-stop.json'),('原四阶段预算可行性','budget-feasibility-r1.json'),
        ('全量索引三阶段对照结果','full-index-three-stage-comparison/compiled-report.json'),
        ('阶段自动调整授权与项目硬上限','project-budget-authorization.json'),
        ('552份元数据审查包清单','../metadata-review-preparation/manifest.json')]
    links.append(('来源元数据与冲突逐项审核','metadata-audit/review.html'))
    if (OUT/'dataset-v1/manifest.json').exists():links.insert(0,('新500条：来源、隔离分区、原文与参考状态','../dataset-v1/review.html'))
    if authorization['total_tokens']==20000000:links.insert(1,('用户明确批准的2000万总额授权','project-budget-authorization-v2.json'))
    if semantic:links.insert(0,('语义质量拦截：逐条原文与失败证据','../semantic-quality-audit-v1/review.html'))
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>抽取基准重建当前进度</title><style>body{font:15px system-ui;margin:30px;max-width:1300px;color:#253249}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:8px 0}.stop{padding:16px;background:#fff3d3;border:1px solid #d4b56a}</style><h1>GraphRAG抽取基准重建：当前进度</h1><p class="stop">API已恢复。用户授权阶段额度自动调整，项目总上限仍为1000万token或5000次请求，并发最多2。全量字符索引三阶段小样本对照已完成：14/14控制参考一致，2/2文献参考就绪；压缩索引方案继续弃用。当前正在核查来源元数据，下面是生成页面时的快照。参考构建流程验证不等于后端质量通过，最终数值验收仍需用户确认门槛。</p><ul>'
    if not running:
        page=page.replace('当前正在核查来源元数据，下面是生成页面时的快照。','来源批处理已因系统性类型/质量判定异常停止，结果及未知用量预留均已保存；正在核查字段规则，未自动恢复批量调用。下面是生成页面时的快照。')
    if report.get('final_membership_frozen'):
        start=page.index('<p class="stop">');end=page.index('</p>',start)+4
        page=page[:start]+'<p class="stop">已复核来源并冻结500条、200个文档隔离组：校准100条，最终400条。质量较差和质量未知来源保留为明确分层。标签正在建设；协议有效不能代替证据质量通过，发布检查已拦截题名冒充关系断言的参考。项目总上限1000万token或5000次请求不变；未运行最终候选验收。</p>'+page[end:]
    if authorization['total_tokens']==20000000:
        page=page.replace('项目总上限1000万token或5000次请求不变','用户已批准项目总上限2000万token；5000次请求、并发2及历史消耗不变')
        page=page.replace('项目总上限仍为1000万token或5000次请求','项目总上限已明确调整为2000万token或5000次请求')
    if semantic and semantic.get('release_hold'):
        start=page.index('<p class="stop">');end=page.index('</p>',start)+4
        page=page[:start]+'<p class="stop">语义质量检查未通过，批次已停止。抽查发现实体残词、实验室步骤误作农艺措施及关系断言不足；合法坐标不能证明语义正确。现有100条冻结校准参考保留原文件，仅作开发诊断，暂不可用于正式验收；最终400条仍是未完成草案。全项目上限2000万token、5000次请求、并发2，历史用量不变。</p>'+page[end:]
    page+=''.join('<li><a href="'+e(url)+'">'+e(title)+'</a></li>' for title,url in links)+'</ul><pre>'+e(json.dumps(report,ensure_ascii=False,indent=2))+'</pre></html>'
    (execution/'review.html').write_text(page,encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k in ['status','stage','compact_three_stage','shared_budget','historical_files_unchanged','run_dependencies_checked','changed_dependencies']},ensure_ascii=False))


if __name__=='__main__':main()
