"""Versioned acceptance run selection without modifying historical configurations."""
import json
from pathlib import Path

def active_output(root):
    base=Path(root)/'artifacts/knowledge_platform'
    selector=base/'acceptance-active-run.json'
    if not selector.exists():return base/'acceptance-v1'
    name=json.loads(selector.read_text(encoding='utf-8'))['directory']
    if not isinstance(name,str) or not name.startswith('acceptance-') or '/' in name or '\\' in name or name in ('.','..'):
        raise ValueError('invalid_acceptance_run_directory')
    return base/name

def shared_budget(root,output):
    output=Path(output);metadata=output/'shared-budget.json'
    if not metadata.exists():return output/'budget.sqlite3'
    path=(Path(root)/json.loads(metadata.read_text(encoding='utf-8'))['path']).resolve()
    if Path(root).resolve() not in path.parents:raise ValueError('shared_budget_outside_workspace')
    return path
