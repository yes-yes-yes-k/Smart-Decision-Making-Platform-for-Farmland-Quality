"""Isolated real vector/JsonGraphStore evaluation; no reference labels are accepted."""
import math
from .acceptance_data import digest,normalized
from .stores import JsonGraphStore
from .contracts import GraphQuery

def build_prediction_graph(predictions,sources,release_id):
    from .evaluation_v4 import input_digest,digest as text_digest
    partitions={s['partition'] for s in sources.values()}
    if len(partitions)!=1:raise ValueError('graph_sources_must_have_one_partition')
    nodes={};relations=[]
    seen=set()
    for p in predictions:
        if p.get('origin')!='candidate_extractor':raise ValueError('only_candidate_predictions_may_build_graph')
        if p['sample_id'] in seen:raise ValueError('duplicate_graph_prediction')
        seen.add(p['sample_id'])
        source=sources[p['sample_id']];a=p.get('annotation')
        if a is None:continue
        visible=dict(sample_id=source['sample_id'],blocks=[dict(block_id=k,kind=k,text=t,text_sha256=text_digest(t)) for k,t in [('chunk',source['text']),('document_title',source['document_title'])]])
        if a['sample_id']!=p['sample_id'] or a['input_sha256']!=input_digest(visible):raise ValueError('graph_prediction_source_mismatch')
        ids={}
        for m in a['mentions']:
            name=m['fragment']['text'];node='entity:'+digest(m['type']+':'+''.join(name.split()))[:24]
            ids[m['id']]=node;nodes[node]=dict(id=node,type=m['type'],name=name)
        for r in a['relations']:
            if r['modality'] not in ('asserted','normative'):continue
            ev=[dict(document_id=source['document_id'],content_sha256=source['file_sha256'],chunk_index=source['chunk_index'],page=source['page'],
                span_start=e['span_start'],span_end=e['span_end'],quote_sha256=e['text_sha256']) for e in r['evidence'] if e['block_id']=='chunk']
            if not ev:continue
            relations.append(dict(id='pred-relation:'+digest(p['sample_id']+str(len(relations)))[:24],source=ids[r['source']],target=ids[r['target']],type=r['relation_type'],evidence=ev))
    graph=dict(schema_version='minimal-cultivated-land-kg-schema-v1',release=dict(release_id=release_id),entities=list(nodes.values()),relations=relations,evaluation_partition=next(iter(partitions)))
    if not JsonGraphStore(graph).health()['ready']:raise ValueError('candidate_graph_backend_not_ready')
    return graph

class FrozenRetrieval:
    def __init__(self,corpus,*,embedding_identity,graph=None):
        self.corpus={r['sample_id']:r for r in corpus};self.embedding_identity=embedding_identity
        if len(self.corpus)!=len(corpus):raise ValueError('duplicate_corpus_sample')
        dims={len(r['embedding']) for r in corpus}
        if len(dims)!=1 or not dims or 0 in dims:raise ValueError('missing_or_mixed_frozen_embeddings')
        if any(not math.isfinite(v) for r in corpus for v in r['embedding']):raise ValueError('nonfinite_embedding')
        self.dimension=next(iter(dims));self.graph=JsonGraphStore(graph) if graph is not None else None
        if self.graph and not self.graph.health()['ready']:raise ValueError('graph_backend_not_ready')
        self.lookup={(r['document_id'],r['chunk_index']):sid for sid,r in self.corpus.items()}
    def retrieve(self,question,query_embedding,*,embedding_identity,arm,partition,top_k=5):
        if embedding_identity!=self.embedding_identity or len(query_embedding)!=self.dimension:raise ValueError('query_embedding_identity_mismatch')
        if any(not math.isfinite(v) for v in query_embedding):raise ValueError('nonfinite_query_embedding')
        if arm not in ('vector','graphrag') or top_k!=5:raise ValueError('frozen_retrieval_configuration_changed')
        qnorm=math.sqrt(sum(x*x for x in query_embedding))
        if not qnorm:raise ValueError('zero_query_embedding')
        ranked=[]
        for sid,c in self.corpus.items():
            if c['partition']!=partition:continue
            e=c['embedding'];norm=math.sqrt(sum(x*x for x in e));score=sum(x*y for x,y in zip(e,query_embedding))/(qnorm*norm) if norm else -1
            ranked.append((score,sid))
        ranked.sort(key=lambda r:(-r[0],r[1]));vector=[sid for score,sid in ranked[:top_k]];chosen=[]
        if arm=='graphrag':
            if self.graph is None:raise ValueError('graph_backend_unavailable_no_vector_fallback_in_comparison')
            if self.graph.graph.get('evaluation_partition')!=partition:raise ValueError('graph_partition_mismatch')
            q=normalized(question);seeds=[e['id'] for e in self.graph.graph['entities'] if len(normalized(e['name']))>=2 and normalized(e['name']) in q][:5]
            if seeds:
                result=self.graph.neighbors(GraphQuery(entity_ids=tuple(seeds),max_hops=2,top_k=5))
                for e in result.evidence_references:
                    sid=self.lookup.get((e.get('document_id'),e.get('chunk_index')))
                    if sid and self.corpus[sid]['partition']==partition and sid not in chosen:chosen.append(sid)
                    if len(chosen)==3:break
        for sid in vector:
            if sid not in chosen:chosen.append(sid)
            if len(chosen)==top_k:break
        return [dict(sample_id=sid,text=self.corpus[sid]['text'][:1600]) for sid in chosen]

def validate_answer(answer,retrieved,corpus):
    """Quotes must be literal and inside the actual prompt, not merely in the corpus."""
    provided={r['sample_id']:r['text'] for r in retrieved}
    if type(answer.get('abstain')) is not bool or not isinstance(answer.get('answer'),str):raise ValueError('invalid_answer_shape')
    citations=answer.get('citations',[])
    for e in citations:
        sid=e['sample_id'];start,end=e['span_start'],e['span_end']
        if sid not in provided or type(start) is not int or type(end) is not int or not 0<=start<end<=len(provided[sid]):raise ValueError('citation_outside_retrieved_context')
        if not e['text'] or corpus[sid]['text'][start:end]!=e['text'] or provided[sid][start:end]!=e['text']:raise ValueError('citation_quote_not_bound')
    if not answer['abstain'] and not citations:raise ValueError('substantive_answer_needs_citation')
    return dict(answer,citation_bindings_validated=True,retrieved_sample_ids=[r['sample_id'] for r in retrieved])
