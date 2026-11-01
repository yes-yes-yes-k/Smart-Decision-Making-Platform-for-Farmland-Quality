"""Deterministic source-only sampling and document-grouped benchmark splits."""
from collections import defaultdict
import hashlib
import re


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalized_text(text):
    return ''.join(c.casefold() for c in text if c.isalnum())


def document_order(documents, seed):
    groups=defaultdict(lambda:defaultdict(list))
    for doc in documents:
        labels=doc.get('domain_labels') or ['unclassified']
        groups[doc['kind']][sorted(labels)[0]].append(doc)
    for domains in groups.values():
        for key in domains:
            domains[key].sort(key=lambda d:digest(f'{seed}:doc:{d["file_sha256"]}'))
    ordered=[]
    while any(rows for domains in groups.values() for rows in domains.values()):
        for kind in sorted(groups):
            domains=groups[kind]
            for domain in sorted(domains):
                if domains[domain]:
                    ordered.append(domains[domain].pop(0))
    return ordered


def sample_document_chunks(doc, chunks, *, seed, count, seen):
    eligible=[]
    indices=set()
    for chunk in chunks:
        meta=chunk['metadata'];index=meta.get('chunk_index')
        if (meta.get('document_id')!=doc['id'] or meta.get('content_sha256')!=doc['file_sha256']
                or meta.get('visibility_scope')!='public' or not isinstance(index,int)
                or index<0 or not isinstance(meta.get('page'),int) or meta['page']<=0
                or not isinstance(chunk.get('content'),str) or not chunk['content'].strip()):
            raise ValueError(f'invalid source provenance in document {doc["id"]}')
        if index in indices:
            raise ValueError(f'duplicate chunk index in document {doc["id"]}')
        indices.add(index)
        eligible.append(chunk)
    eligible.sort(key=lambda c:c['metadata']['chunk_index'])
    buckets=defaultdict(list)
    for rank,chunk in enumerate(eligible):
        bucket=min(3,rank*4//max(1,len(eligible)))
        buckets[bucket].append(chunk)
    result=[]
    for bucket in sorted(buckets):
        buckets[bucket].sort(key=lambda c:digest(f'{seed}:{doc["file_sha256"]}:{c["metadata"]["chunk_index"]}'))
    while len(result)<count and any(buckets.values()):
        for bucket in sorted(buckets):
            if not buckets[bucket] or len(result)>=count:
                continue
            chunk=buckets[bucket].pop(0);content=chunk['content'];meta=chunk['metadata']
            normalized=normalized_text(content)
            if not normalized or digest(normalized) in seen:
                continue
            seen.add(digest(normalized))
            result.append(dict(sample_id='kg-source:'+digest(f'{doc["file_sha256"]}:{meta["chunk_index"]}:{digest(content)}')[:24],
                document_id=doc['id'],document_title=doc['title'],document_kind=doc['kind'],
                domain_labels=doc.get('domain_labels',[]),file_sha256=doc['file_sha256'],
                chunk_index=meta['chunk_index'],page=meta['page'],text=content,
                text_sha256=digest(content),normalized_text_sha256=digest(normalized),position_quartile=bucket,
                quality_flags=[flag for flag,condition in (
                    ('short_text',len(normalized)<80),('reference_heading',bool(re.search(r'参考文献|References',content,re.I))),
                    ('replacement_character','\ufffd' in content)) if condition],
                annotation_status='unannotated',gold_approved=False))
    return result


def assign_splits(samples,seed):
    """Whole source files stay together. Near duplicate sampled texts union groups."""
    parent={s['file_sha256']:s['file_sha256'] for s in samples}
    def find(key):
        while parent[key]!=key:
            parent[key]=parent[parent[key]];key=parent[key]
        return key
    def union(a,b):
        a,b=find(a),find(b)
        parent[max(a,b)]=min(a,b)
    # MinHash-style exact fingerprint bands propose near duplicates; verify by
    # character shingles before grouping, so a short boilerplate cannot join all.
    band_index=defaultdict(list)
    prior=[]
    for sample in samples:
        text=normalized_text(sample['text'])
        shingles={text[i:i+5] for i in range(max(1,len(text)-4))}
        hashes=sorted(int(digest(s)[:16],16) for s in shingles)
        signatures=hashes[:8]
        possible=set()
        for signature in signatures:
            possible.update(band_index[signature])
        for index in possible:
            other,other_shingles=prior[index]
            if len(shingles & other_shingles)/max(1,len(shingles|other_shingles))>=0.85:
                union(sample['file_sha256'],other['file_sha256'])
        index=len(prior);prior.append((sample,shingles))
        for signature in signatures:
            band_index[signature].append(index)
    groups=defaultdict(list)
    for sample in samples:
        groups[find(sample['file_sha256'])].append(sample)
    counts={'development':0,'validation':0,'test':0}
    targets={'development':0.7,'validation':0.15,'test':0.15}
    for key,rows in sorted(groups.items(),key=lambda pair:digest(f'{seed}:split:{pair[0]}')):
        split=max(targets,key=lambda name:targets[name]*len(samples)-counts[name])
        for sample in rows:
            sample['split']=split;sample['leakage_group']=key
        counts[split]+=len(rows)
    return counts
