"""Render admission evidence and unresolved gates; never report a benchmark pass."""
from pathlib import Path
import hashlib
import html
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_budget import open_external_budget
from prepare_kg_external_benchmarks import write_json


ROOT = Path("artifacts/knowledge_platform/external-benchmark-v1")


def main():
    registry = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
    data = json.loads((ROOT / "reports/materialization.json").read_text(encoding="utf-8"))
    resolutions = json.loads((ROOT / "reports/data-resolutions-v1.json").read_text(encoding="utf-8"))
    updates = {}
    for filename in ["qasper-source-spans-v3.json", "source-group-decisions-v2.json", "isolation-screen-v2.json", "calibration-budget-v1.json", "qa-scoring-chain-v1.json", "qa-scoring-chain-v2.json", "real-QA-pilot-v1.json", "real-QA-pilot-v2.json", "QA-evidence-granularity-v2.json", "qa-threshold-proposal-v1.json", "qa-judge-repeat-stability-v1.json", "qa-scoring-chain-v3.json", "final-QA-full-scope-budget-v2.json", "extraction-threshold-proposal-v1.json", "final-QA-budget-gap-v1.json", "task-input-coverage-v2.json", "task-input-coverage-v3.json"]:
        path = ROOT / "reports" / filename
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if filename == "isolation-screen-v2.json":
                value = {name: {"documents": item["documents"], "cross_partition_candidates": len(item["cross_partition_candidates"]),
                                "semantic_deduplication_certified": False}
                         for name, item in value["datasets"].items()}
            updates[filename] = value
    qa_run=ROOT/"runs/qa-pilot-v2-metadata"
    if (qa_run/"run-config.json").exists():
        updates["real_QA_execution_progress"]={}
        for dataset in ("qasper","multihop_rag"):
            folder=qa_run/dataset
            updates["real_QA_execution_progress"][dataset]={
                "graph_units_saved":len(list((folder/"graph-predictions").glob("*.json"))),
                "embedding_batches_saved":len(list((folder/"embedding-responses").glob("*.json"))),
                "vector_answer_items":len(list((folder/"vector/items").glob("*.json"))),
                "graphrag_answer_items":len(list((folder/"graphrag/items").glob("*.json")))}
    calibration_progress = ROOT / "runs/redocred-calibration-v1/progress.json"
    if calibration_progress.exists():
        updates["full_calibration_progress"] = json.loads(calibration_progress.read_text(encoding="utf-8"))
    calibration_score = ROOT / "runs/redocred-calibration-v1/score.json"
    if calibration_score.exists():
        value = json.loads(calibration_score.read_text(encoding="utf-8"))
        updates["full_calibration_score"] = {key: value[key] for key in ["execution_state", "saved_documents", "pending_documents", "scores_provisional", "precision", "recall", "f1", "completion_rate", "document_bootstrap_95_interval"]}
    pilot_path = ROOT / "runs/redocred-pilot-v2-utf8/score.json"
    if pilot_path.exists():
        pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
        updates["real_native_relation_pilot"] = {key: pilot[key] for key in
            ["scope", "precision", "recall", "f1", "completion_rate", "tp", "fp", "fn", "document_bootstrap_95_interval", "budget"]}
    downloads = json.loads((ROOT / "download-manifest.json").read_text(encoding="utf-8"))
    for file in downloads["files"]:
        if hashlib.sha256((ROOT / file["path"]).read_bytes()).hexdigest() != file["sha256"]:
            raise ValueError("download_hash_mismatch:" + file["path"])
    admissions = {
        "agriner": {"status": "blocked", "license": "unconfirmed_from_original_publisher",
                    "evidence": ["sources/agriner/README.md", "sources/agriner/tree.json", "sources/agriner/split_data.py"],
                    "reasons": ["No publisher LICENSE or data terms found in pinned repository; third-party CC-BY-SA claim is not sufficient.",
                                "Published split script shuffles records without fixed seed or document grouping; source grouping needs verification."],
                    "data_downloaded": False, "model_use_allowed": False},
        "redocred": {"status": "admitted_local_evaluation_pending_release_gates", "license": "MIT",
                     "evidence": ["sources/redocred/LICENSE", "sources/redocred/README.md", "sources/docred_upstream/huggingface/README.md"],
                     "basis": "Publisher revision repository distributes the dataset under root MIT; original publisher DocRED data card independently declares dataset MIT. Retain both attributions and upstream source provenance; no automatic redistribution of original articles.",
                     "tasks": ["given_entity_document_relation"], "data_downloaded": True,
                     "release_gates": ["effective calibration499 vs official dev500 must be reported separately", "complete calibration499 finished; numeric thresholds still unconfirmed", "end-to-end extraction not evaluated by this given-entity task"],
                     "model_use_allowed": "frozen_development_and_effective_calibration_only_final_not_authorized"},
        "qasper": {"status": "admitted_local_evaluation_pending_release_gates", "license": "CC-BY-4.0",
                   "evidence": ["sources/qasper/huggingface/README.md", "sources/qasper/huggingface/qasper.py"],
                   "tasks": ["paper_qa", "evidence_selection", "unanswerable_qa"], "data_downloaded": True,
                   "release_gates": ["60 remaining native evidence source gaps retained; exact-span retrieval scored", "Frozen v2 real nonfinal QA and semantic review completed; small support and same-model judge limits; final scope/thresholds unconfirmed", "Full final QA exceeds current request cap"],
                   "model_use_allowed": "frozen_nonfinal_QA_trial_only_final_not_authorized"},
        "multihop_rag": {"status": "admitted_data_partition_pending", "license": "ODC-BY-1.0",
                         "evidence": ["sources/multihop_rag/README.md", "sources/multihop_rag/huggingface/README.md"],
                         "tasks": ["multi_document_retrieval", "qa", "null_query"], "data_downloaded": True,
                         "release_gates": ["custom source-grouped partition v2: development1905/calibration132/final519, not official full-dataset score", "Frozen 16-question real QA and semantic review completed; reference repeat disagreement1/16; final scope/thresholds unconfirmed"],
                         "model_use_allowed": "frozen_nonfinal_QA_trial_only_final_not_authorized"},
    }
    for row in registry["datasets"]:
        row.setdefault("metadata_fetch_state", row["admission"])
        row["admission_review"] = admissions[row["id"]]
        row["admission"] = admissions[row["id"]]["status"]
        if "error" in row:
            row["metadata_fetch_error"] = row.pop("error")
    registry["status"] = "inconclusive"
    registry["data_manifest"] = "download-manifest.json"
    registry["normalization_report"] = "reports/materialization.json"
    write_json(ROOT / "registry.json", registry)
    summary = open_external_budget(ROOT).summary()
    write_json(ROOT / "execution/budget-summary.json", summary)
    legacy = ROOT.parent / "extraction-benchmark-v2/execution/budget-and-integrity-v2.json"
    write_json(ROOT / "reports/readiness.json", {
        "status": "inconclusive", "scope": "completed_full_relation_calibration_and_frozen_nonfinal_QA_v2",
        "formal_pending_gates": ["numeric_thresholds_not_confirmed", "final_QA_scope_exceeds_existing_request_cap", "AgriNER_license_and_end_to_end_tasks_incomplete", "full_failure_and_release_audit_incomplete"],
        "downloaded_files_verified": len(downloads["files"]), "model_calls": summary["requests"],
        "budget": summary, "dataset_states": admissions,
        "legacy_checkpoint_sha256": hashlib.sha256(legacy.read_bytes()).hexdigest(),
        "legacy_checkpoint_path": str(legacy), "final_acceptance_run": False,
    })
    blocks = []
    for name, admission in admissions.items():
        stats = data["datasets"].get(name, {})
        evidence = " ".join(f'<a href="{html.escape(p, quote=True)}">{html.escape(Path(p).name)}</a>' for p in admission["evidence"])
        blocks.append(f'<section><h2>{html.escape(name)}</h2><p>{html.escape(admission["status"])} · {html.escape(admission["license"])}</p><p>{evidence}</p><pre>{html.escape(json.dumps(stats or admission, ensure_ascii=False, indent=2))}</pre><p>{html.escape("; ".join(admission.get("reasons", admission.get("release_gates", []))))}</p></section>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>外部评测接入审核</title>
<style>body{font:16px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;background:#f5f7fa;color:#182436}section{background:white;border:1px solid #d5dfeb;border-radius:10px;padding:20px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}a{color:#165bbb}.notice{padding:16px;background:#fff0c9;border-radius:8px}</style>
<h1>外部评测接入审核</h1><p class="notice">状态：inconclusive。当前为开发试跑与校准，尚无正式通过结论。499篇关系校准与来源修正版26题真实问答及语义复核已完成并冻结。可答完成率与支持数仍不足，最终范围和门槛未确认；内部500条仍只作历史诊断。</p>
<p>外部预算按用户新授权从零计量；旧账本保留。当前请求：REQUESTS；已用/预留token：TOKENS。上限2000万token / 5000次 / 并发2。</p>
<p><a href="registry.json">准入注册表</a> · <a href="reports/materialization.json">数据核验</a> · <a href="reports/data-resolutions-v1.json">分区与证据处理</a> · <a href="reports/readiness.json">未决门禁</a> · <a href="download-manifest.json">下载哈希</a> · <a href="budget-authorization.json">新预算授权</a> · <a href="reports/calibration-budget-v1.json">499篇预算</a> · <a href="runs/redocred-calibration-v1/score.json">完整校准评分</a> · <a href="reports/calibration-errors-v1.json">校准错误分解</a> · <a href="reports/calibration-coverage-v1.json">类型支持</a> · <a href="reports/calibration-result-manifest-v1.json">冻结清单</a> · <a href="reports/qa-scoring-chain-v3.json">25项离线验证</a> · <a href="reports/real-QA-pilot-v1.json">首轮诊断（来源元数据遗漏）</a> · <a href="reports/real-QA-pilot-v2.json">来源修正版真实对照</a> · <a href="runs/qa-pilot-v2-metadata/review.html">逐题原文与回答审核</a> · <a href="reports/QA-evidence-granularity-v2.json">正文事实召回诊断</a> · <a href="reports/extraction-threshold-proposal-v1.json">关系门槛草案</a> · <a href="reports/qa-threshold-proposal-v1.json">问答门槛草案</a> · <a href="reports/final-QA-full-scope-budget-v2.json">全量问答逐项预算缺口</a> · <a href="reports/qa-judge-repeat-stability-v1.json">同模型复判不稳定性</a></p>
''' + '<section><h2>最新核验与真实试跑</h2><p><a href="runs/redocred-pilot-v2-utf8/score.json">逐项成绩与区间</a> · <a href="reports/redocred-pilot-errors-v1.json">错误分解</a> · <a href="reports/relation-scorer-audit-v1.json">官方主指标核对</a> · <a href="reports/isolation-screen-v2.json">隔离复筛</a></p><pre>' + html.escape(json.dumps(updates, ensure_ascii=False, indent=2)) + '</pre></section>' + "".join(blocks) + '<section><h2>初次处理历史记录</h2><pre>' + html.escape(json.dumps(resolutions, ensure_ascii=False, indent=2)) + '</pre></section></html>'
    (ROOT / "review.html").write_text(page.replace("REQUESTS", str(summary["requests"])).replace("TOKENS", str(summary["tokens_charged_or_reserved"])), encoding="utf-8")
    print(json.dumps({"status": "inconclusive", "files_verified": len(downloads["files"]), "model_calls": summary["requests"], "review": str(ROOT / "review.html")}))


if __name__ == "__main__":
    main()
