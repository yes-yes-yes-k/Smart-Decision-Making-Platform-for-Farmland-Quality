"""Protect explicitly frozen result paths against accidental re-scoring."""
import json
from pathlib import Path


def require_mutable(root, *targets):
    root = Path(root).resolve()
    targets = [Path(target).resolve() for target in targets]
    for manifest in (root/"reports").glob("*result-manifest-*.json"):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for name in data.get("files", {}):
            frozen = (root/name).resolve()
            if any(frozen == target or target in frozen.parents for target in targets):
                raise ValueError("frozen_result_requires_new_version:" + str(frozen))
