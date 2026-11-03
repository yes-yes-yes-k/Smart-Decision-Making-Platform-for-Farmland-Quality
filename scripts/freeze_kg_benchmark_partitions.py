"""Freeze audited source membership and actual extraction inputs, before labels."""
from pathlib import Path
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,SOURCE,dump,lines,readlines
from scripts.prepare_kg_benchmark_metadata import current_qualification
from framework.knowledge_graph.benchmark_sampling_v2 import sample
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from framework.knowledge_graph.benchmark_protocol import source_packet
from framework.knowledge_graph.acceptance_data import assert_isolation

DEST=OUT/'dataset-v1'


def main():
    if (DEST/'manifest.json').exists():
        manifest=json.loads((DEST/'manifest.json').read_text(encoding='utf-8'))
        for r in manifest['files']:
            if sha256_file(ROOT/r['path'])!=r['sha256']:raise ValueError('frozen_dataset_changed:'+r['path'])
        print('existing_frozen_dataset_verified');return
    documents=[r for r in readlines(OUT/'execution/source-pool-v2/documents.jsonl') if r['sampling_eligible']]
    initial={d['id']:d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl')}
    chunks=[]
    for d in documents:
        for c in readlines(OUT/f"audit/chunks/{d['document_id']}.jsonl"):
            if hashlib.sha256(c['text'].encode()).hexdigest()!=c['text_sha256']:raise ValueError('source_chunk_hash_mismatch')
            chunks.append(c)
    seed='extraction-benchmark-v2-source-reviewed-v1-20261029'
    rows,report=sample(documents,chunks,seed);assert_isolation(rows)
    selected={r['document_id'] for r in rows}
    qualification=current_qualification([initial[i] for i in selected])
    if not all(qualification.values()):raise ValueError('current_database_source_qualification_changed')
    source_files=[]
    for i in sorted(selected):
        d=initial[i];path=next((SOURCE/p for p in d['source_paths'] if (SOURCE/p).is_file()),None)
        if path is None or sha256_file(path)!=d['file_hash']:raise ValueError('current_source_file_hash_changed')
        source_files.append(dict(document_id=i,file_sha256=d['file_hash'],source_relative_path=path.relative_to(SOURCE).as_posix()))
    handbook=(OUT/'protocol-r4/annotation-handbook.md').read_text(encoding='utf-8')
    packets=[]
    for r in rows:
        p=source_packet(r,handbook);p['output_protocol']='extraction-benchmark-v2-r4';packets.append(p)
    lines(DEST/'samples.jsonl',rows);lines(DEST/'source-files.jsonl',source_files)
    lines(DEST/'annotation-inputs.jsonl',packets)
    for part in ['calibration','test']:
        lines(DEST/(part+'-samples.jsonl'),[r for r in rows if r['partition']==part])
    dump(DEST/'sampling-report.json',dict(report,status='membership_frozen_reference_pending',
        document_groups_isolated=True,source_files_currently_verified=True,
        input_title_policy='unchanged_frozen_database_title_not_visual_or_corrected_title',
        metadata_unknown_is_explicit_stratum_not_quality_exclusion=True))
    dependencies=[DEST/'samples.jsonl',DEST/'source-files.jsonl',DEST/'annotation-inputs.jsonl',DEST/'calibration-samples.jsonl',DEST/'test-samples.jsonl',DEST/'sampling-report.json',
        OUT/'execution/source-pool-v2/documents.jsonl',OUT/'execution/source-pool-v2/report.json',OUT/'annotation-workflow-v1.json',
        Path(__file__),ROOT/'framework/knowledge_graph/benchmark_sampling_v2.py']
    dump(DEST/'manifest.json',dict(status='frozen_membership_not_completed_labels',seed=seed,samples=len(rows),documents=len(selected),
        reference_status='not_generated',acceptance_status='inconclusive',expert_certified=False,
        final_candidate_evaluation_allowed=False,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in dependencies]))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
