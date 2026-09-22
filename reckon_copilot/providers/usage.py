from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    capability: str
    status: str
    cache_hit: bool
    latency_ms: int = 0
    prompt_chars: int = 0
    response_chars: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class InMemoryUsageLogger:
    def __init__(self):
        self.records: list[UsageRecord] = []

    def log(self, record: UsageRecord) -> None:
        self.records.append(record)


class FrappeUsageLogger:
    def __init__(self, frappe_module=None):
        if frappe_module is None:
            import frappe as frappe_module  # type: ignore
        self.frappe = frappe_module

    def log(self, record: UsageRecord) -> None:
        try:
            doc = self.frappe.get_doc(
                {
                    "doctype": "Copilot Usage Log",
                    "provider": record.provider,
                    "model": record.model,
                    "capability": record.capability,
                    "status": record.status,
                    "cache_hit": int(record.cache_hit),
                    "latency_ms": record.latency_ms,
                    "prompt_chars": record.prompt_chars,
                    "response_chars": record.response_chars,
                    "error": record.error[:500],
                    "metadata": json.dumps(record.metadata, sort_keys=True, default=str)[:5000],
                }
            )
            doc.insert(ignore_permissions=True)
        except Exception:
            return None
