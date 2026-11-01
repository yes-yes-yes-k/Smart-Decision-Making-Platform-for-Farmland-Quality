"""R4.2 Run U1-U5 comparison with frozen configurations.

Zero model calls. For each case and each configuration (C1/C2/C3),
runs PublishedCorpusSearch and records:
- document-level hits (which documents appeared)
- evidence-level hits (which chunks appeared)
- graph contributing_hits (C3 only)
- evidence swap-in/swap-out between configurations

Usage:
    .venv/Scripts/python.exe scripts/run_r4_2_comparison.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = PROJECT_ROOT / "artifacts/knowledge_platform/research-extraction-v2/r4-20261031-comparison-config/frozen-comparison-config-v1.json"
CASES_PATH = PROJECT_ROOT / "artifacts/knowledge_platform/retrieval-quality-r1/r0-20261030/query-cases.json"
OUTPUT_DIR = PROJECT_ROOT / "artifacts/knowledge_platform/research-extraction-v2/r4-20261031-comparison-config"


def main() -> None:
    from flask import Flask
    from framework.models.user import db
    from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
    from framework.knowledge_graph.research_sources import PublishedResearchSources
    from framework.knowledge_graph.graph_expander import BoundedGraphExpander
    from framework.vector_store.chroma_store import vector_store

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cases_data = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    app = Flask("r4-2-comparison")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=(
            f"postgresql+psycopg://{os.getenv('DB_USER','postgres')}:"
            f"{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST','localhost')}:"
            f"{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME')}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(PROJECT_ROOT / "uploads"))
    context = app.app_context()
    context.push()

    source = PublishedResearchSources(
        app.config["SQLALCHEMY_DATABASE_URI"], UPLOAD_FOLDER
    )

    configs = config["retrieval_configurations"]
    primary_cases = [c for c in cases_data["cases"] if c["kind"] == "primary"]

    results = []
    for case in primary_cases:
        case_id = case["id"]
        query = case["query"]
        ref_doc_ids = case.get("reference_document_ids", [])

        print(f"\n{'='*60}")
        print(f"Case {case_id}: {query[:50]}...")
        print(f"  Reference docs: {ref_doc_ids}")

        case_result = {"case_id": case_id, "query": query, "reference_document_ids": ref_doc_ids, "configurations": {}}

        for config_name, cfg in configs.items():
            search = PublishedCorpusSearch(
                vector_store, source,
                enhance_recall=cfg["enhance_recall"],
                rerank=cfg.get("rerank"),
                window=cfg.get("window", 0),
                graph_expander=BoundedGraphExpander() if cfg.get("graph") else None,
            )
            request = {
                "query": query,
                "limit": cfg["limit"],
                "source_scope": cfg["source_scope"],
            }
            if cfg.get("graph"):
                request["graph"] = True

            try:
                response = search.search(owner_id=1, request=request)
                doc_ids = [d["document_id"] for d in response.get("documents", [])]
                source_count = len(response.get("sources", []))
                graph_info = response.get("graph", {})
                state = response.get("state", "unknown")
                error = None
            except Exception as exc:
                doc_ids, source_count, graph_info, state = [], 0, {}, "error"
                error = str(exc)[:200]

            cfg_result = {
                "config": config_name,
                "state": state,
                "document_ids": doc_ids,
                "document_count": len(doc_ids),
                "source_count": source_count,
                "graph": graph_info,
                "error": error,
                # Reference coverage
                "reference_docs_in_results": [d for d in ref_doc_ids if d in doc_ids],
                "reference_docs_missing": [d for d in ref_doc_ids if d not in doc_ids],
            }
            case_result["configurations"][config_name] = cfg_result
            print(f"  {config_name}: docs={len(doc_ids)} sources={source_count} "
                  f"ref_hit={len(cfg_result['reference_docs_in_results'])}/{len(ref_doc_ids)} "
                  f"graph={graph_info.get('state','n/a')}:{graph_info.get('contributing_hits',0)}")

        # Evidence swap-in/swap-out between C1 and C3
        c1_docs = set(case_result["configurations"]["C1_lexical_vector_hybrid"]["document_ids"])
        c3_docs = set(case_result["configurations"]["C3_graph_associated"]["document_ids"])
        case_result["swap_analysis"] = {
            "C1_only": sorted(c1_docs - c3_docs),
            "C3_only": sorted(c3_docs - c1_docs),
            "common": sorted(c1_docs & c3_docs),
            "graph_added": sorted(c3_docs - c1_docs),
        }
        # Also C1 vs C2
        c2_docs = set(case_result["configurations"]["C2_same_domain_filter"]["document_ids"])
        case_result["scope_analysis"] = {
            "C1_only": sorted(c1_docs - c2_docs),
            "C2_only": sorted(c2_docs - c1_docs),
            "common": sorted(c1_docs & c2_docs),
        }
        results.append(case_result)

    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    for r in results:
        c1 = r["configurations"]["C1_lexical_vector_hybrid"]
        c3 = r["configurations"]["C3_graph_associated"]
        ref_hit = len(c1["reference_docs_in_results"])
        ref_total = len(c1["reference_docs_missing"]) + ref_hit
        graph_added = len(r["swap_analysis"]["graph_added"])
        print(f"  {r['case_id']}: ref_hit={ref_hit}/{ref_total} "
              f"C1_docs={c1['document_count']} C3_docs={c3['document_count']} "
              f"graph_added={graph_added}")

    output_path = OUTPUT_DIR / "comparison-results-v1.json"
    output_path.write_text(
        json.dumps({"schema_version": "r4-2-comparison-results-v1", "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nResults written to {output_path}")
    context.pop()


if __name__ == "__main__":
    main()
