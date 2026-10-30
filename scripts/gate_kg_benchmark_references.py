"""Independent release view; never publish invalid facts as a corrected negative."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,lines,dump
from framework.knowledge_graph.benchmark_reference_gate import check_reference
from framework.knowledge_graph.benchmark_reference_compile_v2 import compile_reference_v2
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_rebuild import sha256_file
import json


def main():
    config=dict(scope='necessary_evidence_checks_and_literal_structural_compilation_not_formal_acceptance',
        extends_frozen_annotation_workflow='annotation-workflow-v1.json',
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in [Path(__file__),
            ROOT/'framework/knowledge_graph/benchmark_reference_compile_v2.py',ROOT/'framework/knowledge_graph/benchmark_reference_gate.py']])
    path=OUT/'reference-release-v1/run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('reference_release_rules_frozen_use_new_version')
    if not path.exists():dump(path,config)
    for part in ['calibration','test']:
        path=OUT/f'references-v1/{part}/references.jsonl'
        if not path.exists():continue
        rows=readlines(path);accepted=[];issues=[]
        known={r['sample_id'] for r in rows}
        inputs={r['sample_id']:r for r in readlines(OUT/'dataset-v1/annotation-inputs.jsonl')}
        for item in readlines(OUT/f'references-v1/{part}/items.jsonl'):
            if item.get('compiled'):
                c=compile_reference_v2(inputs[item['sample_id']],item['compiled'],load_schema(ROOT))
                if c['reference_ready']:
                    record=dict(sample_id=item['sample_id'],reference=c['materialized_proposal'],reference_masks=c['source_reference_masks'],
                        visible_input={k:inputs[item['sample_id']][k] for k in ['sample_id','blocks']},
                        structural_compilation=c['canonicalization_version'],expert_certified=False,same_model_error_correlation=True)
                    record['reference_status']='AI_silver_pending_complete_dataset_validation'
                    rows=[r for r in rows if r['sample_id']!=item['sample_id']]+[record]
        for r in rows:
            check=check_reference(r)
            if check['reference_ready']:accepted.append(dict(r,release_gate=check))
            else:issues.append(dict(sample_id=r['sample_id'],release_gate=check,reference_unchanged=True))
        target=OUT/'reference-release-v1'/part
        lines(target/'references.jsonl',accepted);lines(target/'requires-adjudication.jsonl',issues)
        dump(target/'report.json',dict(status='inconclusive',raw_source_adjudicated=len(rows),
            necessary_evidence_checks_passed=len(accepted),requires_adjudication=len(issues),
            all_original_facts_retained_in_raw_archive=True,invalid_relations_not_silently_deleted=True,
            final_acceptance_not_run=True,expert_certified=False))
        print(part,len(accepted),len(issues))


if __name__=='__main__':main()
