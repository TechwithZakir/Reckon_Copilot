from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reckon_copilot.knowledge.models import Evidence
from reckon_copilot.knowledge.retriever import KnowledgeRetriever, RetrievalRequest


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
    def __init__(self, retriever: KnowledgeRetriever):
        self.retriever = retriever

    def build_context(self, question: str, context: dict[str, Any], user: str, top_k: int = 5) -> RagContext:
        evidence = self.retriever.retrieve(
            RetrievalRequest(
                query=question,
                context=context,
                user=user,
                top_k=top_k,
            )
        )
        return RagContext(question=question, evidence=evidence)

