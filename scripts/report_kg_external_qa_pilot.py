"""Report actual paired QA runs without conflating fixtures or full benchmarks."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from scripts.prepare_kg_external_qa_pilot import RUN,OUT,read
from scripts.prepare_kg_external_benchmarks import write_json
from framework.knowledge_graph.external_qa_evaluation import first_predictions,publisher_multi,refusal
from framework.knowledge_graph.external_qasper_scoring import load_official
from framework.knowledge_graph.external_benchmark_budget import open_external_budget


def main():
    from framework.knowledge_graph.external_benchmark_freeze import require_mutable
    require_mutable(OUT, OUT/"reports/real-QA-pilot-v1.json")
    import numpy as np
    selection=json.loads((RUN/"selection.json").read_text(encoding="utf-8"))
    report={"status":"inconclusive","scope":"frozen_26_question_nonfinal_pilot_not_full_benchmark_or_release_acceptance",
            "runtime":"GraphRAG3.3.0_extraction_NetworkX_local_graph_retrieval_vs_bge_m3_cosine",
            "datasets":{},"same_model_judge_bias":True,"expert_certified":False,"final_acceptance":False}
    for dataset in ("qasper","multihop_rag"):
        base=RUN/dataset
        if not all((base/arm/"score.json").exists() for arm in ("vector","graphrag")):
            report["datasets"][dataset]={"status":"not_scored_yet"};continue
        expected=set(selection["datasets"][dataset]["question_ids"])
        scores={arm:json.loads((base/arm/"score.json").read_text(encoding="utf-8")) for arm in ("vector","graphrag")}
        items={arm:{row["question_id"]:row for row in read(base/arm/"score.items.jsonl")} for arm in scores}
        if any(set(value)!=expected for value in items.values()):raise ValueError("paired_QA_denominator_mismatch")
        predictions={arm:first_predictions(read(base/arm/"predictions.jsonl"),expected)[0] for arm in scores}
        native={}
        if dataset=="qasper":
            refs=[row for row in read(OUT/"references/qasper/train.references.jsonl") if row["id"] in expected]
            papers={}
            for row in refs:papers.setdefault(row["document_id"],{"qas":[]})["qas"].append({"question_id":row["id"],"answers":row["native_answers"]})
            official=load_official(OUT)
            gold=official.get_answers_and_evidence(papers,text_evidence_only=False)
            for arm,values in predictions.items():
                native[arm]={key:max(official.token_f1_score(values[key]["predicted_answer"],ref["answer"]) for ref in gold[key]) if key in values else 0. for key in expected}
        else:
            refs={row["id"]:row for row in read(OUT/"references/multihop-v2/calibration.references.jsonl") if row["id"] in expected}
            official=publisher_multi(OUT,"qa_evaluate.py",{"has_intersection","extract_answer","calculate_metrics"})
            for arm,values in predictions.items():
                native[arm]={key:float(official["has_intersection"](official["extract_answer"](values[key]["predicted_answer"]).lower(),refs[key]["answer"].lower())) if key in values else 0. for key in expected}
        grouped=defaultdict(list)
        for key in sorted(expected):
            if items["vector"][key]["document_group"]!=items["graphrag"][key]["document_group"]:raise ValueError("paired_document_group_mismatch")
            grouped[items["vector"][key]["document_group"]].append(key)
        rng=np.random.default_rng(20261030);groups=list(grouped.values());deltas=[]
        for _ in range(2000):
            sample=[key for index in rng.integers(0,len(groups),size=len(groups)) for key in groups[index]]
            deltas.append(sum(native["graphrag"][key]-native["vector"][key] for key in sample)/len(sample))
        graph_build=json.loads((base/"graph-build.json").read_text(encoding="utf-8"))
        arms={}
        changed=0
        for arm,score in scores.items():
            configuration=json.loads((base/arm/"run-config.json").read_text(encoding="utf-8"))
            if configuration["prediction_mode"]!="live_backend_predictions":raise ValueError("fixture_cannot_be_real_QA_report")
            if configuration["selection_sha256"]!=hashlib.sha256((RUN/"selection.json").read_bytes()).hexdigest():raise ValueError("selection_mismatch")
            traces=[json.loads(path.read_text(encoding="utf-8")) for path in (base/arm/"items").glob("*.json")]
            judge_path=base/arm/"semantic-v1/judgments.jsonl"
            judgments={row["question_id"]:row["judgment"] for row in read(judge_path)} if judge_path.exists() else {}
            asserted={key for key,value in predictions[arm].items() if not refusal(value["predicted_answer"])}
            cited={key for key,value in predictions[arm].items() if value.get("predicted_evidence")}
            supported_assertions=sum(judgments.get(key,{}).get("answer_support")=="supported" for key in asserted)
            supported_citations=sum(judgments.get(key,{}).get("citation_support")=="supported" for key in cited)
            arms[arm]={"backend":configuration["backend"],"backend_available":configuration["backend_available"],
                       "completed":sum(row["completed"] for row in items[arm].values()),"questions":len(expected),
                       "native_answer_metric":"Answer F1" if dataset=="qasper" else "any_token_overlap_not_strict_accuracy",
                       "native_answer_score":sum(native[arm].values())/len(expected),
                       "official":score.get("official",score.get("official_formula_on_fixed_partition")),
                       "supplementary":score["supplementary"],"semantic_support":score["semantic_support"],
                       "queries_with_graph_contribution":sum(row.get("retrieval",{}).get("graph_contributing_chunks",0)>0 for row in traces),
                       "error_records":sum(row["state"]!="completed" for row in traces),
                       "asserted_answer_grounding":{"answers":len(asserted),"supported":supported_assertions,
                           "support_rate_lower_bound":supported_assertions/len(asserted) if asserted else None,
                           "unjudged":sum(key not in judgments for key in asserted),
                           "refusals_counted_in_separate_completion_and_refusal_metrics":True,
                           "small_support_warning":len(asserted)<30},
                       "citation_query_grounding":{"citing_answers":len(cited),"supported":supported_citations,
                           "support_rate_lower_bound":supported_citations/len(cited) if cited else None,
                           "small_support_warning":len(cited)<30}}
        for key in expected:
            a=base/"vector/items"/(hashlib.sha256(key.encode()).hexdigest()+".json")
            b=base/"graphrag/items"/(hashlib.sha256(key.encode()).hexdigest()+".json")
            if a.exists() and b.exists():
                x,y=json.loads(a.read_text(encoding="utf-8")),json.loads(b.read_text(encoding="utf-8"))
                changed+=x.get("retrieved_chunk_ids")!=y.get("retrieved_chunk_ids")
        report["datasets"][dataset]={"questions":len(expected),"partition":selection["datasets"][dataset]["partition"],
            "graph_build":graph_build,"arms":arms,"retrieval_changed_questions":changed,
            "native_answer_paired_delta_graphrag_minus_vector":sum(native["graphrag"][key]-native["vector"][key] for key in expected)/len(expected),
            "paired_document_group_bootstrap_95_interval":np.quantile(deltas,[.025,.975]).tolist(),
            "bootstrap":{"groups":len(groups),"resamples":2000,"seed":20261030},
            "coverage_limitations":["Small frozen nonfinal pilot; no full-dataset or soil-domain claim.","Only source text/headings/captions indexed; no figure pixels.","No claim that graph descriptions are independently verified facts."]}
    report["budget"]=open_external_budget(OUT).summary()
    write_json(OUT/"reports/real-QA-pilot-v1.json",report)
    print(json.dumps({name:{arm:row["native_answer_score"] for arm,row in value.get("arms",{}).items()} for name,value in report["datasets"].items()}))


if __name__=="__main__":main()
