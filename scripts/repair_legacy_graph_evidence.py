"""Restore legacy graph evidence only from verified persisted source spans."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalized_positions(text):
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    return ''.join(text[i] for i in positions), positions


def repair_graph_evidence(graph, chunks, documents, reviewed_reanchors):
    result = copy.deepcopy(graph)
    audit = []
    for relation in result['relations']:
        replacements = []
        for old in relation['evidence']:
            did = int(old['document_id'])
            document = documents[did]
            if not document['source_hash_verified']:
                raise ValueError('source_hash_not_verified')
            original_quote, _ = normalized_positions(old['quote'])
            page_chunks = sorted([c for c in chunks if int(c['metadata'].get('document_id', -1)) == did and c['metadata'].get('page') == old['page']], key=lambda c: int(c['metadata']['chunk_index']))
            matches = []
            for chunk in page_chunks:
                normalized, positions = normalized_positions(chunk['content'])
                offset = normalized.find(original_quote)
                if original_quote and offset >= 0:
                    matches.append((chunk, positions[offset], positions[offset + len(original_quote)-1]+1))
            mode = 'exact_whitespace_normalized'
            if matches:
                selected = matches[:1]
            else:
                plan = reviewed_reanchors.get(old['evidence_id'])
                if not plan or not plan.get('review_reason'):
                    raise ValueError('manual_source_review_required:' + old['evidence_id'])
                mode = 'reviewed_verbatim_reanchor'
                selected = []
                for locator in plan['locators']:
                    candidates = [c for c in chunks if int(c['metadata'].get('document_id', -1)) == did and c['metadata'].get('page') == locator['page'] and c['metadata'].get('chunk_index') == locator['chunk_index']]
                    if len(candidates) != 1:
                        raise ValueError('source_chunk_not_unique')
                    chunk = candidates[0]
                    start, end = locator.get('span_start', 0), locator.get('span_end', len(chunk['content']))
                    selected.append((chunk, start, end))
            ids = []
            for chunk, start, end in selected:
                meta = chunk['metadata']
                if meta.get('content_sha256') not in (None, '', document['file_hash']):
                    raise ValueError('persisted_content_hash_conflict')
                if meta.get('visibility_scope') != 'public':
                    raise ValueError('source_chunk_not_public')
                if not 0 <= start < end <= len(chunk['content']):
                    raise ValueError('invalid_source_span')
                quote = chunk['content'][start:end]
                identity = dict(document_id=did, content_sha256=document['file_hash'], chunk_index=int(meta['chunk_index']), page=int(meta['page']), span_start=start, span_end=end, quote_sha256=text_hash(quote))
                eid = 'evidence:' + text_hash(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':')))[:24]
                row = dict(old)
                row.update(identity, evidence_id=eid, quote=quote, legacy_evidence_id=old['evidence_id'], legacy_quote_sha256=text_hash(old['quote']), locator_repair_mode=mode)
                replacements.append(row)
                ids.append(eid)
            audit.append(dict(relation_id=relation['id'], legacy_evidence_id=old['evidence_id'], restored_evidence_ids=ids, mode=mode))
        unique = {row['evidence_id']: row for row in replacements}
        relation['evidence'] = list(unique.values())
    return result, audit
