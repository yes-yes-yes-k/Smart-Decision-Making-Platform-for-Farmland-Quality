"""Build the old-to-new span transfer for the re-parsed papers (R2.1 follow-up).

Reads the frozen M1 references and the R2.1 re-parse artefacts, maps every
quoted span by page anchor plus text alignment, and writes an auditable table.
No model call, no write to the corpus.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from framework.knowledge_graph.span_transfer import transfer_references

R1 = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1"
CASES = R1 / "r0-20261030/query-cases.json"
SOURCE_RUN = R1 / "r1-r2-20261030-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_parse():
    chunks, mapping, inputs = {}, {}, {}
    for folder in ("parsing", "parsing-additional"):
        for path in sorted((SOURCE_RUN / folder).glob("*.json")):
            if path.name == "summary.json":
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            document_id = int((data.get("document") or {}).get("document_id") or path.stem)
            chunks[document_id] = data["chunk_set"]["chunks"]
            mapping[document_id] = {row["old_chunk_index"]: row for row in data["legacy_mapping"]}
            inputs[document_id] = {"file": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
    return chunks, mapping, inputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="span-transfer-20261031-v1")
    args = parser.parse_args()
    out = R1 / args.run_id
    if out.exists():
        raise SystemExit("run id already exists")
    out.mkdir(parents=True)

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    chunks, mapping, inputs = load_parse()
    references = []
    for case in cases["cases"]:
        for subquestion in case.get("subquestions", []):
            for reference in subquestion.get("reference_evidence", []):
                if reference["document_id"] in chunks:
                    references.append(dict(reference, case_id=case["id"], subquestion_id=subquestion["id"]))
    report = transfer_references(references, chunks, mapping)
    report.update({"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                   "state": "transferred", "inputs": inputs,
                   "query_cases_sha256": sha256(CASES),
                   "method": "page_anchor_then_exact_normalized_aligned",
                   "min_alignment_ratio": 0.9,
                   "model_calls": 0,
                   "limits": ["page comes from legacy_mapping; a quote absent from that page stays unmapped",
                              "aligned mapping is a character match, not a semantic or layout certificate"]})
    (out / "span-transfer.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# R2.1 跨度转移", "",
             f"- run: `{args.run_id}`", f"- 参考证据：{report['summary']['total']} 条",
             f"- 已映射：{report['summary']['mapped']}（exact {report['summary']['exact']} / "
             f"normalized {report['summary']['normalized']} / aligned {report['summary']['aligned']}）",
             f"- 未映射：{report['summary']['unmapped']}", "",
             "| 用例 | 子问题 | 文献 | 旧块 | 新块 | 方法 | 分数 |", "| --- | --- | ---: | ---: | ---: | --- | ---: |"]
    for row in report["rows"]:
        lines.append(f"| {row.get('case_id', '')} | {row.get('subquestion_id', '')} | {row['document_id']} | "
                     f"{row['old_chunk_index']} | {row.get('chunk_index', '-')} | {row.get('method', 'unmapped')} | "
                     f"{row.get('score', '-')} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
