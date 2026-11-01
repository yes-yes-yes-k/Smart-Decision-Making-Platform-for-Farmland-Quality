"""Download pinned data with explicit local-research admission evidence."""
from pathlib import Path
import hashlib
import http.client
import json
import sys
import urllib.error

from prepare_kg_external_benchmarks import fetch, write_json


ROOT = Path("artifacts/knowledge_platform/external-benchmark-v1")
HF = {
    "qasper": ("allenai/qasper", "fdc9d8214fbab5dd782958601db4d678e6934a54", ["README.md", "qasper.py"]),
    "multihop_rag": ("yixuantt/MultiHopRAG", "71ac0d0bd1f951d2d6b70311f7d2ae404e1ffa82", ["README.md", "MultiHopRAG.json", "corpus.json"]),
    "docred_upstream": ("thunlp/docred", "7985b4e0371e6c61a756feb41b7b27becf71c666", ["README.md", "data/rel_info.json.gz"]),
}


def save(dataset, filename, url, kind):
    dest = ROOT / "sources" / dataset / filename
    record_path = dest.with_name(dest.name + ".source.json")
    if dest.exists() and record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record["url"] != url or record["sha256"] != hashlib.sha256(dest.read_bytes()).hexdigest():
            raise ValueError(f"frozen_download_mismatch:{dest}")
        return record
    if dest.exists():
        raise ValueError(f"refusing_untracked_overwrite:{dest}")
    # One retry for transient transport failure, never execute downloaded code.
    for attempt in range(2):
        try:
            blob = fetch(url)
            break
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead):
            if attempt:
                raise
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    record = {"path": str(dest.relative_to(ROOT)), "url": url, "sha256": hashlib.sha256(blob).hexdigest(),
              "bytes": len(blob), "kind": kind}
    write_json(record_path, record)
    print(json.dumps({"saved": record["path"], "bytes": len(blob)}), flush=True)
    return record


def main():
    registry = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
    downloads = []
    for dataset, (repo, sha, paths) in HF.items():
        for path in paths:
            downloads.append(save(dataset, "huggingface/" + path,
                                  f"https://huggingface.co/datasets/{repo}/resolve/{sha}/{path}",
                                  "data" if path.endswith((".json", ".gz")) else "data_license_or_loader"))
    redocred = next(row for row in registry["datasets"] if row["id"] == "redocred")
    for split in ("train", "dev", "test"):
        name = f"data/{split}_revised.json"
        downloads.append(save("redocred", name,
                              f"https://raw.githubusercontent.com/tonytan48/Re-DocRED/{redocred['commit']}/{name}", "data"))
    # Loader and archive names are pinned to publisher release v0.3.
    for name in ("qasper-train-dev-v0.3.tgz", "qasper-test-and-evaluator-v0.3.tgz"):
        downloads.append(save("qasper", name, "https://qasper-dataset.s3.us-west-2.amazonaws.com/" + name, "data_archive"))
    # Complete the failed metadata transfer at the same pinned revision.
    multi = next(row for row in registry["datasets"] if row["id"] == "multihop_rag")
    for path in ("qa_evaluate.py", "retrieval_evaluate.py"):
        downloads.append(save("multihop_rag", "reviewed/" + path,
                              f"https://raw.githubusercontent.com/yixuantt/MultiHop-RAG/{multi['commit']}/{path}", "official_scorer_source"))
    write_json(ROOT / "download-manifest.json", {"status": "downloaded_not_evaluated", "model_calls": 0, "files": downloads})


if __name__ == "__main__":
    main()
