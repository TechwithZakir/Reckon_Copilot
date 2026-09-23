from __future__ import annotations

from typing import Any

from reckon_copilot.insights.service import generate_insights
from reckon_copilot.notifications.models import CopilotNotification
from reckon_copilot.permissions.boundary import PermissionAdapter


LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}


def generate_notifications(
    context: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    *,
    user: str | None = None,
    permission_adapter: PermissionAdapter | None = None,
    enabled: bool = True,
    limit: int = 3,
) -> dict[str, Any]:
    if not enabled:
        return {"ok": True, "enabled": False, "notifications": [], "counts": _counts([])}

    insight_result = generate_insights(
        context,
        evidence,
        user=user,
        permission_adapter=permission_adapter,
        limit=max(limit, 5),
    )
    notifications = _notifications_from_findings(insight_result.get("findings") or [])[:limit]
    return {
        "ok": True,
        "enabled": True,
        "context_fingerprint": insight_result.get("context_fingerprint"),
        "counts": _counts(notifications),
        "notifications": [notification.as_dict() for notification in notifications],
    }


def _notifications_from_findings(findings: list[dict[str, Any]]) -> list[CopilotNotification]:
    urgent = [
        finding
        for finding in findings
        if finding.get("severity") in {"critical", "warning"}
    ]
    urgent.sort(key=lambda finding: (LEVEL_ORDER.get(str(finding.get("severity")), 9), str(finding.get("title") or "")))
    return [
        CopilotNotification(
            title=str(finding.get("title") or "Copilot alert")[:120],
            message=str(finding.get("summary") or "")[:260],
            level=str(finding.get("severity") or "info"),
            source=str(finding.get("source") or "insight"),
            source_id=str(finding.get("finding_id") or ""),
            action_label="Ask Copilot",
            action_prompt=_first_prompt(finding),
        )
        for finding in urgent
    ]


def _first_prompt(finding: dict[str, Any]) -> str:
    prompts = finding.get("suggested_prompts")
    if isinstance(prompts, list) and prompts:
        return str(prompts[0])
    return "What should I review?"


def _counts(notifications: list[CopilotNotification]) -> dict[str, int]:
    return {
        "critical": sum(1 for item in notifications if item.level == "critical"),
        "warning": sum(1 for item in notifications if item.level == "warning"),
        "info": sum(1 for item in notifications if item.level == "info"),
    }
