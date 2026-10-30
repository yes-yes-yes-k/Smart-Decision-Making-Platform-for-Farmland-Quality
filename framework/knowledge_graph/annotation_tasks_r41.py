"""Explicit occurrence semantics for the next revision; r4 artifacts remain immutable."""
import copy
from .annotation_tasks_r4 import annotate as annotate_r4

OCCURRENCE_RULE='''fragment.occurrence 的含义：同一个 text 在同一个 block_id 中从0起的出现序号。首次出现必须填0，第二次填1。
它不是mention列表编号，也不是整个文档中其他片段的累计序号。不同text各自从0计数。
若片段只出现一次，occurrence必须为0。例：文本“甲乙甲”，text“甲”两次分别为0和1；text“乙”首次仍为0。
空白对齐后按同一片段计数，不修改字母、标点或OCR字形；无法确定重复指代则留待复核，不猜测位置。'''

def clarify(options):
    updated=copy.deepcopy(options)
    updated['messages'][0]['content']+='\n'+OCCURRENCE_RULE
    def walk(node):
        if isinstance(node,dict):
            properties=node.get('properties',{})
            if set(properties)=={'block_id','text','occurrence'}:
                properties['occurrence']['description']='Zero-based occurrence of THIS SAME text within THIS SAME block; first=0. Not a mention-list index.'
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(updated.get('response_format',{}))
    return updated

async def annotate(visible,create,*,attempts=1):
    async def wrapped(**options):return await create(**clarify(options))
    return await annotate_r4(visible,wrapped,attempts=attempts)
