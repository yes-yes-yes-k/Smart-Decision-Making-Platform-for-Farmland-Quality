"""A failed semantic audit cannot be overridden by necessary span checks."""
import json
from pathlib import Path


def require_no_semantic_hold(root):
    report=Path(root)/'semantic-quality-audit-v1/report.json'
    if report.exists():
        audit=json.loads(report.read_text(encoding='utf-8'))
        if audit.get('release_hold',False):
            raise ValueError('semantic_reference_quality_hold_requires_versioned_resolution')
