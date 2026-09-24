from __future__ import annotations

from typing import Any

from reckon_copilot.permissions.boundary import (
    CAPABILITY_RUN_ANALYTICS,
    CopilotPermissionBoundary,
    PermissionAdapter,
    PermissionDenied,
    authorize_context,
)


DOMAIN_TOKENS = {
    "sales": ("quotation", "sales order", "sales invoice", "delivery note", "customer", "selling"),
    "purchasing": ("request for quotation", "supplier quotation", "purchase order", "purchase invoice", "buying", "supplier"),
    "inventory": ("item", "stock", "warehouse", "batch", "serial", "material request", "inventory"),
    "accounts": ("payment", "journal", "account", "general ledger", "receivable", "payable", "accounting"),
    "projects": ("project", "task", "timesheet", "activity", "projects"),
    "people": ("employee", "attendance", "leave", "salary", "payroll", "human resources", "hr"),
}

SOURCE_LABELS = {
    "context": "Current page",
    "doctype": "DocType structure",
    "filter": "Active filters",
    "report": "Report definition",
    "dashboard": "Dashboard layout",
    "workspace": "Workspace layout",
    "permission": "Native permissions",
}

ACTION_LABELS = {
    "analyze": "Analyze",
    "create": "Create preview",
    "filter": "Filter",
    "help": "Explain",
    "navigate": "Navigate",
    "review": "Review",
    "submit": "Submit preview",
    "update": "Update preview",
    "workflow": "Workflow",
}

SENSITIVE_FIELD_TERMS = {"password", "secret", "token", "api_key", "api_secret"}


