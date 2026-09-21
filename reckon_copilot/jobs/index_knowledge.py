from __future__ import annotations

from reckon_copilot.knowledge.service import KnowledgeEngine


def process_knowledge_source(source_id: str, payload: str | bytes | None = None, approve: bool = False):
    engine = KnowledgeEngine()
    return engine.process_source(source_id, payload=payload, approve=approve)


def enqueue_knowledge_source(source_id: str, payload: str | bytes | None = None, approve: bool = False):
    try:
        import frappe  # type: ignore
    except Exception:
        return process_knowledge_source(source_id, payload=payload, approve=approve)

    return frappe.enqueue(
        "reckon_copilot.jobs.index_knowledge.process_knowledge_source",
        queue="long",
        source_id=source_id,
        payload=payload,
        approve=approve,
    )
