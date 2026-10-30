"""Budget scope authorized specifically for external-benchmark-v1."""
import hashlib
import json
from pathlib import Path

from framework.knowledge_graph.acceptance_budget import Budget


def open_external_budget(root: Path) -> Budget:
    root = Path(root).resolve()
    expected_root = Path(__file__).resolve().parents[2] / "artifacts/knowledge_platform/external-benchmark-v1"
    if root != expected_root.resolve():
        raise ValueError("external_budget_scope_cannot_move_or_reset")
    raw = (root / "budget-authorization.json").read_bytes()
    config = json.loads(raw)
    if config.get("scope") != "external-benchmark-v1" or config.get("caps") != {
        "total_tokens": 20_000_000, "requests": 5000, "concurrency": 2
    }:
        raise ValueError("unrecognized_external_budget_authorization")
    if config.get("ledger") != "execution/budget.sqlite3":
        raise ValueError("external_budget_ledger_path_changed")
    ledger = root / config["ledger"]
    budget = Budget(ledger, total=20_000_000, stability=20_000_000, requests=5000)
    # Bind the authorization to this ledger; a changed file must not silently
    # replace the policy used for already reserved calls.
    fingerprint = hashlib.sha256(raw).hexdigest()
    with budget.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS scope_authorization (scope TEXT PRIMARY KEY, sha256 TEXT NOT NULL)")
        existing = conn.execute("SELECT scope,sha256 FROM scope_authorization").fetchall()
        if existing and existing != [("external-benchmark-v1", fingerprint)]:
            raise ValueError("external_budget_authorization_changed")
        if not existing:
            count = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            if count:
                raise ValueError("refusing_reuse_unbound_existing_ledger")
            conn.execute("INSERT INTO scope_authorization VALUES (?,?)", ("external-benchmark-v1", fingerprint))
    return budget
