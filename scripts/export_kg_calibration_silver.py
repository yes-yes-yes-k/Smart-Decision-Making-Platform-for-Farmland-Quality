"""Versioned calibration export; never replace existing frozen references."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,lines,dump,budget_snapshot
from framework.knowledge_graph.benchmark_reference_compile_v2 import compile_reference_v2
from framework.knowledge_graph.benchmark_reference_gate import check_reference
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_rebuild import sha256_file

DEST=OUT/'calibration-silver-v1'


def main():
    manifest=DEST/'manifest.json'
    if manifest.exists():
        frozen=json.loads(manifest.read_text(encoding='utf-8'))
        for f in frozen['files']:
            if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('frozen_calibration_silver_changed')
        print('frozen_calibration_silver_verified');return
    samples=readlines(OUT/'dataset-v1/calibration-samples.jsonl');expected={r['sample_id'] for r in samples}
    references={r['sample_id']:r for r in readlines(OUT/'reference-release-v1/calibration/references.jsonl')}
    packets={p['sample_id']:p for p in readlines(OUT/'dataset-v1/annotation-inputs.jsonl')}
    corrections=[];unresolved_by_id={};issue_paths=[]
    paths=list((OUT/'references-v1/calibration/issue-adjudication/proposals').glob('*.json'))
    paths+=list((OUT/'references-v1/calibration/truncated-field-continuation/proposals').glob('*.json'))
    for path in paths:
        row=json.loads(path.read_text(encoding='utf-8'));sid=row['id'].removeprefix('unresolved-source-case:').removeprefix('unemitted-relations:')
        if sid not in expected:raise ValueError('wrong_partition_adjudication')
        issue_paths.append(path)
        if not row.get('protocol'):
            unresolved_by_id[sid]=dict(sample_id=sid,state=row['state'],error=row.get('error'));continue
        c=compile_reference_v2(packets[sid],row['protocol'],load_schema(ROOT))
        record=dict(sample_id=sid,reference=c['materialized_proposal'],reference_masks=c['source_reference_masks'],
            visible_input={k:packets[sid][k] for k in ['sample_id','blocks']},expert_certified=False,same_model_error_correlation=True,
            reference_status='AI_silver_independent_issue_adjudication',adjudication_path=path.relative_to(ROOT).as_posix(),
            adjudication_sha256=sha256_file(path))
        gate=check_reference(record)
        if c['reference_ready'] and gate['reference_ready']:
            references[sid]=dict(record,release_gate=gate)
            unresolved_by_id.pop(sid,None)
            corrections.append(dict(sample_id=sid,source='separate_source_adjudication_not_silent_deletion',adjudication_path=record['adjudication_path']))
        else:unresolved_by_id[sid]=dict(sample_id=sid,compilation_errors=c['errors'],unresolved=c.get('unresolved'),release_gate=gate)
    unresolved=list(unresolved_by_id.values())
    if not set(references).issubset(expected):raise ValueError('unexpected_reference_sample')
    values=[references[sid] for sid in sorted(references)]
    for r in values:
        if r['visible_input']['blocks']!=packets[r['sample_id']]['blocks']:raise ValueError('reference_wrong_source')
        if not check_reference(r)['reference_ready']:raise ValueError('invalid_reference_evidence')
    lines(DEST/'references.jsonl',values);lines(DEST/'source-adjudication-corrections.jsonl',corrections)
    lines(DEST/'unresolved.jsonl',unresolved)
    report=dict(status='inconclusive',expected_samples=len(expected),available_references=len(values),
        calibration_reference_complete=len(values)==len(expected),missing_sample_ids=sorted(expected-set(references)),
        unresolved_cases=unresolved,adjudication_corrections=len(corrections),expert_certified=False,
        same_model_error_correlation=True,candidate_backend_evaluations=0,formal_acceptance_not_established=True,
        final_400_references_not_generated=True,shared_budget=budget_snapshot())
    dump(DEST/'report.json',report)
    if report['calibration_reference_complete'] and not unresolved:
        files=[DEST/'references.jsonl',DEST/'source-adjudication-corrections.jsonl',DEST/'unresolved.jsonl',DEST/'report.json',
            OUT/'dataset-v1/manifest.json',OUT/'reference-release-v1/run-config.json',Path(__file__),
            ROOT/'framework/knowledge_graph/benchmark_reference_compile_v2.py',ROOT/'framework/knowledge_graph/benchmark_reference_gate.py']+issue_paths
        base=OUT/'references-v1/calibration'
        files+=sorted((base/'initial/proposals').glob('*.json'))+sorted((base/'review/proposals').glob('*.json'))
        files+=sorted(base.rglob('*config.json'))
        files+=[base/'issue-adjudication/initial-response-diagnostics.json',base/'truncated-field-continuation/field-plan.json',
            ROOT/'scripts/build_kg_benchmark_references.py',ROOT/'scripts/adjudicate_kg_reference_issues.py',ROOT/'scripts/complete_kg_truncated_reference_fields.py',
            ROOT/'framework/knowledge_graph/benchmark_partial_annotation.py']
        files=list(dict.fromkeys(files))
        dump(manifest,dict(status='frozen_AI_silver_calibration_reference',samples=len(expected),
            expert_certified=False,final_acceptance_pass=False,
            files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in files]))
    print(json.dumps({k:report[k] for k in ['status','expected_samples','available_references','calibration_reference_complete','adjudication_corrections']},ensure_ascii=False))


if __name__=='__main__':main()
