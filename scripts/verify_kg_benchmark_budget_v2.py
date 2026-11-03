"""Verify immutable histories against the user's new explicit 20M cap."""
from pathlib import Path
import json
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,verify_history,budget_snapshot,dump
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2


def main():
    old=verify_history();initial=json.loads((OUT/'audit/artifact-manifest.json').read_text(encoding='utf-8'))
    for row in initial['files']:
        if sha256_file(OUT/row['path'])!=row['sha256']:raise ValueError('initial_artifact_changed:'+row['path'])
    checkpoint=json.loads((OUT/'governance/checkpoint.json').read_text(encoding='utf-8'))['budget']
    with sqlite3.connect((OLD/'budget.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as conn:
        rows=conn.execute('SELECT phase,reserved,charged,state FROM attempts WHERE id<=?',(checkpoint['requests'],)).fetchall()
    phases={p:sum(ch if ch is not None else reserved for phase,reserved,ch,state in rows if phase==p) for p,_,_,_ in rows}
    if len(rows)!=checkpoint['requests'] or phases!=checkpoint['by_phase']:raise ValueError('historical_budget_prefix_changed')
    auth=OUT/'execution/project-budget-authorization-v2.json';a=json.loads(auth.read_text(encoding='utf-8'))
    if sha256_file(OUT/a['prior_authorization_path'])!=a['prior_authorization_sha256']:raise ValueError('prior_authorization_changed')
    budget=AuthorizedBudgetV2(OLD/'budget.sqlite3',authorization=auth,allocation=OUT/'execution/phase-allocation-v2.json').summary()
    if budget['tokens_charged_or_reserved']>20000000 or budget['requests']>5000 or budget['inflight']>2:
        raise ValueError('global_budget_or_concurrency_exceeded')
    count=0
    manifests=[OUT/'protocol/manifest.json',OUT/'dataset-v1/manifest.json',OUT/'calibration-silver-v1/manifest.json']
    final=OUT/'test-silver-v1/manifest.json'
    if final.exists():manifests.append(final)
    semantic=OUT/'semantic-quality-audit-v1/manifest.json'
    if semantic.exists():manifests.append(semantic)
    for path in manifests:
        manifest=json.loads(path.read_text(encoding='utf-8'))
        for f in manifest['files']:
            if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('frozen_protocol_dataset_or_reference_changed:'+f['path'])
            count+=1
    report=dict(status='pass',scope='immutable_artifacts_and_explicit_shared_budget_only',
        historical_files_unchanged=old,initial_artifacts_verified=len(initial['files']),frozen_dataset_and_reference_files_verified=count,
        historical_ledger_prefix_preserved=True,protocol_and_ontology_hashes_verified=True,
        current_budget=budget,final_dataset_reference_complete=final.exists(),
        integrity_pass_is_not_semantic_quality_acceptance=True)
    dump(OUT/'execution/budget-and-integrity-v2.json',report);print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
