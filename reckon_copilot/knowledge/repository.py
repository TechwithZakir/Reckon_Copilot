from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from reckon_copilot.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    KnowledgeStatus,
)


class KnowledgeRepository:
    def save_source(self, source: KnowledgeSource) -> KnowledgeSource: ...
    def get_source(self, source_id: str) -> KnowledgeSource | None: ...
    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument: ...
    def save_chunks(self, chunks: Iterable[KnowledgeChunk]) -> list[KnowledgeChunk]: ...
    def chunks(self) -> list[KnowledgeChunk]: ...
    def document(self, document_id: str) -> KnowledgeDocument | None: ...
    def source(self, source_id: str) -> KnowledgeSource | None: ...
    def retire_source_chunks(self, source_id: str, except_hash: str | None = None) -> None: ...


class InMemoryKnowledgeRepository(KnowledgeRepository):
    def __init__(self):
        self.sources: dict[str, KnowledgeSource] = {}
        self.documents: dict[str, KnowledgeDocument] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}

    def save_source(self, source: KnowledgeSource) -> KnowledgeSource:
        self.sources[source.source_id] = source
        return source

    def get_source(self, source_id: str) -> KnowledgeSource | None:
        return self.sources.get(source_id)

    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        existing = self.documents.get(document.document_id)
        if existing and existing.content_hash == document.content_hash:
            return existing
        self.documents[document.document_id] = document
        return document

    def save_chunks(self, chunks: Iterable[KnowledgeChunk]) -> list[KnowledgeChunk]:
        saved: list[KnowledgeChunk] = []
        for chunk in chunks:
            existing = self._chunks.get(chunk.chunk_id)
            if existing and existing.content_hash == chunk.content_hash:
                saved.append(existing)
                continue
            self._chunks[chunk.chunk_id] = chunk
            saved.append(chunk)
        return saved

    def chunks(self) -> list[KnowledgeChunk]:
        return list(self._chunks.values())

    def document(self, document_id: str) -> KnowledgeDocument | None:
        return self.documents.get(document_id)

    def source(self, source_id: str) -> KnowledgeSource | None:
        return self.sources.get(source_id)

    def retire_source_chunks(self, source_id: str, except_hash: str | None = None) -> None:
        for chunk_id, chunk in list(self._chunks.items()):
            document = self.documents.get(chunk.document_id)
            if chunk.source_id == source_id and (not except_hash or document and document.content_hash != except_hash):
                self._chunks[chunk_id] = replace(chunk, status=KnowledgeStatus.STALE)


class FrappeKnowledgeRepository(KnowledgeRepository):
    """Frappe-compatible storage adapter placeholder.

    Unit tests use the in-memory repository. A live bench can wire this adapter to the
    DocTypes introduced in Phase 4 without changing retriever/RAG callers.
    """

    def __init__(self, frappe_module=None):
        if frappe_module is None:
            import frappe as frappe_module  # type: ignore
        self.frappe = frappe_module
        self._fallback = InMemoryKnowledgeRepository()

    def save_source(self, source: KnowledgeSource) -> KnowledgeSource:
        return self._fallback.save_source(source)

    def get_source(self, source_id: str) -> KnowledgeSource | None:
        return self._fallback.get_source(source_id)

    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        return self._fallback.save_document(document)

    def save_chunks(self, chunks: Iterable[KnowledgeChunk]) -> list[KnowledgeChunk]:
        return self._fallback.save_chunks(chunks)

    def chunks(self) -> list[KnowledgeChunk]:
        return self._fallback.chunks()

    def document(self, document_id: str) -> KnowledgeDocument | None:
        return self._fallback.document(document_id)

    def source(self, source_id: str) -> KnowledgeSource | None:
        return self._fallback.source(source_id)

    def retire_source_chunks(self, source_id: str, except_hash: str | None = None) -> None:
        self._fallback.retire_source_chunks(source_id, except_hash)

