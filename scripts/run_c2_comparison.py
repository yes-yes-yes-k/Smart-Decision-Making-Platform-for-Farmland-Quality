"""R4.2 C2 same-domain filter rerun using full app context.

Uses create_app() to properly initialize the vector store (Chroma).
Compares C1 (papers only) vs C2 (all_qualified: papers + standards +
policies + guidelines) for U1-U5.

Usage:
    .venv/Scripts/python.exe scripts/run_c2_comparison.py
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

CASES_PATH = PROJECT_ROOT / "artifacts/knowledge_platform/retrieval-quality-r1/r0-20261030/query-cases.json"
OUTPUT_DIR = PROJECT_ROOT / "artifacts/knowledge_platform/research-extraction-v2/r4-20261031-comparison-config"


def main() -> None:
    from framework.api.app import create_app
    from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
    from framework.knowledge_graph.research_sources import PublishedResearchSources
    from framework.models.user import db

    app = create_app()
    cases_data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    primary_cases = [c for c in cases_data["cases"] if c["kind"] == "primary"]

    with app.app_context():
        source = app.extensions.get("literature_evidence_source_adapter")
        if source is None:
            # Fallback: create directly
            source = PublishedResearchSources(
                app.config["SQLALCHEMY_DATABASE_URI"],
                app.config.get("UPLOAD_FOLDER", str(PROJECT_ROOT / "uploads")),
            )

        vector_store = None
        try:
            from framework.vector_store.chroma_store import vector_store
        except Exception as exc:
            print(f"vector_store import failed: {exc}")
            return

        configs = {
            "C1_papers": {"source_scope": "papers", "limit": 20},
            "C2_all_qualified": {"source_scope": "all_qualified", "limit": 20},
        }

        results = []
        for case in primary_cases:
            case_id = case["id"]
            query = case["query"]
            ref_doc_ids = case.get("reference_document_ids", [])
            print(f"\nCase {case_id}: {query[:40]}...")

            case_result = {"case_id": case_id, "reference_document_ids": ref_doc_ids, "configs": {}}
            for config_name, cfg in configs.items():
                search = PublishedCorpusSearch(vector_store, source, enhance_recall=True)
                request = {"query": query, "limit": cfg["limit"], "source_scope": cfg["source_scope"]}
                try:
                    response = search.search(owner_id=1, request=request)
                    doc_ids = [d["document_id"] for d in response.get("documents", [])]
                    state = response.get("state", "unknown")
                    error = None
                except Exception as exc:
                    doc_ids, state, error = [], "error", str(exc)[:200]
                cfg_result = {
                    "config": config_name,
                    "state": state,
                    "document_ids": doc_ids,
                    "document_count": len(doc_ids),
                    "reference_docs_in_results": [d for d in ref_doc_ids if d in doc_ids],
                    "error": error,
                }
                case_result["configs"][config_name] = cfg_result
                ref_hit = len(cfg_result["reference_docs_in_results"])
                print(f"  {config_name}: docs={len(doc_ids)} ref_hit={ref_hit}/{len(ref_doc_ids)} state={state}")

            # Swap analysis
            c1_docs = set(case_result["configs"]["C1_papers"]["document_ids"])
            c2_docs = set(case_result["configs"]["C2_all_qualified"]["document_ids"])
            case_result["swap_analysis"] = {
                "C1_only": sorted(c1_docs - c2_docs),
                "C2_only": sorted(c2_docs - c1_docs),
                "common": sorted(c1_docs & c2_docs),
                "C2_new_docs": sorted(c2_docs - c1_docs),
            }
            swap = case_result["swap_analysis"]
            if swap["C2_only"]:
                print(f"  C2 added: {swap['C2_only']}")
            if swap["C1_only"]:
                print(f"  C1 only: {swap['C1_only']}")
            results.append(case_result)

        # Summary
        print(f"\n{'='*60}")
        print("C1 vs C2 Summary")
        print(f"{'='*60}")
        total_c2_new = 0
        for r in results:
            c2_new = len(r["swap_analysis"]["C2_only"])
            total_c2_new += c2_new
            c1 = r["configs"]["C1_papers"]
            c2 = r["configs"]["C2_all_qualified"]
            print(f"  {r['case_id']}: C1_docs={c1['document_count']} C2_docs={c2['document_count']} "
                  f"C2_new={c2_new} ref_hit_C1={len(c1['reference_docs_in_results'])} "
                  f"ref_hit_C2={len(c2['reference_docs_in_results'])}")
        print(f"\nTotal C2 new documents: {total_c2_new}")

        output_path = OUTPUT_DIR / "c2-comparison-results-v1.json"
        output_path.write_text(
            json.dumps({"schema_version": "r4-2-c2-results-v1", "results": results,
                        "total_c2_new_documents": total_c2_new},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
