"""Source-only request construction and per-item strict-span diagnostics.

This is an annotation protocol check, not semantic certification or a scorer.
"""
import hashlib
import json
from pathlib import Path


def source_packet(sample, handbook):
    blocks=[]
    for key, text in [('chunk',sample['text']),
                      ('document_title',sample['document_title'])]:
        if not isinstance(text,str):
            raise ValueError('invalid_source_text')
        blocks.append(dict(block_id=key,kind=key,text=text,
            text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()))
    return dict(sample_id=sample['sample_id'],blocks=blocks,
                handbook=handbook,output_protocol='extraction-benchmark-v2-draft-1')


def literal_span(fragment,blocks):
    block=fragment['block_id']
    if block not in blocks:
        raise ValueError('unknown_block')
    text=blocks[block]
    start,end,occ=fragment['start'],fragment['end'],fragment['occurrence']
    if any(type(x) is not int for x in (start,end,occ)):
        raise ValueError('non_integer_position')
    quote=fragment['text']
    if not isinstance(quote,str) or not quote or not (0<=start<end<=len(text)) or text[start:end]!=quote:
        raise ValueError('span_not_literal')
    if occ<0:
        raise ValueError('negative_occurrence')
    positions=[]
    offset=0
    while True:
        position=text.find(quote,offset)
        if position<0:
            break
        positions.append(position)
        offset=position+len(quote)
    if occ>=len(positions) or positions[occ]!=start:
        raise ValueError('occurrence_span_conflict')
    return block,start,end


def validate_proposal(packet,proposal,schema):
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    entity_types={r['id'] for r in schema['entity_types']}
    relation_types={r['id']:r for r in schema['relation_types']}
    entities=proposal.get('entities')
    relations=proposal.get('relations')
    if not isinstance(entities,list) or not isinstance(relations,list):
        raise ValueError('entity_and_relation_lists_required')
    ids=[m.get('id') for m in entities if isinstance(m,dict)]
    repeated={i for i in ids if isinstance(i,str) and ids.count(i)>1}
    valid={}
    errors=[]
    seen=set()
    for i,entity in enumerate(entities):
        try:
            if entity['id'] in repeated:
                raise ValueError('duplicate_entity_id')
            if not isinstance(entity['id'],str) or not entity['id']:
                raise ValueError('missing_entity_id')
            if entity['type'] not in entity_types:
                raise ValueError('unknown_entity_type')
            span=literal_span(entity,blocks)
            key=span+(entity['type'],)
            if key in seen:
                raise ValueError('duplicate_entity_span')
            seen.add(key)
            valid[entity['id']]=entity
        except (ValueError,KeyError,TypeError) as exc:
            errors.append(dict(task='entity',index=i,error=str(exc)))
    valid_relations=[]
    relation_keys=set()
    for i,relation in enumerate(relations):
        try:
            src,tgt=valid[relation['source_id']],valid[relation['target_id']]
            definition=relation_types[relation['type']]
            if src['type'] not in definition['source_types'] or tgt['type'] not in definition['target_types']:
                raise ValueError('invalid_direction_or_endpoint_type')
            if relation['modality'] not in {'asserted','normative','hypothetical','negated','unknown'}:
                raise ValueError('invalid_modality')
            if not isinstance(relation.get('conditions'),list):
                raise ValueError('conditions_list_required')
            evidence=relation['evidence']
            if not isinstance(evidence,list) or not evidence:
                raise ValueError('relation_evidence_required')
            roles=set()
            for fragment in evidence:
                literal_span(fragment,blocks)
                if fragment.get('role') not in {'identity','assertion'}:
                    raise ValueError('evidence_role_required')
                roles.add(fragment['role'])
            if 'assertion' not in roles:
                raise ValueError('identity_only_does_not_establish_relation')
            key=(relation['type'],relation['source_id'],relation['target_id'],relation['modality'])
            if key in relation_keys:
                raise ValueError('duplicate_relation')
            relation_keys.add(key)
            valid_relations.append(relation)
        except (ValueError,KeyError,TypeError) as exc:
            errors.append(dict(task='relation',index=i,error=str(exc)))
    if not isinstance(proposal.get('normalization'),list):
        errors.append(dict(task='normalization',error='normalization_list_required'))
    masks=proposal.get('task_masks')
    if not isinstance(masks,dict) or any(masks.get(k) not in {'applicable','unknown','excluded'}
            for k in ('entities','relations','normalization')):
        errors.append(dict(task='quality',error='task_mask_proposals_required'))
    return dict(protocol_complete=not errors,errors=errors,
                literal_valid_entities=list(valid.values()),
                structurally_valid_relations=valid_relations,
                semantic_support_not_certified=True,
                masks_are_proposals_not_scoring_authority=True,
                partial_candidates_for_diagnostics_only=True)


def load_schema(root):
    return json.loads((Path(root)/'framework/knowledge_graph/schemas/minimal-cultivated-land-kg-schema-v1.json').read_text(encoding='utf-8'))
