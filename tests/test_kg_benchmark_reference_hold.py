import json
import pytest
from framework.knowledge_graph.benchmark_reference_hold import require_no_semantic_hold


def test_evidence_spans_cannot_override_semantic_release_hold(tmp_path):
    target=tmp_path/'semantic-quality-audit-v1/report.json';target.parent.mkdir()
    target.write_text(json.dumps(dict(status='fail',release_hold=True)),encoding='utf-8')
    with pytest.raises(ValueError,match='semantic_reference_quality_hold'):
        require_no_semantic_hold(tmp_path)


def test_no_active_hold_does_not_imply_semantic_acceptance(tmp_path):
    # Other source/reference/threshold gates remain mandatory at their callers.
    require_no_semantic_hold(tmp_path)
