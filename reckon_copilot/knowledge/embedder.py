from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str = "native"
    model: str = "hashing-token-vector"
    version: str = "1"
    dimension: int = 64


class HashingEmbedder:
    def __init__(self, profile: EmbeddingProfile | None = None):
        self.profile = profile or EmbeddingProfile()

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.profile.dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.profile.dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def compatible(self, other: EmbeddingProfile) -> bool:
        return self.profile == other
