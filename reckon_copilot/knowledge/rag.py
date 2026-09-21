from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reckon_copilot.cache.keys import build_cache_identity, build_cache_key
from reckon_copilot.cache.manager import CacheManager
from reckon_copilot.cache.ttl import ttl_for
from reckon_copilot.knowledge.models import Evidence
from reckon_copilot.knowledge.retriever import KnowledgeRetriever, RetrievalRequest
from reckon_copilot.permissions.boundary import CAPABILITY_READ_KNOWLEDGE


@dataclass(frozen=True)
class RagContext:
    question: str
    evidence: list[Evidence]

    def as_prompt_context(self) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": item.chunk_id,
                "source_id": item.source_id,
                "source_title": item.source_title,
                "locator": item.locator,
                "score": item.score,
                "text": item.text,
                "untrusted": True,
            }
            for item in self.evidence
        ]


class RagOrchestrator:
    def __init__(self, retriever: KnowledgeRetriever, cache_manager: CacheManager | None = None, site: str = "default"):
        self.retriever = retriever
        self.cache_manager = cache_manager
        self.site = site

    def build_context(self, question: str, context: dict[str, Any], user: str, top_k: int = 5) -> RagContext:
        def compute():
            evidence = self.retriever.retrieve(
                RetrievalRequest(
                    query=question,
                    context=context,
                    user=user,
                    top_k=top_k,
                )
            )
            return [item.__dict__ for item in evidence]

        if self.cache_manager:
            identity = build_cache_identity(
                context=context,
                capability=CAPABILITY_READ_KNOWLEDGE,
                question=question,
                site=self.site,
                data_version="knowledge-v1",
                extra={"top_k": top_k},
            )
            result = self.cache_manager.get_or_compute(
                build_cache_key(identity, namespace="copilot:rag"),
                compute,
                ttl=ttl_for(CAPABILITY_READ_KNOWLEDGE),
            )
            evidence = [Evidence(**item) for item in result.value]
        else:
            evidence = [Evidence(**item) for item in compute()]
        return RagContext(question=question, evidence=evidence)
