"""Lossless row/column source selectors with all Unicode positions eligible."""
import json
import re

WIDTH=10


def indexed_block(block):
    rows=[]
    for offset in range(0,len(block['text']),WIDTH):
        values=[]
        for column,char in enumerate(block['text'][offset:offset+WIDTH]):
            display=json.dumps(char,ensure_ascii=False) if char.isspace() or char in '|\\"' else char
            values.append(str(column)+':'+display)
        rows.append('r'+str(offset//WIDTH)+' '+ ' '.join(values))
    return dict(block,source_cells='\n'.join(rows),
                cell_selector='r{row}c{column}; both endpoints inclusive; ten columns per row')


def to_linear(raw):
    def walk(value):
        if isinstance(value,dict):
            result={k:walk(v) for k,v in value.items()}
            for key in ['start_cell','end_cell']:
                if key not in result:continue
                match=re.fullmatch(r'r(0|[1-9]\d*)c([0-9])',str(result[key]))
                if not match:raise ValueError('invalid_compact_source_cell_id')
                result[key]='c'+str(int(match[1])*WIDTH+int(match[2]))
            return result
        if isinstance(value,list):return [walk(v) for v in value]
        return value
    return walk(raw)


def from_linear(raw):
    def walk(value):
        if isinstance(value,dict):
            result={k:walk(v) for k,v in value.items()}
            for key in ['start_cell','end_cell']:
                if key not in result:continue
                match=re.fullmatch(r'c(0|[1-9]\d*)',str(result[key]))
                if not match:raise ValueError('invalid_linear_source_cell_id')
                n=int(match[1]);result[key]='r'+str(n//WIDTH)+'c'+str(n%WIDTH)
            return result
        if isinstance(value,list):return [walk(v) for v in value]
        return value
    return walk(raw)
