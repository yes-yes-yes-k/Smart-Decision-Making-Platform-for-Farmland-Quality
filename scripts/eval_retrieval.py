"""检索质量评估：基于标注查询集计算 hit_rate@K 与 MRR。

用法: python scripts/eval_retrieval.py --queries tests/fixtures/eval_queries.yaml --top-k 5 --out eval.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.vector_store.chroma_store import vector_store
from framework.rag.category_router import route_category


def load_queries(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["queries"]


def evaluate(queries, top_k=5):
    results = []
    hits = 0
    reciprocal_ranks = []
    for q in queries:
        normalized = q["query"]
        category = route_category(normalized)
        retrieval = vector_store.hybrid_search(
            normalized, category=category, n_results=top_k,
        )
        retrieved_doc_names = [r.get("metadata", {}).get("source") for r in retrieval.get("results", [])]
        expected = set(q.get("expected_doc_ids") or [])
        # hit@K: 命中任一 expected
        hit = any(d in expected for d in retrieved_doc_names)
        # MRR: 首个命中的倒数排名
        rr = 0.0
        for rank, d in enumerate(retrieved_doc_names, start=1):
            if d in expected:
                rr = 1.0 / rank
                break
        if hit:
            hits += 1
        reciprocal_ranks.append(rr)
        results.append({
            "query": normalized,
            "expected": list(expected),
            "retrieved": retrieved_doc_names,
            "hit": hit,
            "reciprocal_rank": rr,
        })
    summary = {
        "n": len(queries),
        "hit_rate": hits / max(len(queries), 1),
        "mrr": sum(reciprocal_ranks) / max(len(reciprocal_ranks), 1),
    }
    return {"queries": results, "summary": summary}


def main():
    ap = argparse.ArgumentParser(description="检索质量评估")
    ap.add_argument("--queries", required=True, help="标注查询集 YAML 路径")
    ap.add_argument("--top-k", type=int, default=5, help="Top-K 检索数量")
    ap.add_argument("--out", default="eval.json", help="输出 JSON 路径")
    args = ap.parse_args()

    queries = load_queries(args.queries)
    result = evaluate(queries, top_k=args.top_k)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[eval] hit_rate={result['summary']['hit_rate']:.2%} mrr={result['summary']['mrr']:.2%}")


if __name__ == "__main__":
    main()
