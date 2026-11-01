"""Canonical, source-only publisher metadata; never inferred from questions."""
import json

from framework.knowledge_graph.external_qa_retrieval import make_index_inputs as body_inputs


def metadata_block(document, dataset):
    native = document.get("native_article", document)
    fields = ("title", "author", "source", "published_at", "category", "url") if dataset == "multihop_rag" else ("title",)
    value = {key: native[key] for key in fields if key in native and native[key] is not None}
    return {"id": "source_metadata", "kind": "source_metadata",
            "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}


def make_index_inputs(documents, limit=4000):
    # Metadata has its own units. Original body unit identities and source spans
    # remain unchanged, permitting exact request-hash reuse of body extraction.
    chunks, units = [], []
    for document in documents:
        for metadata in (False, True):
            blocks = [block for block in document["blocks"] if (block["id"] == "source_metadata") == metadata]
            extra_chunks, extra_units = body_inputs([{**document, "blocks": blocks}], limit)
            chunks.extend(extra_chunks)
            units.extend(extra_units)
    return chunks, units
