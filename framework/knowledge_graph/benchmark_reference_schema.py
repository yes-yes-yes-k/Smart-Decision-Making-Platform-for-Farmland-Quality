"""Required review fields for positive, negative, and empty candidate inputs."""


def build_reference_schema(candidate,ontology):
    def obj(p):return dict(type='object',properties=p,required=list(p),additionalProperties=False)
    def enum(values):return dict(type='string',enum=list(values))
    def arr(items):return dict(type='array',items=items)
    string=dict(type='string')
    cell=obj(dict(block_id=enum(['chunk','document_title']),start_cell=dict(type='string',pattern=r'^c(0|[1-9][0-9]*)$'),end_cell=dict(type='string',pattern=r'^c(0|[1-9][0-9]*)$')))
    ids=[d['id'] for d in candidate['decisions']]
    # An empty enum is invalid JSON Schema; empty inventories require an empty
    # review array instead, without excluding the negative source task.
    decision=obj(dict(id=enum(ids) if ids else string,decision=enum(['include','exclude','uncertain']),
        entity_type=dict(anyOf=[enum(['indicator','obstacle','measure','standard']),dict(type='null')]),reason=string,evidence=arr(cell)))
    addition=obj(dict(id=string,type=enum(['indicator','obstacle','measure','standard']),decision=enum(['include']),reason=string,fragment=cell))
    def reviews(count):
        row=obj(dict(index=dict(type='integer',minimum=0,maximum=max(0,count-1)),status=enum(['supported','unsupported','uncertain']),reason=string,evidence=arr(cell)))
        return dict(type='array',items=row,minItems=count,maxItems=count)
    relation=obj(dict(type=enum([r['id'] for r in ontology['relation_types']]),source_id=string,target_id=string,
        modality=enum(['asserted','normative','hypothetical','negated','unknown']),conditions=arr(string),
        evidence=arr(obj(dict(**cell['properties'],role=enum(['identity','assertion'])))),review_reason=string))
    masks=obj(dict(task=enum(['entities','relations','normalization']),block_id=enum(['chunk','document_title']),
        status=enum(['unknown','excluded']),reason=string,evidence=arr(cell)))
    schema=obj(dict(decision_reviews=dict(type='array',items=decision,minItems=len(ids),maxItems=len(ids)),
        additions=arr(addition),relation_reviews=reviews(len(candidate['relations'])),add_relations=arr(relation),
        normalization_reviews=reviews(len(candidate['normalization'])),mask_overrides=arr(masks),
        policy_conflicts=arr(obj(dict(issue=string,reason=string)))))
    return dict(type='json_schema',json_schema=dict(name='reference_support_review',strict=True,schema=schema))
