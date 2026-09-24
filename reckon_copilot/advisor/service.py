from __future__ import annotations

from typing import Any

from reckon_copilot.permissions.boundary import (
    CAPABILITY_RUN_ANALYTICS,
    CopilotPermissionBoundary,
    PermissionAdapter,
    PermissionDenied,
    authorize_context,
)


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
    label = str(
        authorized.get("doctype")
        or authorized.get("report_name")
        or authorized.get("dashboard_name")
        or authorized.get("workspace_name")
        or "this page"
    )
    questions = _questions(page_type, authorized, metadata)
    actions = _actions(page_type, authorized, adapter, user, metadata)
    return {
        "ok": True,
        "context_fingerprint": authorized.get("fingerprint"),
        "context_label": label,
        "questions": questions,
        "actions": actions,
        "signals": _signals(page_type, authorized, metadata),
    }


def _questions(page_type: str, context: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    if page_type == "List":
        filters = context.get("filters") if isinstance(context.get("filters"), dict) else {}
        result = [
            _item("Summarize this list", "Summarize the visible scope", "analysis", "Ask for a compact view of the current list scope.", "context"),
            _item("Which filters may help?", "Suggest filters for this list", "analysis", "Use the current DocType and filter state to narrow the review.", "context"),
        ]
        if not filters:
            result.insert(0, _item("Find records needing attention", "Find operational risks in this list", "analysis", "No filters are active, so an attention scan can start with the full permitted list scope.", "context", priority="high"))
        elif _has_status_filter(filters):
            result.insert(0, _item("Review this status slice", "Review the records in the selected status", "analysis", "The current filters include a status-like field.", "filter", priority="high"))
        return result
    if page_type == "Form":
        result = [_item("Explain this document", "Explain this record and its workflow", "analysis", "Use the permitted form context and DocType structure.", "context")]
        if metadata.get("required_fields"):
            result.append(_item("What is still required?", "Identify required fields that need review", "validation", "This DocType has required fields that are useful for a completion check.", "doctype", priority="high"))
        result.append(_item("What should I review?", "Review this record for missing or risky information", "analysis", "Check the record against its permitted fields and current workflow signals.", "context"))
        if metadata.get("has_workflow_state") or metadata.get("is_submittable"):
            reason = "This DocType exposes workflow or submission state."
            source = "doctype"
        else:
            reason = "Explain the next step from the current form route and available context."
            source = "context"
        result.append(_item("What happens next?", "Explain the next workflow step", "workflow", reason, source))
        return result
    if page_type == "Report":
        result = [_item("Explain this report", "Explain the report scope and filters", "analysis", "Start with the report identity and sanitized filters.", "context")]
        if context.get("filters"):
            result.append(_item("Review the active report filters", "Explain what the current report filters include", "analysis", "The report has active filters that define its scope.", "filter", priority="high"))
        if metadata.get("ref_doctype"):
            result.append(_item("Explain the source DocType", "Explain the DocType behind this report", "analysis", f"This report is linked to {metadata['ref_doctype']}.", "report"))
        return result
    if page_type == "Dashboard":
        result = [_item("Explain these metrics", "Explain the current dashboard metrics", "analysis", "Interpret the visible dashboard scope without exposing underlying rows.", "dashboard")]
        if metadata.get("card_count"):
            result.append(_item("Which metrics need attention?", "Identify dashboard metrics that need attention", "analysis", f"The dashboard contains {metadata['card_count']} configured metric card(s).", "dashboard"))
        return result
    if page_type == "Workspace":
        result = [_item("Explain this workspace", "Explain the useful areas in this workspace", "help", "Use the current workspace and its visible navigation context.", "workspace")]
        if metadata.get("link_count"):
            result.append(_item("What should I open first?", "Recommend the most relevant workspace area", "navigation", f"This workspace exposes {metadata['link_count']} visible link group(s).", "workspace"))
        return result
    return [_item("What can I do here?", f"Explain useful tasks for {context.get('page_name') or 'this page'}", "help", "No richer page metadata was available, so Copilot is keeping the suggestion general.", "context")]


def _actions(
    page_type: str,
    context: dict[str, Any],
    permission_adapter: PermissionAdapter | None,
    user: str | None,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    if page_type == "Form" and str(context.get("document_name") or "").startswith("new-"):
        if _can_action(context, "create", permission_adapter, user):
            return [_item("Complete this draft", "Suggest missing fields before saving", "draft", "The form is new and the user can create this DocType.", "permission", action_type="create", requires_confirmation=True)]
        return []
    if page_type == "Form":
        result = [_item("Prepare a workflow review", "Create a read-only review plan", "plan", "Build a read-only checklist from the current record and workflow metadata.", "context")]
        if _can_action(context, "update", permission_adapter, user):
            result.append(_item("Preview an update", "Prepare a preview of allowed record updates", "write-preview", "The user has native write permission for this record; execution still requires approval.", "permission", action_type="update", requires_confirmation=True))
        if metadata.get("is_submittable") and _can_action(context, "submit", permission_adapter, user):
            result.append(_item("Preview submission", "Prepare a preview of submitting this document", "write-preview", "The DocType is submittable and native submit permission is available; execution still requires approval.", "permission", action_type="submit", requires_confirmation=True, priority="high"))
        return result
    if page_type == "List":
        return [_item("Prepare a filtered review", "Create a read-only review plan for this list", "plan", "Create a review plan constrained to the current permitted list scope.", "context")]
    return []


def _item(
    title: str,
    prompt: str,
    category: str,
    reason: str,
    source: str,
    *,
    action_type: str | None = None,
    requires_confirmation: bool = False,
    priority: str = "normal",
) -> dict[str, Any]:
    item = {
        "id": _slug(title),
        "title": title,
        "prompt": prompt,
        "category": category,
        "reason": reason,
        "source": source,
        "priority": priority,
        "requires_confirmation": requires_confirmation,
    }
    if action_type:
        item["action_type"] = action_type
    return item


def _signals(page_type: str, context: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    filters = context.get("filters") if isinstance(context.get("filters"), dict) else {}
    return {
        "page_type": page_type,
        "filter_count": len(filters),
        "has_filters": bool(filters),
        "is_new_record": page_type == "Form" and str(context.get("document_name") or "").startswith("new-"),
        "metadata": metadata,
    }


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    allowed = {"required_fields", "has_status", "has_workflow_state", "is_submittable", "field_count", "ref_doctype", "report_type", "card_count", "link_count"}
    clean: dict[str, Any] = {}
    for key in allowed:
        value = metadata.get(key)
        if key == "required_fields" and isinstance(value, list):
            clean[key] = [str(item)[:80] for item in value[:8]]
        elif isinstance(value, bool | int | float):
            clean[key] = value
        elif isinstance(value, str) and value:
            clean[key] = value[:120]
    return clean


def _can_action(context: dict[str, Any], action: str, adapter: PermissionAdapter | None, user: str | None) -> bool:
    if adapter is None:
        return False
    try:
        CopilotPermissionBoundary(adapter).authorize_action(context, action, user=user)
        return True
    except (PermissionDenied, KeyError, TypeError, ValueError):
        return False


def _has_status_filter(filters: dict[str, Any]) -> bool:
    return any("status" in str(key).lower() for key in filters)


def _slug(value: str) -> str:
    return "-".join(part.lower() for part in str(value).replace("/", " ").split() if part)
