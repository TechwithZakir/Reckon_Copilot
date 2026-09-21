from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from reckon_copilot.knowledge.embedder import HashingEmbedder
from reckon_copilot.knowledge.models import Evidence, KnowledgeStatus, RETRIEVABLE_STATUSES
from reckon_copilot.knowledge.repository import KnowledgeRepository
from reckon_copilot.knowledge.vector_store import VectorStore
from reckon_copilot.permissions.boundary import CAPABILITY_READ_KNOWLEDGE, CopilotPermissionBoundary, PermissionAdapter


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    context: dict[str, Any]
    user: str = "user@example.com"
    roles: set[str] | None = None
    top_k: int = 5
    filters: dict[str, str] | None = None
    max_text_chars: int = 500


class KnowledgeRetriever:
    def __init__(
        self,
        repository: KnowledgeRepository,
        permission_boundary: CopilotPermissionBoundary | None = None,
        permission_adapter: PermissionAdapter | None = None,
        vector_store: VectorStore | None = None,
        embedder: HashingEmbedder | None = None,
    ):
        self.repository = repository
        self.permission_boundary = permission_boundary
        self.permission_adapter = permission_adapter
        self.vector_store = vector_store
        self.embedder = embedder or HashingEmbedder()

    def retrieve(self, request: RetrievalRequest) -> list[Evidence]:
        self._authorize_context(request)
        keyword = self._keyword_results(request)
        vector = self._vector_results(request) if self.vector_store else {}
        merged = {}
        for chunk, score in keyword:
            merged[chunk.chunk_id] = max(score, vector.get(chunk.chunk_id, 0.0))
        for chunk_id, score in vector.items():
            if chunk_id not in merged:
                merged[chunk_id] = score
        evidence = [self._to_evidence(chunk_id, score, request) for chunk_id, score in merged.items()]
        return sorted([item for item in evidence if item], key=lambda item: item.score, reverse=True)[: request.top_k]

    def _authorize_context(self, request: RetrievalRequest) -> None:
        if self.permission_boundary:
            self.permission_boundary.authorize(
                request.context,
                capability=CAPABILITY_READ_KNOWLEDGE,
                user=request.user,
            )

    def _keyword_results(self, request: RetrievalRequest):
        terms = _terms(request.query)
        scored = []
        for chunk in self.repository.chunks():
            source = self.repository.source(chunk.source_id)
            if not source or source.status not in RETRIEVABLE_STATUSES:
                continue
            if chunk.status not in {KnowledgeStatus.INDEXED, KnowledgeStatus.APPROVED}:
                continue
            if request.filters and any(str(source.metadata.get(key) or getattr(source, key, "")) != str(value) for key, value in request.filters.items()):
                continue
            roles = request.roles
            if roles is None and self.permission_adapter:
                roles = self.permission_adapter.user_roles(request.user)
            if not source.permission_scope.allows(request.context, user=request.user, roles=roles):
                continue
            score = _score(terms, chunk.text)
            if score > 0:
                scored.append((chunk, score))
        return sorted(scored, key=lambda item: item[1], reverse=True)[: request.top_k]

    def _vector_results(self, request: RetrievalRequest) -> dict[str, float]:
        query_vector = self.embedder.embed(request.query)
        filters = request.filters or {}
        return dict(self.vector_store.similarity_search(query_vector, request.top_k, filters))

    def _to_evidence(self, chunk_id: str, score: float, request: RetrievalRequest) -> Evidence | None:
        chunk = next((item for item in self.repository.chunks() if item.chunk_id == chunk_id), None)
        if not chunk:
            return None
        source = self.repository.source(chunk.source_id)
        document = self.repository.document(chunk.document_id)
        if not source or not document or source.status not in RETRIEVABLE_STATUSES:
            return None
        return Evidence(
            chunk_id=chunk.chunk_id,
            document_id=document.document_id,
            source_id=source.source_id,
            source_title=source.title,
            source_type=str(source.source_type),
            locator=source.origin or document.metadata.get("locator", ""),
            version=document.version,
            score=round(float(score), 6),
            text=chunk.text[: request.max_text_chars],
            metadata={"untrusted": True, **chunk.metadata},
        )


def _terms(query: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", query.lower()))


def _score(terms: set[str], text: str) -> float:
    if not terms:
        return 0.0
    haystack = _terms(text)
    matched = terms.intersection(haystack)
    return len(matched) / len(terms)

