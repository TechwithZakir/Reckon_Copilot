from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from reckon_copilot.knowledge.embedder import EmbeddingProfile


@dataclass(frozen=True)
class VectorRecord:
    id: str
    vector: list[float]
    metadata: dict[str, str] = field(default_factory=dict)


class VectorStore(Protocol):
    profile: EmbeddingProfile

    def upsert(self, records: list[VectorRecord]) -> None: ...
    def delete(self, ids: list[str]) -> None: ...
    def similarity_search(self, vector: list[float], top_k: int = 5, filters: dict[str, str] | None = None) -> list[tuple[str, float]]: ...
    def rebuild(self) -> None: ...
    def health_check(self) -> dict[str, str | int | bool]: ...


class InMemoryVectorStore:
    def __init__(self, profile: EmbeddingProfile | None = None):
        self.profile = profile or EmbeddingProfile()
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            if len(record.vector) != self.profile.dimension:
                raise ValueError("Vector dimension does not match index profile")
            self.records[record.id] = record

    def delete(self, ids: list[str]) -> None:
        for record_id in ids:
            self.records.pop(record_id, None)

    def similarity_search(self, vector: list[float], top_k: int = 5, filters: dict[str, str] | None = None) -> list[tuple[str, float]]:
        if len(vector) != self.profile.dimension:
            raise ValueError("Query vector dimension does not match index profile")
        results: list[tuple[str, float]] = []
        for record in self.records.values():
            if filters and any(str(record.metadata.get(key)) != str(value) for key, value in filters.items()):
                continue
            results.append((record.id, _cosine(vector, record.vector)))
        return sorted(results, key=lambda item: item[1], reverse=True)[:top_k]

    def rebuild(self) -> None:
        self.records = {}

    def health_check(self) -> dict[str, str | int | bool]:
        return {
            "ok": True,
            "provider": self.profile.provider,
            "model": self.profile.model,
            "version": self.profile.version,
            "dimension": self.profile.dimension,
            "records": len(self.records),
        }


def _cosine(first: list[float], second: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(first, second, strict=False))
    left = math.sqrt(sum(a * a for a in first)) or 1.0
    right = math.sqrt(sum(b * b for b in second)) or 1.0
    return numerator / (left * right)
