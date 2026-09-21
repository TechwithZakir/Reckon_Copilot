from __future__ import annotations

from typing import Any

from reckon_copilot.jobs.index_knowledge import enqueue_knowledge_source
from reckon_copilot.knowledge.models import KnowledgeSourceType, PermissionScope
from reckon_copilot.knowledge.service import KnowledgeEngine

_engine = KnowledgeEngine()


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn
        return decorator
    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def create_manual_knowledge(title: str, content: str, company: str | None = None) -> dict[str, Any]:
    source = _engine.create_source(
        KnowledgeSourceType.MANUAL_TEXT,
        title=title,
        description=content,
        permission_scope=PermissionScope(company=company),
    )
    enqueue_knowledge_source(source.source_id, payload=content, approve=True)
    return {
        "source_id": source.source_id,
        "status": "QUEUED",
    }


@_whitelist(allow_guest=False)
def submit_url(title: str, url: str, content: str | None = None) -> dict[str, Any]:
    source = _engine.create_source(KnowledgeSourceType.MANUAL_URL, title=title, origin=url)
    enqueue_knowledge_source(source.source_id, payload=content or url, approve=False)
    return {
        "source_id": source.source_id,
        "status": "QUEUED",
    }
