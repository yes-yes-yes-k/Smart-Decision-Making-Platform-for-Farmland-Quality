"""Produce non-secret environment evidence for the OpenSPG/KAG offline POC."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Mapping


def _command_version(command: list[str]) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if not executable:
        return {"available": False, "version": None}
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "version": None}
    raw_output = completed.stdout or completed.stderr
    if b"\x00" in raw_output[:32]:
        decoded = raw_output.decode("utf-16-le", errors="replace")
    else:
        decoded = raw_output.decode("utf-8", errors="replace")
    output = decoded.replace("\ufffd", "?").strip().splitlines()
    return {
        "available": completed.returncode == 0,
        "version": output[0] if output else None,
    }


def evaluate_probe(checks: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers = []
    if not checks["docker_cli"]["available"]:
        blockers.append("docker_cli_missing")
    if not checks["docker_compose"]["available"]:
        blockers.append("docker_compose_missing")
    if not checks["python_modules"]["kag"]:
        blockers.append("kag_module_missing")
    if not checks["python_modules"]["knext"]:
        blockers.append("knext_module_missing")
    if not checks["openspg_server_configured"]:
        blockers.append("openspg_server_not_configured")
    if not checks["model_provider_configured"]:
        blockers.append("model_provider_not_configured")
    return not blockers, blockers


def probe_environment(
    *,
    openspg_server_configured: bool = False,
    model_provider_configured: bool = False,
) -> dict[str, Any]:
    docker_cli = _command_version(["docker", "--version"])
    docker_compose = _command_version(["docker", "compose", "version"])
    checks = {
        "docker_cli": docker_cli,
        "docker_compose": docker_compose,
        "wsl_cli": _command_version(["wsl", "--version"]),
        "python_modules": {
            "kag": importlib.util.find_spec("kag") is not None,
            "knext": importlib.util.find_spec("knext") is not None,
        },
        "openspg_server_configured": openspg_server_configured,
        "model_provider_configured": model_provider_configured,
    }
    ready, blockers = evaluate_probe(checks)
    return {
        "schema": "openspg-kag-environment-probe-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready_for_offline_poc": ready,
        "blockers": blockers,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "checks": checks,
        "requirements_source": [
            "https://github.com/OpenSPG/KAG#411-engine--dependent-image-installation",
            "https://github.com/OpenSPG/KAG/tree/master/kag/examples/medicine",
        ],
        "secrets_recorded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--server-configured", action="store_true")
    parser.add_argument("--model-configured", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    report = probe_environment(
        openspg_server_configured=args.server_configured,
        model_provider_configured=args.model_configured,
    )
    # ASCII escaping keeps diagnostics printable in Windows GBK shells while
    # preserving the original Unicode content in JSON.
    output = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8", newline="\n")
    print(output, end="")
    return 2 if args.require_ready and not report["ready_for_offline_poc"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
