"""Require model-selected verbatim text and coordinates to identify the same span."""
import copy
from .benchmark_cells import select

_SPAN_KEYS={'quote','start','end'}


def verify_selected_span(value,blocks):
    if not isinstance(value,dict) or not {'block_id',*_SPAN_KEYS}.issubset(value):
        raise ValueError('quoted_span_and_coordinates_required')
    if set(value)&{'start_cell','end_cell','text','occurrence'}:
        raise ValueError('mixed_legacy_and_quoted_span_protocol')
    block=value['block_id'];quote=value['quote'];start=value['start'];end=value['end']
    if block not in blocks:raise ValueError('unknown_source_block')
    if not isinstance(quote,str) or not quote:raise ValueError('empty_verbatim_quote')
    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(blocks[block]):
        raise ValueError('invalid_unicode_character_offsets')
    if blocks[block][start:end]!=quote:raise ValueError('quote_coordinate_mismatch')
    try:cell=select(dict(block_id=block,start_cell=f'c{start}',end_cell=f'c{end-1}'),blocks)
    except ValueError as exc:raise ValueError('quoted_span_not_reconstructable') from exc
    return dict(block_id=block,text=quote,start=start,end=end,occurrence=cell['occurrence'])


def materialize_quoted(packet,value):
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    def walk(item):
        if isinstance(item,list):return [walk(v) for v in item]
        if not isinstance(item,dict):return item
        if _SPAN_KEYS&item.keys():
            span=verify_selected_span(item,blocks)
            return {**{k:walk(v) for k,v in item.items() if k not in _SPAN_KEYS},**span}
        if item.keys()&{'start_cell','end_cell'}:
            raise ValueError('legacy_character_selector_forbidden_in_quoted_protocol')
        return {k:walk(v) for k,v in item.items()}
    return walk(copy.deepcopy(value))


def selected_entity(surface,block_id,start,end):
    return dict(block_id=block_id,quote=surface,start=start,end=end)


def selected_evidence(surface,block_id,start,end,role):
    return dict(block_id=block_id,quote=surface,start=start,end=end,role=role)
