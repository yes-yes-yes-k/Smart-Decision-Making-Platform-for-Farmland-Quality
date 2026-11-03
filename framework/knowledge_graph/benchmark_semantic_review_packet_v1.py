"""Show adjudicators the exact materialized candidate text, not selector IDs alone."""
import copy


def explicit_candidate(proposal):
    """Return source-fragment text beside every source coordinate, preserving IDs."""
    result=copy.deepcopy(proposal)
    for entity in result.get('entities',[]):
        entity['selected_surface']=dict(block_id=entity['block_id'],quote=entity['text'],
            start=entity['start'],end=entity['end'])
    for relation in result.get('relations',[]):
        relation['assertion_windows']=[dict(block_id=e['block_id'],quote=e['text'],
            start=e['start'],end=e['end']) for e in relation.get('evidence',[]) if e.get('role')=='assertion']
    return result
