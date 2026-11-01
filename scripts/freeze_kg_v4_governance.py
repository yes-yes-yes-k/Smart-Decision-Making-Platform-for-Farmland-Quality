"""Preserve history and pre-register tracks/gates without authorizing experiments."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import write,sha,BASE

def main():
    out=BASE.parent/'gold-v4';target=out/'history-freeze.json'
    if target.exists():raise ValueError('history already registered')
    names=['samples.jsonl','codex-reference.jsonl','codex-reference.manifest.json','graphrag-v6-codex-report.json',
        'development-recall-v8/comparison.json','development-two-stage-v9/comparison.json',
        'development-span-v10/comparison.json','development-candidate-v11-pilot/comparison.json','candidate-retention-v12/report.json']
    write(target,dict(files=[dict(path=str(BASE/n),sha256=sha(BASE/n)) for n in names],
        classification='historical_AI_development_reference',unchanged=True,expert_gold=False,production_acceptance_evidence=False))
    write(out/'evaluation-design/tracks-and-gates.json',dict(
        tracks=[dict(id='source_distribution',status='historical_snapshot_only',weighting='no population probability weights available'),
        dict(id='relation_challenge',status='requires_new_annotation',coverage_goal=dict(facts_per_type=30,independent_documents_per_type=10),goal_is_diagnostic_not_statistical_sufficiency=True),
        dict(id='new_blind_test',status='unestablished',label_custodian='unavailable',must_exclude_all_training_and_calibration_documents=True)],
        calibration_gate=dict(samples=100,mention_pairwise_f1=.90,relation_pairwise_f1=.85,valid_bindings=1.0,all_disagreements_resolved_or_unknown=True),
        scorer_tests_required=True,same_visible_input_required=True,context_and_normalization_tasks_separate=True,
        experiment=dict(status='not_authorized_by_quality_gate',arms=['frozen_v6_baseline','one_pre_registered_candidate'],
            inputs='new_task_contract_only',schedule='paired_interleaving',model='same configured model identity',
            failures='count in end-to-end; also report success-only extraction and availability',
            outputs=['mention_span_type','normalization_on_known_mentions','oracle_entity_relations','end_to_end_relations','evidence_overlap','independently_reviewed_evidence_sufficiency','document_macro','document_cluster_intervals','per_type_support','tokens_latency'],
            maximum_variants=1,budget='must be frozen after calibration; not unlimited retries'),
        production_approved=False))
    print('History and future experiment gates registered')

if __name__=='__main__':main()
