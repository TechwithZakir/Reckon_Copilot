from __future__ import annotations

from dataclasses import replace
from typing import Any

from reckon_copilot.knowledge.chunker import DeterministicChunker
from reckon_copilot.knowledge.embedder import HashingEmbedder
from reckon_copilot.knowledge.extractor import ExtractionError, KnowledgeExtractor
from reckon_copilot.knowledge.models import (
    KnowledgeDocument,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
    PermissionScope,
    normalize_text,
    stable_hash,
    utcnow,
)
from reckon_copilot.knowledge.repository import InMemoryKnowledgeRepository, KnowledgeRepository
from reckon_copilot.knowledge.vector_store import InMemoryVectorStore, VectorRecord, VectorStore


class KnowledgeEngine:
    def __init__(
        self,
        repository: KnowledgeRepository | None = None,
        extractor: KnowledgeExtractor | None = None,
        chunker: DeterministicChunker | None = None,
        vector_store: VectorStore | None = None,
        embedder: HashingEmbedder | None = None,
    ):
        self.repository = repository or InMemoryKnowledgeRepository()
        self.extractor = extractor or KnowledgeExtractor()
        self.chunker = chunker or DeterministicChunker()
        self.embedder = embedder or HashingEmbedder()
        self.vector_store = vector_store or InMemoryVectorStore(self.embedder.profile)

    def create_source(
        self,
        source_type: KnowledgeSourceType | str,
        title: str,
        origin: str = "",
        description: str = "",
        owner: str = "Administrator",
        permission_scope: PermissionScope | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeSource:
        source_type = KnowledgeSourceType(source_type)
        source_id = stable_hash({"type": source_type, "title": title, "origin": origin, "owner": owner})[:32]
        source = KnowledgeSource(
            source_id=source_id,
            source_type=source_type,
            title=title,
            origin=origin,
            description=description,
            owner=owner,
            permission_scope=permission_scope or PermissionScope(),
            metadata=metadata or {},
        )
        return self.repository.save_source(source)

    def process_source(self, source_id: str, payload: str | bytes | None = None, approve: bool = False) -> tuple[KnowledgeDocument, list]:
        source = self.repository.get_source(source_id)
        if not source:
            raise ValueError("Knowledge source not found")
        source = self.repository.save_source(replace(source, status=KnowledgeStatus.EXTRACTING, updated_at=utcnow()))
        try:
            text = self.extractor.extract(source, payload)
            text = normalize_text(text)
            content_hash = stable_hash(text)
            document_id = stable_hash({"source_id": source.source_id, "hash": content_hash})[:32]
            document = KnowledgeDocument(
                document_id=document_id,
                source_id=source.source_id,
                title=source.title,
                text=text,
                version=content_hash[:12],
                content_hash=content_hash,
                metadata={"locator": source.origin},
            )
            self.repository.save_document(document)
            self.repository.retire_source_chunks(source.source_id, except_hash=content_hash)
            chunks = self.repository.save_chunks(self.chunker.chunk(document_id, source.source_id, text, document.version))
            self._index_vectors(chunks, source)
            status = KnowledgeStatus.APPROVED if approve else KnowledgeStatus.INDEXED
            self.repository.save_source(
                replace(
                    source,
                    status=status,
                    content_hash=content_hash,
                    version=document.version,
                    updated_at=utcnow(),
                    last_processed_at=utcnow(),
                    last_error="",
                )
            )
            return document, chunks
        except Exception as error:
            self.repository.save_source(replace(source, status=KnowledgeStatus.FAILED, last_error=str(error), updated_at=utcnow()))
            if isinstance(error, ExtractionError):
                raise
            raise

    def approve_source(self, source_id: str) -> KnowledgeSource:
        source = self.repository.get_source(source_id)
        if not source:
            raise ValueError("Knowledge source not found")
        approved = replace(source, status=KnowledgeStatus.APPROVED, updated_at=utcnow())
        return self.repository.save_source(approved)

    def retire_source(self, source_id: str) -> KnowledgeSource:
        source = self.repository.get_source(source_id)
        if not source:
            raise ValueError("Knowledge source not found")
        retired = replace(source, status=KnowledgeStatus.RETIRED, updated_at=utcnow())
        self.repository.retire_source_chunks(source_id)
        return self.repository.save_source(retired)

    def _index_vectors(self, chunks, source: KnowledgeSource) -> None:
        records = [
            VectorRecord(
                id=chunk.chunk_id,
                vector=self.embedder.embed(chunk.text),
                metadata={"source_id": source.source_id, "source_type": str(source.source_type)},
            )
            for chunk in chunks
        ]
        self.vector_store.upsert(records)

