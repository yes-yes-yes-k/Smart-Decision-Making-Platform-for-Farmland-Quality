"""Lossless source character selectors: all positions eligible, no generated text."""
import re


def indexed_block(block):
    text=block['text']
    import json
    cells=['c'+str(i)+'='+json.dumps(char,ensure_ascii=False) for i,char in enumerate(text)]
    return dict(block,source_cells='\n'.join(' '.join(cells[i:i+12]) for i in range(0,len(cells),12)),
                cell_range_semantics='start_cell_and_end_cell_inclusive')


def select(fragment,blocks):
    block=fragment['block_id']
    if not isinstance(block,str) or block not in blocks:
        raise ValueError('invalid_source_block')
    text=blocks[block]
    values=[]
    for name in ['start_cell','end_cell']:
        value=fragment[name]
        if not isinstance(value,str) or not re.fullmatch(r'c(?:0|[1-9]\d*)',value):
            raise ValueError('invalid_source_cell_id')
        values.append(int(value[1:]))
    start,last=values
    if not (0<=start<=last<len(text)):
        raise ValueError('source_cell_range_out_of_bounds')
    quote=text[start:last+1]
    position=-len(quote);occurrence=-1
    while position<start:
        position=text.find(quote,position+len(quote))
        occurrence+=1
        if position<0 or position>start:
            raise ValueError('cell_range_not_representable_by_nonoverlapping_occurrence')
    return dict(block_id=block,text=quote,occurrence=occurrence)


def materialize(raw,packet):
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    def walk(value):
        if isinstance(value,dict):
            if 'block_id' in value and ('start_cell' in value or 'end_cell' in value):
                fragment=select(value,blocks)
                return dict({k:walk(v) for k,v in value.items() if k not in {'block_id','start_cell','end_cell','text','occurrence'}},**fragment)
            if 'block_id' in value and 'text' in value:
                raise ValueError('response_fragments_must_select_source_cells')
            return {k:walk(v) for k,v in value.items()}
        if isinstance(value,list):return [walk(v) for v in value]
        return value
    return walk(raw)
