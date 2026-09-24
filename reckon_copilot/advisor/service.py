from __future__ import annotations

from typing import Any

from reckon_copilot.permissions.boundary import (
    CAPABILITY_RUN_ANALYTICS,
    PermissionAdapter,
    authorize_context,
)


def get_advice(
    context: dict[str, Any],
    *,
    user: str | None = None,
    permission_adapter: PermissionAdapter | None = None,
) -> dict[str, Any]:
    authorized = authorize_context(
        context,
        capability=CAPABILITY_RUN_ANALYTICS,
        user=user,
        adapter=permission_adapter,
    ).context
    page_type = str(authorized.get("page_type") or "Page")
    label = str(
        authorized.get("doctype")
        or authorized.get("report_name")
        or authorized.get("dashboard_name")
        or authorized.get("workspace_name")
        or "this page"
    )
    questions = _questions(page_type, authorized)
    actions = _actions(page_type, authorized)
    return {
        "ok": True,
        "context_fingerprint": authorized.get("fingerprint"),
        "context_label": label,
        "questions": questions,
        "actions": actions,
    }


def _questions(page_type: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    if page_type == "List":
        filters = context.get("filters") if isinstance(context.get("filters"), dict) else {}
        result = [
            _item("Summarize this list", "Summarize the visible scope", "analysis"),
            _item("Which filters may help?", "Suggest filters for this list", "analysis"),
        ]
        if not filters:
            result.insert(0, _item("Find records needing attention", "Find operational risks in this list", "analysis"))
        return result
    if page_type == "Form":
        return [
            _item("Explain this document", "Explain this record and its workflow", "analysis"),
            _item("What should I review?", "Review this record for missing or risky information", "analysis"),
            _item("What happens next?", "Explain the next workflow step", "workflow"),
        ]
    if page_type == "Report":
        return [
            _item("Explain this report", "Explain the report scope and filters", "analysis"),
            _item("Summarize the report setup", "Summarize the configured report", "analysis"),
        ]
    if page_type == "Dashboard":
        return [_item("Explain these metrics", "Explain the current dashboard metrics", "analysis"), _item("What needs attention?", "Identify dashboard risk signals", "analysis")]
    return [_item("What can I do here?", f"Explain useful tasks for {context.get('page_name') or 'this page'}", "help")]


def _actions(page_type: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    if page_type == "Form" and str(context.get("document_name") or "").startswith("new-"):
        return [_item("Complete this draft", "Suggest missing fields before saving", "draft")]
    if page_type == "Form":
        return [_item("Prepare a workflow review", "Create a read-only review plan", "plan")]
    if page_type == "List":
        return [_item("Prepare a filtered review", "Create a read-only review plan for this list", "plan")]
    return []


def _item(title: str, prompt: str, category: str) -> dict[str, Any]:
    return {"title": title, "prompt": prompt, "category": category, "requires_confirmation": False}
