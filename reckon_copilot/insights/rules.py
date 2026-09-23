from __future__ import annotations

from typing import Any

from reckon_copilot.insights.models import InsightFinding


RISK_TERMS = {
    "critical": ("critical", "exception", "failed", "blocked", "unauthorized"),
    "warning": ("overdue", "unpaid", "pending", "timeout", "warning", "incomplete"),
}


def context_findings(context: dict[str, Any]) -> list[InsightFinding]:
    page_type = str(context.get("page_type") or "Page")
    label = _context_label(context)
    findings = [
        InsightFinding(
            title=f"{page_type} context ready",
            summary=f"Copilot is using sanitized, permission-authorized context for {label}.",
            severity="info",
            source="context",
            confidence="high",
            suggested_prompts=(
                "Explain this page",
                "What should I review?",
            ),
        )
    ]

    if page_type == "List":
        filters = context.get("filters") if isinstance(context.get("filters"), dict) else {}
        if filters:
            findings.append(
                InsightFinding(
                    title="Review active filters",
                    summary=f"{len(filters)} list filter(s) are part of the current context scope.",
                    severity="info",
                    source="context",
                    confidence="high",
                    suggested_prompts=("Which filters may help?",),
                )
            )
        else:
            findings.append(
                InsightFinding(
                    title="No list filters applied",
                    summary="The list context is broad. Add filters before asking for targeted operational analysis.",
                    severity="warning",
                    source="context",
                    confidence="medium",
                    suggested_prompts=("Which filters may help?",),
                )
            )

    if page_type == "Form" and _is_new_document(context.get("document_name")):
        findings.append(
            InsightFinding(
                title="Draft record is not saved",
                summary="This form appears to be a new unsaved record, so Copilot can only use route and field-safe context.",
                severity="warning",
                source="context",
                confidence="high",
                suggested_prompts=("What should I complete before saving?",),
            )
        )

    if page_type == "Report":
        findings.append(
            InsightFinding(
                title="Report filters define the scope",
                summary="Copilot will use report name and sanitized filters, not unrestricted report output rows.",
                severity="info",
                source="context",
                confidence="high",
                suggested_prompts=("Summarize this report setup",),
            )
        )

    return findings


def evidence_findings(evidence: list[dict[str, Any]] | None) -> list[InsightFinding]:
    findings: list[InsightFinding] = []
    for item in (evidence or [])[:5]:
        text = _compact_text(str(item.get("text") or item.get("summary") or ""))
        if not text:
            continue
        severity = _severity_for_text(text)
        if severity == "info":
            continue
        source_title = str(item.get("source_title") or item.get("source") or "approved knowledge")[:120]
        evidence_id = str(item.get("chunk_id") or item.get("source_id") or "")
        findings.append(
            InsightFinding(
                title="Relevant knowledge risk signal",
                summary=f"{source_title}: {text}",
                severity=severity,
                source="knowledge",
                confidence="medium",
                suggested_prompts=("Explain this evidence", "What should I review?"),
                evidence_refs=(evidence_id,) if evidence_id else (),
            )
        )
    return findings


def severity_counts(findings: list[InsightFinding]) -> dict[str, int]:
    return {
        "critical": sum(1 for finding in findings if finding.severity == "critical"),
        "warning": sum(1 for finding in findings if finding.severity == "warning"),
        "info": sum(1 for finding in findings if finding.severity == "info"),
    }


def _context_label(context: dict[str, Any]) -> str:
    return str(
        context.get("doctype")
        or context.get("report_name")
        or context.get("dashboard_name")
        or context.get("workspace_name")
        or context.get("page_name")
        or "this Desk page"
    )


def _compact_text(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    return compact[: limit - 1] + "..." if len(compact) > limit else compact


def _severity_for_text(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in RISK_TERMS["critical"]):
        return "critical"
    if any(term in lowered for term in RISK_TERMS["warning"]):
        return "warning"
    return "info"


def _is_new_document(document_name: Any) -> bool:
    return str(document_name or "").lower().startswith("new-")
