"""Bind model-quoted verbatim text to deterministic source positions."""
import copy


def materialize_quote(value,blocks):
    if not isinstance(value,dict) or not {'block_id','quote'}.issubset(value):
        raise ValueError('source_quote_required')
    if {'start','end','start_cell','end_cell'}&value.keys():
        raise ValueError('model_offsets_not_allowed_in_quote_v2')
    block=value['block_id'];quote=value['quote']
    if block not in blocks:raise ValueError('unknown_source_block')
    if not isinstance(quote,str) or not quote:raise ValueError('empty_source_quote')
    hits=[];cursor=0
    while True:
        pos=blocks[block].find(quote,cursor)
        if pos<0:break
        hits.append(pos);cursor=pos+len(quote)
    if not hits:raise ValueError('quote_not_found_verbatim')
    occurrence=value.get('occurrence')
    if len(hits)==1:
        if occurrence not in (None,0):raise ValueError('invalid_unique_quote_occurrence')
        occurrence=0
    else:
        if type(occurrence) is not int or occurrence<0 or occurrence>=len(hits):
            raise ValueError('repeated_quote_requires_valid_occurrence')
    start=hits[occurrence]
    result={k:copy.deepcopy(v) for k,v in value.items() if k not in {'quote','occurrence'}}
    result.update(text=quote,start=start,end=start+len(quote),occurrence=occurrence)
    return result


def materialize_quoted(packet,value):
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    def walk(item):
        if isinstance(item,list):return [walk(v) for v in item]
        if not isinstance(item,dict):return item
        if 'block_id' in item and 'quote' in item:
            return materialize_quote(item,blocks)
        if {'start','end','start_cell','end_cell'}&item.keys():
            raise ValueError('model_offsets_not_allowed_in_quote_v2')
        return {k:walk(v) for k,v in item.items()}
    return walk(copy.deepcopy(value))
