from __future__ import annotations


INTENTS = {"explain", "summarize", "troubleshoot", "related_records", "reminder", "general"}


def classify_intent(question: str) -> str:
    text = (question or "").strip().lower()
    if not text:
        return "general"
    if any(term in text for term in ("why", "error", "failed", "issue", "problem", "not working")):
        return "troubleshoot"
    if any(term in text for term in ("summarize", "summary", "brief")):
        return "summarize"
    if any(term in text for term in ("related", "linked", "connection", "records")):
        return "related_records"
    if any(term in text for term in ("remind", "reminder", "follow up")):
        return "reminder"
    if any(term in text for term in ("explain", "what is", "what are", "how to", "how do")):
        return "explain"
    return "general"
