"""Freeze M2 measured evidence and source code without touching prior versions."""
import ctypes
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.audit_knowledge_m2_integrity import digest
OUT = REPO/"artifacts/knowledge_platform/operations-m2-v1"


def read(name):
    return json.loads((OUT/name).read_text(encoding="utf-8"))


def main():
    manifest = OUT/"completion-manifest-v1.json"
    if manifest.exists():
        data = read(manifest.name)
        for name, expected in data["files"].items():
            if digest(OUT/name) != expected:
                raise ValueError("frozen_M2_asset_changed:"+name)
        print(json.dumps({"state": "frozen_unchanged", "files": len(data["files"])})); return
    warm, updates, product, validation, integrity, post = [read(name) for name in
        ("runtime-warm-v1.json", "incremental-v1.json", "product-v1.json", "validation-v1.json", "integrity-v1.json", "source-store-postcheck-v1.json")]
    if validation["state"] != "passed" or validation["total_passed"] != 81 or integrity["state"] != "verified":
        raise ValueError("validation_or_integrity_incomplete")
    for relative, expected in validation["test_sha256"].items():
        if digest(REPO/relative) != expected:
            raise ValueError("validated_tests_changed")
    if warm["startup"]["source_reads"]["text_rows"] or any(item["metrics"]["tokenized_rows"] for item in warm["startup"]["lexical"].values()):
        raise ValueError("warm_start_rebuilt_corpus")
    if updates["final"]["vectors"] != 112168 or sum(item["rows"] for item in updates["final"]["lexical"].values()) != 112168 or any(item["pending_operations"] for item in updates["final"]["lexical"].values()):
        raise ValueError("incremental_conservation_failed")
    if not updates["document_restored_exactly"] or updates["metadata_update_retokenized_rows"]:
        raise ValueError("incremental_scope_or_recovery_failed")
    if product["queue_counts"] != {"cancelled": 2, "completed": 7, "failed": 1, "invalidated": 1} or product["backlog"] or product["total_jobs"] != 11:
        raise ValueError("queue_conservation_failed")
    if post["database"]["documents_total"] != 1173 or post["database"]["eligible_public_documents"] != 1144 or post["vector"]["embedding_rows"] != 112168 or post["database"]["KG_tables_across_schemas"]:
        raise ValueError("original_database_postcheck_failed")
    # Capture actual physical memory as a hardware observation, not a process SLO.
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), *[(name, ctypes.c_ulonglong) for name in
            ("total_physical", "available_physical", "total_pagefile", "available_pagefile", "total_virtual", "available_virtual", "available_extended_virtual")]]
    status = MemoryStatus(); status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("physical_memory_measurement_failed")
    hardware = {**post["hardware"], "physical_memory_bytes": status.total_physical, "processor": platform.processor(),
        "python_version": platform.python_version(), "sqlite_version": sqlite3.sqlite_version,
        "versions": warm["versions"], "PostgreSQL": post["database"]["server_version"]}
    (OUT/"hardware-v1.json").write_text(json.dumps(hardware, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    code = [REPO/name for name in ("framework/vector_store/lexical_index.py", "framework/vector_store/bm25_store.py", "framework/vector_store/chroma_store.py",
        "framework/knowledge_graph/research_retrieval.py", "framework/knowledge_graph/research_service.py", "framework/knowledge_graph/research_sources.py",
        "framework/knowledge_graph/research_store.py", "framework/knowledge_graph/operational_measurements.py", "framework/api/routes/literature_evidence.py",
        "tests/test_lexical_operations_m2.py", "tests/test_chroma_lexical_m2.py", "tests/test_research_evidence.py", "tests/test_research_corpus_m2.py", "tests/test_research_admission_m2.py",
        "tests/test_bm25_store.py", "tests/test_kb_persistence.py", "tests/test_collection_routing.py", "tests/test_hybrid_search.py")]
    code += list((REPO/"scripts").glob("*knowledge_m2*.py"))
    code += [REPO/"docs"/name for name in ("knowledge-engineering-m2-results.md", "knowledge-engineering-m3-capacity-proposal.md")]
    code += [REPO/"openspec/changes/enable-literature-evidence-comparison"/name for name in ("tasks.md", "design.md")]
    for path in code:
        target = OUT/"frozen-code"/path.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    title = "M2 千篇库增量运行审核"
    review = "<!doctype html><html lang=zh-CN><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>"+title+"</title><style>body{font:16px/1.7 system-ui;max-width:1050px;margin:40px auto;padding:0 22px;color:#142b38}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd8dd;padding:10px;text-align:left}a{color:#135e86}pre{white-space:pre-wrap;background:#f2f6f8;padding:18px}.note{background:#fff1d0;padding:18px}</style><h1>"+title+"</h1><p class=note>M2隔离实现与验证完成。未部署、未运行10k/100k、未证明抽取质量。新增模型调用0，新增发布0。</p>"
    values = [("实际分块", "112168（1173份混合文献）"), ("合格来源", "1144份/107505块；642份为论文"), ("暖启动", "3.965秒；全库正文读取0、分词0"),
        ("词法后端40次", "P50 0.073秒 / P95 0.411秒"), ("真实HTTP来源检索8次", "P50 0.583秒 / 最大1.000秒；包含PG/原件哈希"),
        ("单篇102块删除＋重放", "3.209秒；不含新embedding"), ("队列11任务", "完成7 / 取消2 / 失败1 / 失效1；积压0"), ("测试", "58项独立＋23项既有兼容 = 81项通过")]
    review += "<table><tr><th>项目</th><th>实测</th></tr>"+"".join("<tr><td>"+html.escape(a)+"</td><td>"+html.escape(b)+"</td></tr>" for a,b in values)+"</table>"
    review += "<h2>报告与原始证据</h2><ul>"+"".join("<li><a href='"+name+"'>"+html.escape(name)+"</a></li>" for name in
        ("frozen-code/docs/knowledge-engineering-m2-results.md", "frozen-code/docs/knowledge-engineering-m3-capacity-proposal.md", "baseline-v1.json", "runtime-bootstrap-v1.json", "runtime-warm-v1.json", "incremental-v1.json", "product-v1.json", "validation-v1.json", "integrity-v1.json", "source-store-postcheck-v1.json", "hardware-v1.json"))+"</ul>"
    review += "<h2>使用边界</h2><p>混合检索重放原有向量，仅测HNSW成本；不含embedding生成或回答。语义比较仅十篇及两个既有pending记录，不将待审候选提升为知识。下一步确认M3资源和数值后，先隔离10k，再100k。</p></html>"
    (OUT/"review.html").write_text(review, encoding="utf-8")
    files = {path.relative_to(OUT).as_posix(): digest(path) for path in sorted(OUT.rglob("*")) if path.is_file()
        and path.relative_to(OUT).parts[0] not in {"runtime", "corpus"} and path != manifest}
    result = {"state": "M2_isolated_current_corpus_implementation_and_verification_complete", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "actual_chunks": 112168, "source_documents": 1173, "eligible_documents": 1144, "tests_passed": 81,
        "model_calls": 0, "published_claims_added": 0, "network_service_deployed": False,
        "M3_state": "not_started_targets_proposed_not_confirmed", "files": files}
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"state": result["state"], "frozen_files": len(files), "tests_passed": 81, "model_calls": 0}))


if __name__ == "__main__":
    main()
