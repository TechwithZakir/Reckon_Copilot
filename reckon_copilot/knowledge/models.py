from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class KnowledgeSourceType(StrEnum):
    ERP_DATABASE = "ERP_DATABASE"
    INTERNAL_DOCUMENT = "INTERNAL_DOCUMENT"
    WEB_URL = "WEB_URL"
    MANUAL_URL = "MANUAL_URL"
    PDF = "PDF"
    DOCX = "DOCX"
    MANUAL_TEXT = "MANUAL_TEXT"


class KnowledgeStatus(StrEnum):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    APPROVED = "APPROVED"
    STALE = "STALE"
    FAILED = "FAILED"
    RETIRED = "RETIRED"


RETRIEVABLE_STATUSES = {KnowledgeStatus.APPROVED}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def stable_hash(value: Any) -> str:
    if not isinstance(value, str):
        value = stable_json(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass
class PermissionScope:
    site: str | None = None
    company: str | None = None
    module: str | None = None
    doctype: str | None = None
    roles: tuple[str, ...] = ()
    users: tuple[str, ...] = ()

    def allows(self, context: dict[str, Any], user: str | None = None, roles: set[str] | None = None) -> bool:
        filters = context.get("filters") or {}
        company = filters.get("company") or filters.get("Company")
        if self.company and company and self.company != company:
            return False
        if self.doctype and context.get("doctype") and self.doctype != context.get("doctype"):
            return False
        if self.users and user and user not in self.users:
            return False
        if self.roles and roles is not None and not set(self.roles).intersection(roles):
            return False
        return True


@dataclass
class KnowledgeSource:
    source_id: str
    source_type: KnowledgeSourceType
    title: str
    origin: str = ""
    description: str = ""
    status: KnowledgeStatus = KnowledgeStatus.QUEUED
    version: str = "1"
    content_hash: str = ""
    language: str = "en"
    permission_scope: PermissionScope = field(default_factory=PermissionScope)
    owner: str = "Administrator"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    last_processed_at: str | None = None
    last_error: str = ""


@dataclass
class KnowledgeDocument:
    document_id: str
    source_id: str
    title: str
    text: str
    version: str
    content_hash: str
    status: KnowledgeStatus = KnowledgeStatus.INDEXED
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)


@dataclass
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    source_id: str
    text: str
    sequence: int
    content_hash: str
    version: str
    status: KnowledgeStatus = KnowledgeStatus.INDEXED
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    document_id: str
    source_id: str
    source_title: str
    source_type: str
    locator: str
    version: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

