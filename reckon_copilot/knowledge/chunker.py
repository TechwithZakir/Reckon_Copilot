from __future__ import annotations

from reckon_copilot.knowledge.models import KnowledgeChunk, KnowledgeStatus, stable_hash


class DeterministicChunker:
    def __init__(self, chunk_size: int = 700, overlap: int = 120):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, document_id: str, source_id: str, text: str, version: str) -> list[KnowledgeChunk]:
        if not text:
            return []
        chunks: list[KnowledgeChunk] = []
        start = 0
        sequence = 0
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start + self.chunk_size // 2:
                    end = boundary
            chunk_text = text[start:end].strip()
            if chunk_text:
                content_hash = stable_hash(chunk_text)
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=stable_hash({"document_id": document_id, "sequence": sequence, "hash": content_hash})[:32],
                        document_id=document_id,
                        source_id=source_id,
                        text=chunk_text,
                        sequence=sequence,
                        content_hash=content_hash,
                        version=version,
                        status=KnowledgeStatus.INDEXED,
                    )
                )
                sequence += 1
            if end >= len(text):
                break
            start = max(end - self.overlap, start + 1)
        return chunks

