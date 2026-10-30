from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,dump
from framework.knowledge_graph.benchmark_membership_gate import verify_membership
from framework.knowledge_graph.benchmark_rebuild import sha256_file


def main():
    manifest=json.loads((OUT/'dataset-v1/manifest.json').read_text(encoding='utf-8'))
    for f in manifest['files']:
        if sha256_file(ROOT/f['path'])!=f['sha256']:raise ValueError('frozen_membership_file_changed')
    rows=readlines(OUT/'dataset-v1/samples.jsonl');docs={d['document_id']:d for d in readlines(OUT/'execution/source-pool-v2/documents.jsonl')}
    result=verify_membership(rows,docs)
    near=json.loads((OUT/'dataset-v1/selected-near-duplicate-gate.json').read_text(encoding='utf-8'))
    if near['status']!='pass':raise ValueError('selected_near_duplicate_review_pending')
    result.update(frozen_files_verified=len(manifest['files']),selected_near_duplicate_candidate_conflicts=len(near['conflicts']),
        formal_reference_complete=False,final_acceptance_allowed=False)
    dump(OUT/'dataset-v1/membership-gate.json',result);print(json.dumps(result))


if __name__=='__main__':main()
