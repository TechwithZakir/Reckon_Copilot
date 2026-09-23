from __future__ import annotations

from typing import Any

from reckon_copilot.insights.models import InsightFinding
from reckon_copilot.insights.rules import context_findings, evidence_findings, severity_counts
from reckon_copilot.permissions.boundary import (
    CAPABILITY_RUN_ANALYTICS,
    PermissionAdapter,
    authorize_context,
)


def generate_insights(
    context: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    *,
    user: str | None = None,
    permission_adapter: PermissionAdapter | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    authorized = authorize_context(
        context,
        capability=CAPABILITY_RUN_ANALYTICS,
        user=user,
        adapter=permission_adapter,
    ).context
    findings = _dedupe(context_findings(authorized) + evidence_findings(evidence))[:limit]
    return {
        "ok": True,
        "capability": CAPABILITY_RUN_ANALYTICS,
        "context_fingerprint": authorized.get("fingerprint"),
        "counts": severity_counts(findings),
        "findings": [finding.as_dict() for finding in findings],
    }


def _dedupe(findings: list[InsightFinding]) -> list[InsightFinding]:
    seen: set[str] = set()
    unique: list[InsightFinding] = []
    for finding in findings:
        if finding.finding_id in seen:
            continue
        seen.add(finding.finding_id)
        unique.append(finding)
    return unique
