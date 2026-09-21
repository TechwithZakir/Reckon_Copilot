from __future__ import annotations

import json
from dataclasses import replace
from typing import Iterable

from reckon_copilot.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    KnowledgeSourceType,
    KnowledgeStatus,
    PermissionScope,
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
    """Frappe-backed repository for approved knowledge and compact evidence."""

    def __init__(self, frappe_module=None):
        if frappe_module is None:
            import frappe as frappe_module  # type: ignore
        self.frappe = frappe_module

    def save_source(self, source: KnowledgeSource) -> KnowledgeSource:
        values = {
            "source_type": str(source.source_type),
            "title": source.title,
            "origin": source.origin,
            "status": str(source.status),
            "version": source.version,
            "content_hash": source.content_hash,
            "language": source.language,
            "company": source.permission_scope.company,
            "module": source.permission_scope.module,
            "reference_doctype": source.permission_scope.doctype,
            "owner_user": source.owner,
            "last_processed_at": source.last_processed_at,
            "last_error": source.last_error,
            "metadata_json": _json_dumps(source.metadata),
        }
        name = self._name_for("Copilot Knowledge Source", "source_id", source.source_id)
        if name:
            doc = self.frappe.get_doc("Copilot Knowledge Source", name)
            doc.update(values)
            doc.save(ignore_permissions=True)
        else:
            doc = self.frappe.get_doc({"doctype": "Copilot Knowledge Source", "source_id": source.source_id, **values})
            doc.insert(ignore_permissions=True)
        return source

    def get_source(self, source_id: str) -> KnowledgeSource | None:
        name = self._name_for("Copilot Knowledge Source", "source_id", source_id)
        if not name:
            return None
        return self._source_from_doc(self.frappe.get_doc("Copilot Knowledge Source", name))

    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        values = {
            "source_id": document.source_id,
            "title": document.title,
            "status": str(document.status),
            "version": document.version,
            "content_hash": document.content_hash,
            "locator": document.metadata.get("locator", ""),
            "metadata_json": _json_dumps(document.metadata),
        }
        name = self._name_for("Copilot Knowledge Document", "document_id", document.document_id)
        if name:
            doc = self.frappe.get_doc("Copilot Knowledge Document", name)
            if getattr(doc, "content_hash", "") == document.content_hash:
                return document
            doc.update(values)
            doc.save(ignore_permissions=True)
        else:
            doc = self.frappe.get_doc({"doctype": "Copilot Knowledge Document", "document_id": document.document_id, **values})
            doc.insert(ignore_permissions=True)
        return document

    def save_chunks(self, chunks: Iterable[KnowledgeChunk]) -> list[KnowledgeChunk]:
        saved: list[KnowledgeChunk] = []
        for chunk in chunks:
            values = {
                "source_id": chunk.source_id,
                "document_id": chunk.document_id,
                "sequence": chunk.sequence,
                "status": str(chunk.status),
                "version": chunk.version,
                "content_hash": chunk.content_hash,
                "chunk_text": chunk.text,
                "metadata_json": _json_dumps(chunk.metadata),
            }
            name = self._name_for("Copilot Knowledge Chunk", "chunk_id", chunk.chunk_id)
            if name:
                doc = self.frappe.get_doc("Copilot Knowledge Chunk", name)
                if getattr(doc, "content_hash", "") == chunk.content_hash:
                    saved.append(chunk)
                    continue
                doc.update(values)
                doc.save(ignore_permissions=True)
            else:
                doc = self.frappe.get_doc({"doctype": "Copilot Knowledge Chunk", "chunk_id": chunk.chunk_id, **values})
                doc.insert(ignore_permissions=True)
            saved.append(chunk)
        return saved

    def chunks(self) -> list[KnowledgeChunk]:
        rows = self.frappe.get_all(
            "Copilot Knowledge Chunk",
            fields=["name", "chunk_id", "source_id", "document_id", "sequence", "status", "version", "content_hash", "chunk_text", "metadata_json"],
            limit_page_length=1000,
        )
        return [self._chunk_from_row(row) for row in rows]

    def document(self, document_id: str) -> KnowledgeDocument | None:
        name = self._name_for("Copilot Knowledge Document", "document_id", document_id)
        if not name:
            return None
        doc = self.frappe.get_doc("Copilot Knowledge Document", name)
        metadata = _json_loads(getattr(doc, "metadata_json", ""))
        return KnowledgeDocument(
            document_id=document_id,
            source_id=str(getattr(doc, "source_id", "")),
            title=str(getattr(doc, "title", "")),
            text="",
            version=str(getattr(doc, "version", "")),
            content_hash=str(getattr(doc, "content_hash", "")),
            status=KnowledgeStatus(str(getattr(doc, "status", KnowledgeStatus.INDEXED))),
            metadata=metadata,
        )

    def source(self, source_id: str) -> KnowledgeSource | None:
        return self.get_source(source_id)

    def retire_source_chunks(self, source_id: str, except_hash: str | None = None) -> None:
        filters = {"source_id": source_id}
        for row in self.frappe.get_all("Copilot Knowledge Chunk", filters=filters, fields=["name", "content_hash"]):
            if except_hash and str(row.get("content_hash") or "") == except_hash:
                continue
            doc = self.frappe.get_doc("Copilot Knowledge Chunk", row["name"])
            doc.status = KnowledgeStatus.STALE
            doc.save(ignore_permissions=True)

    def _name_for(self, doctype: str, field: str, value: str) -> str | None:
        result = self.frappe.db.get_value(doctype, {field: value}, "name")
        return str(result) if result else None

    def _source_from_doc(self, doc) -> KnowledgeSource:
        return KnowledgeSource(
            source_id=str(getattr(doc, "source_id", "")),
            source_type=KnowledgeSourceType(str(getattr(doc, "source_type", KnowledgeSourceType.MANUAL_TEXT))),
            title=str(getattr(doc, "title", "")),
            origin=str(getattr(doc, "origin", "") or ""),
            status=KnowledgeStatus(str(getattr(doc, "status", KnowledgeStatus.QUEUED))),
            version=str(getattr(doc, "version", "") or "1"),
            content_hash=str(getattr(doc, "content_hash", "") or ""),
            language=str(getattr(doc, "language", "") or "en"),
            permission_scope=PermissionScope(
                company=str(getattr(doc, "company", "") or "") or None,
                module=str(getattr(doc, "module", "") or "") or None,
                doctype=str(getattr(doc, "reference_doctype", "") or "") or None,
            ),
            owner=str(getattr(doc, "owner_user", "") or getattr(doc, "owner", "") or "Administrator"),
            metadata=_json_loads(getattr(doc, "metadata_json", "")),
            last_processed_at=getattr(doc, "last_processed_at", None),
            last_error=str(getattr(doc, "last_error", "") or ""),
        )

    def _chunk_from_row(self, row) -> KnowledgeChunk:
        return KnowledgeChunk(
            chunk_id=str(row.get("chunk_id") or row.get("name") or ""),
            document_id=str(row.get("document_id") or ""),
            source_id=str(row.get("source_id") or ""),
            text=str(row.get("chunk_text") or ""),
            sequence=int(row.get("sequence") or 0),
            content_hash=str(row.get("content_hash") or ""),
            version=str(row.get("version") or ""),
            status=KnowledgeStatus(str(row.get("status") or KnowledgeStatus.INDEXED)),
            metadata=_json_loads(row.get("metadata_json") or ""),
        )


def _json_dumps(value: dict) -> str:
    return json.dumps(value or {}, sort_keys=True, ensure_ascii=True)


def _json_loads(value: str) -> dict:
    try:
        payload = json.loads(value or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