def get_advice(
    context: dict[str, Any],
    *,
    user: str | None = None,
    permission_adapter: PermissionAdapter | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    adapter = permission_adapter
    authorized = authorize_context(
        context,
        capability=CAPABILITY_RUN_ANALYTICS,
        user=user,
        adapter=permission_adapter,
    ).context
    metadata = _safe_metadata(metadata)
    page_type = str(authorized.get("page_type") or "Page")
    label = _context_label(authorized)
    family = _page_family(authorized, metadata)
    questions = _questions(page_type, authorized, metadata, family)
    actions = _actions(page_type, authorized, adapter, user, metadata, family)
    return {
        "ok": True,
        "advisor_version": "v2",
        "audience": "end_user",
        "context_fingerprint": authorized.get("fingerprint"),
        "context_label": label,
        "page_family": family,
        "page_summary": _page_summary(page_type, authorized, metadata, family),
        "questions": questions,
        "actions": actions,
        "signals": _signals(page_type, authorized, metadata, family),
    }


def _questions(page_type: str, context: dict[str, Any], metadata: dict[str, Any], family: str) -> list[dict[str, Any]]:
    label = _context_label(context)
    if page_type == "List":
        filters = _filters(context)
        result: list[dict[str, Any]] = []
        if filters:
            filter_reason = _filter_reason(filters)
            if _has_status_filter(filters):
                result.append(_item(
                    f"What needs attention in this {label} status?",
                    f"Review the {label} records in the current status scope and identify the next follow-up.",
                    "operational-review", filter_reason, "filter", priority="high", action_type="review",
                ))
            else:
                result.append(_item(
                    f"What should I focus on in this {label} list?",
                    f"Summarize the permitted {label} records within the active filters and highlight useful follow-up.",
                    "operational-review", filter_reason, "filter", priority="high", action_type="analyze",
                ))
        else:
            result.append(_item(
                f"Which {label} records need attention?",
                f"Find operational risks or follow-up items in the permitted {label} list.",
                "operational-review",
                "No filters are active, so Copilot will start with the full permitted list scope.",
                "context", priority="high", action_type="analyze",
            ))
        result.append(_item(
            f"Which filters would make this {label} review useful?",
            f"Suggest safe filters for a focused {label} review.",
            "filter-help",
            "Use the current DocType and available list fields to narrow the review.",
            "doctype" if metadata.get("field_names") else "context", action_type="filter",
        ))
        if family == "sales":
            result.append(_item(
                "Which sales records need follow-up?",
                "Identify permitted sales records that may need customer, delivery or billing follow-up.",
                "sales-operations",
                "This page belongs to the Selling flow; follow-up is prioritized without exposing records outside the current scope.",
                "context", priority="high", action_type="review",
            ))
        return result[:4]

    if page_type == "Form":
        is_new = _is_new_document(context.get("document_name"))
        result: list[dict[str, Any]] = []
        if metadata.get("required_fields"):
            required = ", ".join(metadata["required_fields"][:4])
            result.append(_item(
                "What must be completed before saving?",
                f"Check the required fields for this {label}: {required}.",
                "completion-check",
                f"The DocType defines {len(metadata['required_fields'])} required field(s) visible to Copilot.",
                "doctype", priority="high", action_type="review",
            ))
        if family == "sales":
            result.append(_item(
                f"Is this {label} ready for the next step?",
                f"Review customer, dates, items, pricing, taxes and delivery readiness for this {label}.",
                "sales-readiness",
                "Selling documents commonly depend on customer, item and delivery details before workflow progression.",
                "doctype" if metadata.get("field_names") else "context",
                priority="high" if not is_new else "normal", action_type="workflow",
            ))
        elif family == "purchasing":
            result.append(_item(
                f"What should I verify on this {label}?",
                f"Review supplier, items, rates, taxes and receipt expectations for this {label}.",
                "purchasing-review",
                "Purchasing documents need supplier and fulfilment details before approval or receipt.",
                "doctype" if metadata.get("field_names") else "context", action_type="review",
            ))
        elif family == "inventory":
            result.append(_item(
                f"What inventory checks apply to this {label}?",
                f"Review item, warehouse, quantity and valuation details for this {label}.",
                "inventory-review",
                "Inventory documents depend on item and warehouse consistency.",
                "doctype" if metadata.get("field_names") else "context", action_type="review",
            ))
        else:
            result.append(_item(
                "What should I review on this document?",
                f"Review this {label} for missing, inconsistent or risky information.",
                "document-review",
                "Use the permitted form context and safe DocType structure to prepare a review.",
                "context", action_type="review",
            ))
        result.append(_item(
            "Explain the next workflow step",
            f"Explain what normally happens next for this {label}.",
            "workflow",
            "The request is limited to the current record context and workflow metadata.",
            "doctype" if metadata.get("has_workflow_state") or metadata.get("is_submittable") else "context",
            action_type="workflow",
        ))
        return result[:4]

    if page_type == "Report":
        filters = _filters(context)
        result = [_item(
            f"What is this {label} report telling me?",
            f"Explain the scope, source and meaning of this {label} report without exposing unrestricted rows.",
            "report-explanation",
            "Start with the report definition and the current permitted filter scope.",
            "report" if metadata.get("ref_doctype") or metadata.get("report_type") else "context", action_type="analyze",
        )]
        if filters:
            result.append(_item(
                "Are the active report filters appropriate?",
                "Review the current report filters and explain what they include or exclude.",
                "report-scope", _filter_reason(filters), "filter", priority="high", action_type="filter",
            ))
        else:
            result.append(_item(
                "Which report filters should I add first?",
                "Suggest a date, company or status filter that would make this report more useful.",
                "report-scope",
                "The report has no active filters, so conclusions could be too broad.",
                "context", priority="high", action_type="filter",
            ))
        if metadata.get("ref_doctype"):
            result.append(_item(
                f"How does {metadata['ref_doctype']} affect this report?",
                f"Explain the source DocType fields most relevant to this {label} report.",
                "report-source",
                f"The report definition identifies {metadata['ref_doctype']} as its source DocType.",
                "report", action_type="analyze",
            ))
        return result[:4]

    if page_type == "Dashboard":
        card_count = metadata.get("card_count")
        return [
            _item(
                f"Which {label} metrics need attention?",
                f"Explain the visible {label} metrics and identify where an operator should look first.",
                "metric-review",
                f"The dashboard exposes {card_count} configured metric card(s)." if card_count else "Use the visible dashboard context without exposing underlying records.",
                "dashboard", priority="high" if card_count else "normal", action_type="analyze",
            ),
            _item(
                "What changed in this dashboard scope?",
                "Explain how the selected dashboard or date scope affects the visible metrics.",
                "metric-scope",
                "Dashboard interpretation should stay aligned with the current route and filters.",
                "context", action_type="filter",
            ),
        ]

    if page_type == "Workspace":
        link_count = metadata.get("link_count")
        return [
            _item(
                f"What should I open first in {label}?",
                f"Recommend the most relevant next area in the {label} workspace.",
                "workspace-navigation",
                f"This workspace exposes {link_count} visible link group(s)." if link_count else "Use the current workspace route and visible navigation context.",
                "workspace", action_type="navigate",
            ),
            _item(
                "Explain this workspace",
                f"Explain the purpose of the visible areas in {label}.",
                "workspace-help",
                "Keep guidance limited to navigation that the current user can already see.",
                "workspace", action_type="help",
            ),
        ]

    return [_item(
        "What can I do on this page?",
        f"Explain useful next steps for {context.get('page_name') or 'this Desk page'}.",
        "page-help",
        "No richer page metadata was available, so Copilot is keeping the guidance general.",
        "context", action_type="help",
    )]


def _actions(
    page_type: str,
    context: dict[str, Any],
    permission_adapter: PermissionAdapter | None,
    user: str | None,
    metadata: dict[str, Any],
    family: str,
) -> list[dict[str, Any]]:
    label = _context_label(context)
    if page_type == "Form" and _is_new_document(context.get("document_name")):
        if _can_action(context, "create", permission_adapter, user):
            return [_item(
                f"Complete this {label} draft",
                f"Identify missing information before saving this {label}.",
                "draft-completion",
                "This is a new form and the user has native create permission; approval is still required before any future insert.",
                "permission", priority="high" if metadata.get("required_fields") else "normal",
                action_type="create", requires_confirmation=True,
            )]
        return []

    if page_type == "Form":
        if family == "sales":
            title = f"Prepare {label} readiness review"
            prompt = f"Prepare a review of customer, items, pricing, taxes and delivery readiness for this {label}."
        elif family == "purchasing":
            title = f"Prepare {label} approval review"
            prompt = f"Prepare a review of supplier, items, rates, taxes and fulfilment readiness for this {label}."
        else:
            title = f"Prepare {label} workflow review"
            prompt = f"Prepare a read-only review plan for this {label} before the next workflow step."
        result = [_item(
            title, prompt, "workflow-review",
            "This read-only review uses the current document context and DocType structure.",
            "context", action_type="review",
        )]
        if _can_action(context, "update", permission_adapter, user):
            result.append(_item(
                "Preview allowed edits",
                f"Prepare a preview of permitted updates to this {label}; do not apply them.",
                "write-preview",
                "Native write permission is available for this record, but execution remains disabled until explicit approval and audit are implemented.",
                "permission", action_type="update", requires_confirmation=True,
            ))
        if metadata.get("is_submittable") and _can_action(context, "submit", permission_adapter, user):
            result.append(_item(
                "Preview submission checks",
                f"Prepare a preview of the checks required before submitting this {label}.",
                "submission-preview",
                "This DocType is submittable and native submit permission is available; execution remains disabled.",
                "permission", priority="high", action_type="submit", requires_confirmation=True,
            ))
        return result

    if page_type == "List":
        if family == "sales":
            title = f"Prepare {label} follow-up review"
            prompt = f"Review visible {label} records for customer, delivery and billing follow-up within the current scope."
        elif family == "inventory":
            title = f"Prepare {label} stock review"
            prompt = f"Review visible {label} records for item, warehouse and quantity follow-up within the current scope."
        else:
            title = f"Prepare focused {label} review"
            prompt = f"Create a read-only review plan for the visible {label} records within the current permitted scope."
        filters = _filters(context)
        return [_item(
            title, prompt, "operational-review",
            _filter_reason(filters) if filters else "No filters are active; the review will stay within the full permitted list scope.",
            "filter" if filters else "context", priority="high" if filters else "normal", action_type="review",
        )]

    if page_type == "Report":
        filters = _filters(context)
        return [_item(
            "Prepare a focused report review",
            "Summarize the report scope, active filters and the most useful next analysis.",
            "report-review",
            _filter_reason(filters) if filters else "A focused review is useful because the report has no active filters.",
            "filter" if filters else "report", priority="high" if not filters else "normal", action_type="analyze",
        )]

    if page_type == "Dashboard":
        return [_item(
            "Prioritize dashboard signals",
            "Summarize which visible metrics deserve attention first and why.",
            "metric-review",
            "This is a read-only metric review; underlying record access remains permission-scoped.",
            "dashboard", action_type="analyze",
        )]

    if page_type == "Workspace":
        return [_item(
            "Find the next workspace step",
            "Recommend the most relevant visible DocType, report or dashboard to open next.",
            "workspace-navigation",
            "Recommendations are limited to the current workspace navigation scope.",
            "workspace", action_type="navigate",
        )]
    return []


def _item(
    title: str,
    prompt: str,
    category: str,
    reason: str,
    source: str,
    *,
    action_type: str,
    requires_confirmation: bool = False,
    priority: str = "normal",
) -> dict[str, Any]:
    normalized_priority = priority if priority in {"high", "normal", "low"} else "normal"
    return {
        "id": _slug(title),
        "title": title,
        "prompt": prompt,
        "category": category,
        "reason": reason[:300],
        "source": source,
        "source_label": SOURCE_LABELS.get(source, "Page context"),
        "priority": normalized_priority,
        "action_type": action_type,
        "action_label": ACTION_LABELS.get(action_type, action_type.replace("_", " ").title()),
        "execution": "approval_preview" if requires_confirmation else "prompt",
        "requires_confirmation": requires_confirmation,
    }


def _page_summary(page_type: str, context: dict[str, Any], metadata: dict[str, Any], family: str) -> str:
    label = _context_label(context)
    family_label = family.replace("_", " ") if family != "general" else "general"
    if page_type == "Form":
        if _is_new_document(context.get("document_name")):
            return f"New {label} form in the {family_label} flow; guidance focuses on completion before saving."
        if metadata.get("is_submittable") or metadata.get("has_workflow_state"):
            return f"Existing {label} record with workflow signals; guidance focuses on readiness and next steps."
        return f"Existing {label} record; guidance focuses on completeness and safe review."
    if page_type == "List":
        return f"{label} list with {_filter_phrase(_filters(context)) or 'no active filters'}; guidance focuses on scoped follow-up."
    if page_type == "Report":
        return f"{label} report using {_filter_phrase(_filters(context)) or 'its current broad scope'}; guidance focuses on interpretation."
    if page_type == "Dashboard":
        return f"{label} dashboard with {metadata.get('card_count', 'visible')} metric signal(s); guidance focuses on prioritization."
    if page_type == "Workspace":
        return f"{label} workspace; guidance focuses on the next visible area to open."
    return f"{label} page; guidance is limited to the available route context."


def _signals(page_type: str, context: dict[str, Any], metadata: dict[str, Any], family: str) -> dict[str, Any]:
    filters = _filters(context)
    return {
        "page_type": page_type,
        "page_family": family,
        "filter_count": len(filters),
        "filter_fields": [str(key)[:80] for key in list(filters)[:8]],
        "has_filters": bool(filters),
        "is_new_record": page_type == "Form" and _is_new_document(context.get("document_name")),
        "metadata": metadata,
    }


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    allowed = {
        "required_fields", "field_names", "has_status", "has_workflow_state", "is_submittable",
        "field_count", "ref_doctype", "report_type", "card_count", "link_count", "module",
        "title_field", "is_tree",
    }
    clean: dict[str, Any] = {}
    for key in allowed:
        value = metadata.get(key)
        if key in {"required_fields", "field_names"} and isinstance(value, list):
            clean[key] = [str(item)[:80] for item in value[:30] if _safe_field_name(item)]
        elif isinstance(value, bool | int | float):
            clean[key] = value
        elif isinstance(value, str) and value:
            clean[key] = value[:120]
    return clean


def _can_action(context: dict[str, Any], action: str, adapter: PermissionAdapter | None, user: str | None) -> bool:
    if adapter is None:
        return False
    try:
        boundary = CopilotPermissionBoundary(adapter)
        authorize_action = getattr(boundary, "authorize_action", None)
        if not callable(authorize_action):
            return False
        authorize_action(context, action, user=user)
        return True
    except (PermissionDenied, AttributeError, KeyError, TypeError, ValueError):
        return False


def _context_label(context: dict[str, Any]) -> str:
    return str(
        context.get("doctype")
        or context.get("report_name")
        or context.get("dashboard_name")
        or context.get("workspace_name")
        or context.get("page_name")
        or "this page"
    )


def _filters(context: dict[str, Any]) -> dict[str, Any]:
    filters = context.get("filters")
    return filters if isinstance(filters, dict) else {}


def _filter_reason(filters: dict[str, Any]) -> str:
    phrase = _filter_phrase(filters)
    return f"Active filters define the current permitted scope: {phrase}." if phrase else "Active filters define the current permitted page scope."


def _filter_phrase(filters: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in list(filters.items())[:3]:
        if str(key).lower() in SENSITIVE_FIELD_TERMS or value in (None, "", "[redacted]"):
            continue
        if isinstance(value, list):
            display = ", ".join(str(item)[:40] for item in value[:3])
        else:
            display = str(value)[:60]
        if display:
            parts.append(f"{_humanize(str(key))} = {display}")
    return "; ".join(parts)


def _page_family(context: dict[str, Any], metadata: dict[str, Any]) -> str:
    values = [
        context.get("doctype"), context.get("report_name"), context.get("dashboard_name"),
        context.get("workspace_name"), metadata.get("module"), metadata.get("ref_doctype"),
    ]
    haystack = " ".join(str(value or "").lower().replace("_", " ") for value in values)
    for family, tokens in DOMAIN_TOKENS.items():
        if any(token in haystack for token in tokens):
            return family
    return "general"


def _has_status_filter(filters: dict[str, Any]) -> bool:
    return any("status" in str(key).lower() for key in filters)


def _is_new_document(value: Any) -> bool:
    return str(value or "").lower().startswith("new-")


def _safe_field_name(value: Any) -> bool:
    lowered = str(value or "").lower()
    return bool(lowered) and not any(term in lowered for term in SENSITIVE_FIELD_TERMS)


def _humanize(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def _slug(value: str) -> str:
    return "-".join(part.lower() for part in str(value).replace("/", " ").split() if part)
