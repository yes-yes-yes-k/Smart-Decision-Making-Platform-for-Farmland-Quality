"""Final reference export; only freeze once all 400 source cases are resolved."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,lines,dump,budget_snapshot
from framework.knowledge_graph.benchmark_reference_compile_v2 import compile_reference_v2
from framework.knowledge_graph.benchmark_reference_gate import check_reference
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from collections import Counter
from framework.knowledge_graph.benchmark_reference_hold import require_no_semantic_hold

DEST=OUT/'test-silver-v1';BASE=OUT/'references-v1/test'


def main():
    require_no_semantic_hold(OUT)
    manifest_path=DEST/'manifest.json'
    if manifest_path.exists():
        for f in json.loads(manifest_path.read_text(encoding='utf-8'))['files']:
            if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('frozen_final_reference_changed:'+f['path'])
        print('frozen_final_silver_verified');return
    samples=readlines(OUT/'dataset-v1/test-samples.jsonl');expected={r['sample_id'] for r in samples}
    if len(samples)!=400 or len(expected)!=400:raise ValueError('frozen_final400_roster_required')
    packets={r['sample_id']:r for r in readlines(OUT/'dataset-v1/annotation-inputs.jsonl')}
    references={r['sample_id']:r for r in readlines(OUT/'reference-release-v1/test/references.jsonl')}
    unresolved={r['sample_id']:dict(sample_id=r['sample_id'],release_gate=r['release_gate'])
        for r in readlines(OUT/'reference-release-v1/test/requires-adjudication.jsonl')}
    corrections=[];issue_paths=[]
    for stage in ['issue-adjudication','truncated-field-continuation']:
        for path in sorted((BASE/stage/'proposals').glob('*.json')):
            row=json.loads(path.read_text(encoding='utf-8'))
            sid=row['id'].removeprefix('unresolved-source-case:').removeprefix('unemitted-fields:')
            if sid not in expected:raise ValueError('wrong_final_reference_partition')
            issue_paths.append(path)
            # A newer unresolved source judgment must never be hidden by an
            # earlier accepted prediction of the same case.
            references.pop(sid,None)
            if not row.get('protocol'):
                unresolved[sid]=dict(sample_id=sid,state=row['state'],error=row.get('error'));continue
            compiled=compile_reference_v2(packets[sid],row['protocol'],load_schema(ROOT))
            record=dict(sample_id=sid,reference=compiled['materialized_proposal'],reference_masks=compiled['source_reference_masks'],
                visible_input={k:packets[sid][k] for k in ['sample_id','blocks']},expert_certified=False,
                same_model_error_correlation=True,reference_status='AI_silver_independent_issue_adjudication',
                adjudication_path=path.relative_to(ROOT).as_posix(),adjudication_sha256=sha256_file(path))
            gate=check_reference(record)
            if compiled['reference_ready'] and gate['reference_ready']:
                references[sid]=dict(record,release_gate=gate);unresolved.pop(sid,None)
                corrections.append(dict(sample_id=sid,adjudication_path=record['adjudication_path'],
                    source='separate_source_judgment_not_automatic_relation_deletion'))
            else:unresolved[sid]=dict(sample_id=sid,compilation_errors=compiled['errors'],
                unresolved=compiled.get('unresolved'),release_gate=gate)
    if not set(references).issubset(expected):raise ValueError('unexpected_final_reference_sample')
    initial={}
    for path in (BASE/'initial/proposals').glob('*.json'):
        row=json.loads(path.read_text(encoding='utf-8'));initial[row['id']]=row
    values=[references[sid] for sid in sorted(references)]
    for r in values:
        if r['visible_input']['blocks']!=packets[r['sample_id']]['blocks']:raise ValueError('reference_wrong_source')
        if not check_reference(r)['reference_ready']:raise ValueError('invalid_final_reference_evidence')
        r['construction_initial_states']=[initial.get(role+':'+r['sample_id'],{}).get('state','missing') for role in ['A','B']]
        r['initial_failures_not_reclassified']=True
    lines(DEST/'references.jsonl',values);lines(DEST/'source-adjudication-corrections.jsonl',corrections)
    lines(DEST/'unresolved.jsonl',[unresolved[sid] for sid in sorted(unresolved)])
    state=json.loads((BASE/'run-state.json').read_text(encoding='utf-8'))
    complete=len(values)==400 and not unresolved and state.get('active') is False
    report=dict(status='inconclusive',expected_samples=400,available_references=len(values),
        final_reference_complete=complete,missing_sample_ids=sorted(expected-set(references)),
        unresolved_cases=len(unresolved),expert_certified=False,same_model_error_correlation=True,
        initial_response_states=dict(Counter(row['state'] for row in initial.values())),
        reference_cases_with_two_protocol_valid_initials=sum(r['construction_initial_states']==['protocol_valid','protocol_valid'] for r in values),
        complete_reference_does_not_imply_all_initial_annotations_succeeded=True,
        candidate_backend_evaluations=0,formal_acceptance_not_established=True,shared_budget=budget_snapshot())
    dump(DEST/'report.json',report)
    if complete:
        originals=list((BASE/'initial/proposals').glob('*.json'))
        if len(originals)!=800:raise ValueError('all_800_original_responses_must_be_archived')
        if budget_snapshot()['inflight']:raise ValueError('cannot_freeze_during_model_calls')
        files=[DEST/'references.jsonl',DEST/'source-adjudication-corrections.jsonl',DEST/'unresolved.jsonl',DEST/'report.json',
            Path(__file__),OUT/'reference-release-v1/run-config.json',OUT/'annotation-workflow-v1.json',
            ROOT/'framework/knowledge_graph/benchmark_reference_compile_v2.py',ROOT/'framework/knowledge_graph/benchmark_reference_gate.py',
            ROOT/'scripts/build_kg_benchmark_final_references.py',ROOT/'scripts/resume_kg_benchmark_final_references.py',
            ROOT/'scripts/adjudicate_kg_final_reference_issues.py',OUT/'execution/project-budget-authorization-v2.json']
        for manifest in [OUT/'protocol/manifest.json',OUT/'dataset-v1/manifest.json',OUT/'calibration-silver-v1/manifest.json']:
            files.append(manifest)
            for f in json.loads(manifest.read_text(encoding='utf-8'))['files']:
                path=ROOT/f['path']
                if sha256_file(path)!=f['sha256']:raise ValueError('frozen_dependency_changed:'+f['path'])
                files.append(path)
        files+=originals+list((BASE/'review/proposals').glob('*.json'))+issue_paths
        files+=list(BASE.rglob('*config.json'))+list(BASE.rglob('selection.json'))+list(BASE.rglob('field-plan.json'))
        files+=list(BASE.rglob('initial-response-diagnostics.json'))+list(BASE.rglob('source-qualification.json'))
        files+=list((BASE/'resume-audit-v1').rglob('*.json'))
        continuation=ROOT/'scripts/complete_kg_final_truncated_fields.py'
        if continuation.exists():files.append(continuation)
        dump(manifest_path,dict(status='frozen_AI_silver_final_reference',samples=400,expert_certified=False,
            final_acceptance_pass=False,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p))
                for p in sorted(set(files))]))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
