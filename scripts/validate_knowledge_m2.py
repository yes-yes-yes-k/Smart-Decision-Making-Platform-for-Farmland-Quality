"""Capture necessary isolated regression results without app startup hooks."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
OUT = REPO/"artifacts/knowledge_platform/operations-m2-v1"


def main():
    target = OUT/"validation-v1.json"
    if target.exists():
        raise ValueError("validation_exists_use_new_version")
    modules = ["test_chroma_lexical_m2", "test_lexical_operations_m2", "test_research_evidence", "test_research_corpus_m2", "test_research_admission_m2"]
    commands = [[sys.executable, "-m", "unittest", *["tests."+name for name in modules]],
        [sys.executable, "scripts/validate_knowledge_m2_compatibility.py"]]
    results = []
    for index, command in enumerate(commands):
        completed = subprocess.run(command, cwd=REPO, env={**os.environ, "PYTHONUTF8": "1"}, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=120)
        log = OUT/("validation-"+str(index)+"-v1.log")
        log.write_text(completed.stdout, encoding="utf-8")
        match = re.search(r"Ran (\d+) tests", completed.stdout) if index == 0 else re.search(r"(\d+) passed", completed.stdout)
        results.append({"command": " ".join(command[1:]), "exit_code": completed.returncode,
            "passed": int(match.group(1)) if match and completed.returncode == 0 else 0,
            "log": log.name, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
        print(json.dumps(results[-1]), flush=True)
        if completed.returncode:
            break
    files = [REPO/"tests"/(name+".py") for name in modules]
    report = {"state": "passed" if len(results) == 2 and all(row["exit_code"] == 0 for row in results) else "failed",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(), "runs": results, "total_passed": sum(row["passed"] for row in results),
        "test_sha256": {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "model_calls": 0, "full_app_started": False, "production_database_used": False}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if report["state"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
