"""Cross-check the model's verbatim surface against selected source cells."""
from .benchmark_cells import select


def materialize_dual(raw,packet):
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    def walk(value):
        if isinstance(value,list):return [walk(v) for v in value]
        if not isinstance(value,dict):return value
        if 'block_id' in value and any(k in value for k in ['text','start_cell','end_cell']):
            if not all(k in value for k in ['text','start_cell','end_cell']):
                raise ValueError('verbatim_text_and_both_cells_required')
            chosen=select(value,blocks)
            if value['text']!=chosen['text']:raise ValueError('verbatim_text_cell_disagreement')
            return dict({k:walk(v) for k,v in value.items() if k not in ['block_id','text','start_cell','end_cell','occurrence']},**chosen)
        return {k:walk(v) for k,v in value.items()}
    return walk(raw)


def materialized_candidate_view(candidate,packet):
    """Show literal selected content to a reviewer without adding label votes."""
    from .benchmark_cells import materialize
    return materialize(candidate,packet)
