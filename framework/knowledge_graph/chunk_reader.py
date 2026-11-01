"""Bounded source lookup using Chroma's public API, without BM25 startup."""
from pathlib import Path


class WorkerPublishedChunkReader:
    def __init__(self, persist_dir=None, *, client=None):
        if client is None:
            if not persist_dir or not Path(persist_dir).is_dir():
                raise ValueError("published_vector_directory_missing")
            from framework.vector_store.runtime_temp import prepare_chroma_temp_directory
            prepare_chroma_temp_directory()
            import chromadb
            from chromadb.config import Settings
            client = chromadb.PersistentClient(path=str(Path(persist_dir).resolve()),
                settings=Settings(anonymized_telemetry=False, allow_reset=False))
        self.client = client

    def read_published_chunks(self, *, document_id, content_sha256, expected_count):
        where = {"$and": [{"document_id": int(document_id)},
                             {"content_sha256": str(content_sha256)},
                             {"visibility_scope": "public"}]}
        return self._read(where, int(expected_count)+1)

    def _read(self, where, limit):
        rows = []
        # Refresh collection names each task: uploads can introduce a new domain.
        for item in self.client.list_collections():
            name = item.name if hasattr(item, "name") else str(item)
            collection = self.client.get_collection(name=name, embedding_function=None)
            data = collection.get(where=where, limit=limit-len(rows),
                                  include=["documents", "metadatas"])
            rows.extend(dict(content=text, metadata=metadata) for text, metadata in
                        zip(data.get("documents") or [], data.get("metadatas") or []))
            if len(rows) >= limit:
                break
        return rows


class VerifiedLegacyShadowReader(WorkerPublishedChunkReader):
    """Shadow-only bridge: prove legacy chunks against the original source bytes.

    Does not update Chroma metadata. Production workers retain strict hash reads.
    """
    def __init__(self, persist_dir, *, source, upload_root, client=None):
        super().__init__(persist_dir, client=client)
        self.source, self.upload_root = source, Path(upload_root)
        self.legacy_verified = False

    def read_published_chunks(self, *, document_id, content_sha256, expected_count):
        current = super().read_published_chunks(document_id=document_id,
            content_sha256=content_sha256, expected_count=expected_count)
        if len(current) == expected_count:
            return current
        from .candidate_pipeline import CandidatePipelineError
        from framework.rag.kg_runtime import sha256_file
        if int(document_id) != self.source["id"] or content_sha256 != self.source["file_hash"]:
            raise CandidatePipelineError("legacy_source_mismatch", "shadow source identity differs")
        rows = self._read({"$and": [{"document_id": int(document_id)},
                                     {"visibility_scope": "public"}]}, expected_count+1)
        rows.sort(key=lambda row: int(row["metadata"].get("chunk_index", -1)))
        if (len(rows) != expected_count or
                any(row["metadata"].get("content_sha256") not in {None, "", content_sha256} for row in rows)):
            raise CandidatePipelineError("legacy_source_reindex_required", "legacy source cannot be bound")
        original = Path(self.source["file_path"])
        if not original.is_absolute():
            original = self.upload_root / original
        if not original.is_file() or sha256_file(original) != content_sha256:
            raise CandidatePipelineError("legacy_source_hash_mismatch", "original bytes do not match")
        from framework.upload.document_parser import parse_document
        from framework.upload.chunker import split_text_with_pages
        pages = parse_document(str(original), self.source["file_type"], page_aware=True)
        if not isinstance(pages, list) or not pages or not isinstance(pages[0], tuple):
            raise CandidatePipelineError("legacy_source_reindex_required", "page-aware source is required")
        rebuilt = split_text_with_pages(pages)
        if len(rebuilt) != len(rows) or sha256_file(original) != content_sha256:
            raise CandidatePipelineError("legacy_source_reindex_required", "source chunks differ")
        verified = []
        for index, ((text, page), row) in enumerate(zip(rebuilt, rows)):
            meta = row["metadata"]
            if (row["content"] != text or int(meta.get("page", -1)) != page or
                    int(meta.get("chunk_index", -1)) != index):
                raise CandidatePipelineError("legacy_source_reindex_required", "source chunks differ")
            verified.append(dict(content=text, metadata={**meta, "content_sha256": content_sha256}))
        self.legacy_verified = True
        return verified
