from __future__ import annotations

import json
from typing import Any

from reckon_copilot.advisor.service import get_advice
from reckon_copilot.permissions.boundary import (
    FrappePermissionAdapter,
    PermissionDenied,
    authorize_context,
)


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        return lambda fn: fn
    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def get_agent_advice(context: dict[str, Any] | str | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(context) if isinstance(context, str) else context
        if not isinstance(payload, dict):
            return {"ok": False, "message": "Copilot context is unavailable."}
        import frappe  # type: ignore
        adapter = FrappePermissionAdapter(frappe)
        authorized = authorize_context(payload, user=frappe.session.user, adapter=adapter).context
        result = get_advice(
            authorized,
            user=frappe.session.user,
            permission_adapter=adapter,
            metadata=_safe_page_metadata(authorized, frappe),
        )
        return result
    except PermissionDenied as error:
        return {"ok": False, "access_denied": True, "message": str(error), "questions": [], "actions": []}


def _safe_page_metadata(context: dict[str, Any], frappe: Any) -> dict[str, Any]:
    """Read only compact structural metadata after route authorization.

    No document values, report rows, chart data or workspace content crosses
    this endpoint. This keeps the advisor useful without creating a side channel.
    """
    page_type = context.get("page_type")
    metadata: dict[str, Any] = {}
    if page_type in {"Form", "List"} and context.get("doctype"):
        try:
            meta = frappe.get_meta(context["doctype"])
            fields = list(getattr(meta, "fields", []) or [])
            metadata.update(
                {
                    "field_count": len(fields),
                    "field_names": [
                        getattr(field, "fieldname", "")
                        for field in fields
                        if getattr(field, "fieldname", "")
                    ][:30],
                    "required_fields": [
                        getattr(field, "label", None) or getattr(field, "fieldname", "")
                        for field in fields
                        if getattr(field, "reqd", False) and getattr(field, "fieldtype", "") not in {"Section Break", "Column Break"}
                    ][:8],
                    "has_status": any(getattr(field, "fieldname", "") == "status" for field in fields),
                    "has_workflow_state": any(getattr(field, "fieldname", "") == "workflow_state" for field in fields),
                    "is_submittable": bool(getattr(meta, "is_submittable", False)),
                    "module": getattr(meta, "module", None),
                    "title_field": getattr(meta, "title_field", None),
                    "is_tree": bool(getattr(meta, "is_tree", False)),
                }
            )
        except Exception:
            return metadata
    elif page_type == "Report" and context.get("report_name"):
        try:
            report = frappe.get_doc("Report", context["report_name"])
            metadata["report_type"] = getattr(report, "report_type", None)
            metadata["ref_doctype"] = getattr(report, "ref_doctype", None)
            metadata["module"] = getattr(report, "module", None)
        except Exception:
            pass
    elif page_type == "Dashboard" and context.get("dashboard_name"):
        try:
            dashboard = frappe.get_doc("Dashboard", context["dashboard_name"])
            metadata["card_count"] = len(getattr(dashboard, "charts", []) or []) + len(getattr(dashboard, "cards", []) or [])
            metadata["module"] = getattr(dashboard, "module", None)
        except Exception:
            pass
    elif page_type == "Workspace" and context.get("workspace_name"):
        try:
            workspace = frappe.get_doc("Workspace", context["workspace_name"])
            metadata["link_count"] = len(getattr(workspace, "links", []) or [])
            metadata["module"] = getattr(workspace, "module", None)
        except Exception:
            pass
    return metadata
