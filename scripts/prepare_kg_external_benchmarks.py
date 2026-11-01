"""Pin publisher metadata without executing downloaded code or calling models."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request


REPOS = {
    "agriner": ("Tec4Tric/AgriNER", ["README.md", "Agriculture entity taxonomy.csv", "relations", "split_data.py"]),
    "redocred": ("tonytan48/Re-DocRED", ["README.md", "LICENSE", "data/README.md", "evaluation.py"]),
    "qasper": ("allenai/qasper-led-baseline", ["README.md", "LICENSE", "scripts/evaluator.py", "fixtures/data/qasper_sample_small.json"]),
    "multihop_rag": ("yixuantt/MultiHop-RAG", ["README.md", "qa_evaluate.py", "retrieval_evaluate.py"]),
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "kg-external-benchmark-provenance/1"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    registry_path = root / "registry.json"
    if registry_path.exists():
        raise RuntimeError("registry_exists_use_existing_pinned_snapshot")
    rows = []
    for name, (repo, paths) in REPOS.items():
        folder = root / "sources" / name
        folder.mkdir(parents=True, exist_ok=True)
        entry = {"id": name, "publisher_repository": f"https://github.com/{repo}",
                 "admission": "pending_review", "model_calls": 0, "files": []}
        # Persist partial work on failure; subsequent retries must not rewrite prior bytes.
        try:
            metadata_bytes = fetch(f"https://api.github.com/repos/{repo}")
            metadata = json.loads(metadata_bytes)
            commit_bytes = fetch(f"https://api.github.com/repos/{repo}/commits/{metadata['default_branch']}")
            commit = json.loads(commit_bytes)["sha"]
            tree_bytes = fetch(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1")
            tree = json.loads(tree_bytes)
            if tree.get("truncated"):
                raise RuntimeError("publisher_tree_truncated")
            entry.update(commit=commit, github_license=metadata.get("license"), tree_sha=tree["sha"])
            for filename, blob in [("repository.json", metadata_bytes), ("commit.json", commit_bytes), ("tree.json", tree_bytes)]:
                dest = folder / filename
                if dest.exists() and dest.read_bytes() != blob:
                    raise RuntimeError(f"refusing_snapshot_overwrite:{dest}")
                dest.write_bytes(blob)
                entry["files"].append({"path": str(dest.relative_to(root)), "sha256": hashlib.sha256(blob).hexdigest(), "kind": "publisher_metadata"})
            available = {item["path"] for item in tree["tree"]}
            for path in paths:
                if path not in available:
                    raise RuntimeError(f"publisher_file_missing:{path}")
                url = f"https://raw.githubusercontent.com/{repo}/{commit}/{urllib.parse.quote(path)}"
                blob = fetch(url)
                dest = folder / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and dest.read_bytes() != blob:
                    raise RuntimeError(f"refusing_snapshot_overwrite:{dest}")
                dest.write_bytes(blob)
                entry["files"].append({"path": str(dest.relative_to(root)), "url": url, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob), "kind": "admission_evidence"})
        except Exception as exc:
            entry.update(admission="blocked_fetch", error=f"{type(exc).__name__}: {exc}")
        write_json(folder / "snapshot.json", entry)
        rows.append(entry)
        print(json.dumps({"dataset": name, "state": entry["admission"], "files": len(entry["files"])}), flush=True)
    registry = {"schema": "external-benchmark-registry-v1", "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "inconclusive", "datasets": rows, "model_calls": 0,
                "warning": "Repository code license alone does not establish dataset licensing; admission requires review."}
    write_json(registry_path, registry)
    return registry


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("artifacts/knowledge_platform/external-benchmark-v1"))
    prepare(parser.parse_args().root)
