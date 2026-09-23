from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


SEVERITIES = {"critical", "warning", "info"}


@dataclass(frozen=True)
class InsightFinding:
    title: str
    summary: str
    severity: str = "info"
    source: str = "context"
    confidence: str = "medium"
    suggested_prompts: tuple[str, ...] = ()
    suggested_actions: tuple[dict[str, Any], ...] = ()
    evidence_refs: tuple[str, ...] = ()
    finding_id: str = field(default="")

    def __post_init__(self):
        severity = self.severity if self.severity in SEVERITIES else "info"
        object.__setattr__(self, "severity", severity)
        if not self.finding_id:
            object.__setattr__(self, "finding_id", _finding_id(self.as_identity()))

    def as_identity(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "source": self.source,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "source": self.source,
            "confidence": self.confidence,
            "suggested_prompts": list(self.suggested_prompts),
            "suggested_actions": list(self.suggested_actions),
            "evidence_refs": list(self.evidence_refs),
        }


def _finding_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]
