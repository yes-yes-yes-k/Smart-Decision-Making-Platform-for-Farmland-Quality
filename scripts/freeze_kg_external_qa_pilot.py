"""Freeze the completed first QA trial and its exact source/scoring versions."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from scripts.prepare_kg_external_qa_pilot import RUN,OUT
from scripts.prepare_kg_external_benchmarks import write_json
from framework.knowledge_graph.external_benchmark_budget import open_external_budget


def main():
    target=OUT/'reports/qa-pilot-result-manifest-v1.json'
    if target.exists():
        data=json.loads(target.read_text(encoding='utf-8'))
        for name,h in data['files'].items():
            if hashlib.sha256((OUT/name).read_bytes()).hexdigest()!=h:raise ValueError('frozen_QA_trial_changed:'+name)
        print(json.dumps({'state':'already_frozen_unchanged','files':len(data['files'])}));return
    state=json.loads((RUN/'run-state.json').read_text(encoding='utf-8'))
    if state['state']!='completed' or open_external_budget(OUT).summary()['inflight']:raise ValueError('trial_not_terminal')
    for dataset,n in [('qasper',10),('multihop_rag',16)]:
        for arm in ['vector','graphrag']:
            folder=RUN/dataset/arm
            if len((folder/'predictions.jsonl').read_text(encoding='utf-8').splitlines())!=n:raise ValueError('prediction_count_mismatch')
            if len((folder/'semantic-v1/judgments.jsonl').read_text(encoding='utf-8').splitlines())!=n:raise ValueError('semantic_review_incomplete')
    names=['scripts/run_kg_external_qa_pilot.py','scripts/prepare_kg_external_qa_pilot.py',
           'framework/knowledge_graph/external_qa_retrieval.py','framework/knowledge_graph/external_qa_evaluation.py',
           'framework/knowledge_graph/external_qasper_scoring.py','scripts/score_kg_external_qa.py','scripts/judge_kg_external_qa.py',
           'scripts/report_kg_external_qa_pilot.py','tests/test_external_qa_scoring.py','tests/test_external_qa_retrieval.py',
           'framework/knowledge_graph/acceptance_budget.py','framework/knowledge_graph/external_benchmark_budget.py']
    for name in names:
        src=REPO/name;dst=RUN/'frozen-code'/name;dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists() and dst.read_bytes()!=src.read_bytes():raise ValueError('frozen_code_already_differs')
        dst.write_bytes(src.read_bytes())
    issue={'status':'diagnostic_input_adapter_issue','issue':'Native publisher/author/published_at metadata omitted from candidate source blocks; temporal/source questions may be affected.',
           'reference_changes':0,'next_version':'qa-pilot-v2-metadata','first_trial_must_not_be_overwritten':True}
    write_json(RUN/'known-input-limitations.json',issue)
    paths=[p for p in RUN.rglob('*') if p.is_file()]
    paths.append(OUT/'reports/real-QA-pilot-v1.json')
    files={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write_json(target,{'status':'frozen_nonfinal_diagnostic_trial','created_at':datetime.now(timezone.utc).isoformat(),
        'files':files,'known_input_limitation':issue,'final_acceptance':False,'budget_checkpoint':open_external_budget(OUT).summary()})
    print(json.dumps({'state':'frozen','files':len(files),'reference_changes':0}))


if __name__=='__main__':main()
