"""Validate the knowledge-platform CycloneDX baseline and gate upgrades."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


ALLOWED_LICENSES = {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"}
ALLOWED_STATUSES = {"evaluation", "selected", "deferred"}


def _properties(component: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(item.get("name")): str(item.get("value"))
        for item in component.get("properties") or []
        if item.get("name") is not None and item.get("value") is not None
    }


def _licenses(component: Mapping[str, Any]) -> tuple[str, ...]:
    values = []
    for item in component.get("licenses") or []:
        license_data = item.get("license") or {}
        identifier = license_data.get("id") or license_data.get("name")
        if identifier:
            values.append(str(identifier))
    return tuple(sorted(set(values)))


def _references(component: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(item.get("type")): str(item.get("url"))
        for item in component.get("externalReferences") or []
        if item.get("type") and item.get("url")
    }


def validate_sbom(payload: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if payload.get("bomFormat") != "CycloneDX":
        issues.append("bomFormat must be CycloneDX")
    if str(payload.get("specVersion") or "") not in {"1.5", "1.6"}:
        issues.append("CycloneDX specVersion must be 1.5 or 1.6")
    components = payload.get("components") or []
    if not components:
        issues.append("at least one open-source component is required")
        return issues
    seen: set[str] = set()
    for component in components:
        ref = str(component.get("bom-ref") or "")
        location = ref or str(component.get("name") or "unnamed")
        if not ref:
            issues.append(f"{location}: bom-ref is required")
        elif ref in seen:
            issues.append(f"{location}: duplicate bom-ref")
        seen.add(ref)
        version = str(component.get("version") or "").strip()
        if not version or version.casefold() == "latest":
            issues.append(f"{location}: exact version is required")
        licenses = _licenses(component)
        if not licenses:
            issues.append(f"{location}: SPDX license is required")
        disallowed = set(licenses) - ALLOWED_LICENSES
        if disallowed:
            issues.append(f"{location}: licenses are not approved: {sorted(disallowed)}")
        references = _references(component)
        if "vcs" not in references or not references["vcs"].startswith("https://"):
            issues.append(f"{location}: an HTTPS vcs source is required")
        properties = _properties(component)
        status = properties.get("culti:status")
        if status not in ALLOWED_STATUSES:
            issues.append(f"{location}: invalid culti:status")
        if not properties.get("culti:source-revision"):
            issues.append(f"{location}: culti:source-revision is required")
        verification = properties.get("culti:artifact-verification")
        if status == "selected" and verification != "verified-sha256":
            issues.append(f"{location}: selected components require verified-sha256")
        if status == "selected":
            hashes = component.get("hashes") or []
            if not any(item.get("alg") == "SHA-256" and item.get("content") for item in hashes):
                issues.append(f"{location}: selected components require a SHA-256 hash")
    return issues


def _component_index(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(component["bom-ref"]): component
        for component in payload.get("components") or []
        if component.get("bom-ref")
    }


def compare_sboms(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    golden_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blockers = [f"candidate_invalid: {issue}" for issue in validate_sbom(candidate)]
    changes: list[dict[str, Any]] = []
    old = _component_index(baseline)
    new = _component_index(candidate)
    for ref in sorted(set(old) | set(new)):
        before = old.get(ref)
        after = new.get(ref)
        if before is None:
            changes.append({"component": ref, "change": "added"})
            blockers.append(f"new_component_review_required: {ref}")
            continue
        if after is None:
            changes.append({"component": ref, "change": "removed"})
            blockers.append(f"component_removal_review_required: {ref}")
            continue
        fields = {
            "version": (before.get("version"), after.get("version")),
            "licenses": (_licenses(before), _licenses(after)),
            "vcs": (_references(before).get("vcs"), _references(after).get("vcs")),
            "source_revision": (
                _properties(before).get("culti:source-revision"),
                _properties(after).get("culti:source-revision"),
            ),
        }
        for field, (left, right) in fields.items():
            if left != right:
                changes.append({
                    "component": ref,
                    "change": field,
                    "before": left,
                    "after": right,
                })
                if field in {"licenses", "vcs"}:
                    blockers.append(f"manual_supply_chain_review_required: {ref}:{field}")
    requires_golden = any(
        change["change"] in {"added", "removed", "version", "source_revision"}
        for change in changes
    )
    if requires_golden and not (golden_report or {}).get("passed"):
        blockers.append("golden_evaluation_required")
    return {
        "schema": "knowledge-platform-component-diff-v1",
        "passed": not blockers,
        "requires_golden_evaluation": requires_golden,
        "changes": changes,
        "blockers": sorted(set(blockers)),
    }


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--golden-report", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    candidate = _load(args.candidate)
    if args.baseline:
        result = compare_sboms(
            _load(args.baseline),
            candidate,
            golden_report=_load(args.golden_report) if args.golden_report else None,
        )
    else:
        issues = validate_sbom(candidate)
        result = {
            "schema": "knowledge-platform-component-validation-v1",
            "passed": not issues,
            "issues": issues,
        }
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8", newline="\n")
    print(output, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
