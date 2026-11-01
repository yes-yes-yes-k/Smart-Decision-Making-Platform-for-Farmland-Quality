import copy
import json
from pathlib import Path

from scripts.check_knowledge_platform_components import compare_sboms, validate_sbom


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "governance" / "knowledge-platform" / "oss-components.cdx.json"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_open_source_component_sbom_is_valid_and_version_pinned():
    payload = _manifest()

    assert validate_sbom(payload) == []
    assert {component["name"] for component in payload["components"]} == {
        "Microsoft GraphRAG",
        "OpenSPG / KAG",
        "Apache AGE",
        "Neo4j GraphRAG for Python",
    }
    assert all(component["version"] != "latest" for component in payload["components"])
    age = next(item for item in payload["components"] if item["name"] == "Apache AGE")
    assert age["version"] == "1.6.0-pg16"
    assert age["hashes"] == [{
        "alg": "SHA-256",
        "content": "16aa423d20a31aed36a3313244bf7aa00731325862f20ed584510e381f2feaed",
    }]


def test_noop_component_diff_passes_without_a_golden_evaluation():
    payload = _manifest()

    report = compare_sboms(payload, copy.deepcopy(payload))

    assert report["passed"] is True
    assert report["changes"] == []
    assert report["requires_golden_evaluation"] is False


def test_version_upgrade_is_blocked_until_gold_evaluation_passes():
    baseline = _manifest()
    candidate = copy.deepcopy(baseline)
    candidate["components"][0]["version"] = "3.4.0"
    candidate["components"][0]["properties"][2]["value"] = "future-revision"

    blocked = compare_sboms(baseline, candidate)
    accepted = compare_sboms(baseline, candidate, golden_report={"passed": True})

    assert blocked["passed"] is False
    assert "golden_evaluation_required" in blocked["blockers"]
    assert accepted["passed"] is True
    assert {change["change"] for change in accepted["changes"]} == {
        "version", "source_revision",
    }


def test_license_or_source_change_requires_manual_supply_chain_review():
    baseline = _manifest()
    candidate = copy.deepcopy(baseline)
    candidate["components"][0]["licenses"] = [{"license": {"id": "GPL-3.0-only"}}]
    candidate["components"][0]["externalReferences"][0]["url"] = (
        "https://example.invalid/fork"
    )

    report = compare_sboms(baseline, candidate, golden_report={"passed": True})

    assert report["passed"] is False
    assert any("licenses" in blocker for blocker in report["blockers"])
    assert any("vcs" in blocker for blocker in report["blockers"])
