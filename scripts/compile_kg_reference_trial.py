"""Compile the completed full-index trial and freeze only the annotation workflow."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,budget_snapshot
from scripts.prepare_kg_reference_full_index_comparison import prepare,RUN
from scripts.report_kg_benchmark_pilot import signature
from framework.knowledge_graph.benchmark_reference_compile import compile_reference
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_rebuild import sha256_file


def main():
    jobs=prepare();packets={j['id']:j['packet'] for j in jobs}
    keys={r['sample_id']:r for r in readlines(OUT/'protocol-r4/private-control-keys.jsonl')}
    items=[];refs=[]
    for path in sorted((RUN/'proposals').glob('*.json')):
        row=json.loads(path.read_text(encoding='utf-8'));sid=row['id'].removeprefix('full-index-review:')
        valid=row.get('protocol')
        item=dict(sample_id=sid,control=sid in keys,original_state=row['state'],original_response_sha256=sha256_file(path))
        if valid:
            compiled=compile_reference(packets[row['id']],valid,load_schema(ROOT))
            item['compiled']=compiled
            if sid in keys:
                item['control_exact']=signature(compiled['materialized_proposal'])==signature(keys[sid]['expected'])
                item['masks_applicable']=all(m['status']=='applicable' for m in compiled['source_reference_masks'])
            elif compiled['reference_ready']:
                refs.append(dict(sample_id=sid,visible_input={k:packets[row['id']][k] for k in ['sample_id','blocks']},
                    reference=compiled['materialized_proposal'],reference_masks=compiled['source_reference_masks'],
                    independent_source_review=compiled,reference_status='AI_silver_development_trial_not_formal_acceptance',
                    expert_certified=False,same_model_error_correlation=True))
        items.append(item)
    controls=[r for r in items if r['control']]
    passed=len(items)==16 and all(r.get('compiled',{}).get('reference_ready') for r in items) and all(r['control_exact'] and r['masks_applicable'] for r in controls)
    summary=dict(status='inconclusive',scope='annotation_workflow_small_pilot_only',
        workflow_validation='pass' if passed else 'inconclusive',expected_cases=16,compiled_cases=len(items),
        control_cases=len(controls),control_references_exact=sum(r.get('control_exact',False) for r in controls),
        real_source_references_ready=len(refs),reference_call_stages=3,
        duplicate_facts_merge_evidence_not_extra_true_positives=True,model_responses_modified=False,
        full_character_ids_retained=True,compact_selector_adopted=False,
        production_backend_quality_not_measured=True,formal_acceptance_ready=False,
        expert_certified=False,same_model_error_correlation=True,budget=budget_snapshot())
    lines(RUN/'compiled-items.jsonl',items);lines(RUN/'source-reference-drafts.jsonl',refs)
    dump(RUN/'compiled-report.json',summary)
    if passed:
        paths=[OUT/'protocol-r4/annotation-handbook.md',ROOT/'framework/knowledge_graph/benchmark_cells.py',
            ROOT/'framework/knowledge_graph/benchmark_legacy_proposal_union.py',ROOT/'framework/knowledge_graph/benchmark_reference_schema.py',
            ROOT/'scripts/replay_kg_benchmark_reference_review.py',ROOT/'scripts/review_kg_benchmark_reference.py',
            ROOT/'framework/knowledge_graph/benchmark_reference_compile.py']
        dump(OUT/'annotation-workflow-v1.json',dict(status='frozen_for_AI_silver_construction',
            formal_acceptance=False,reference_request_stages=3,expert_certified=False,same_model_error_correlation=True,
            source_input='original_chunk_and_document_title_only',files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in paths],
            trial_report_sha256=sha256_file(RUN/'compiled-report.json')))
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
