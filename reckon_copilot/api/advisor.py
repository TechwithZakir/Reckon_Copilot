from __future__ import annotations

import json
from datetime import date
from typing import Any

from reckon_copilot.advisor.service import get_advice
from reckon_copilot.context.dashboard import build_dashboard_snapshot, enrich_dashboard_context
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
        authorized = enrich_dashboard_context(authorized, frappe, user=frappe.session.user)
        dashboard_snapshot = build_dashboard_snapshot(
            authorized,
            frappe,
            user=frappe.session.user,
        )
        result = get_advice(
            authorized,
            user=frappe.session.user,
            permission_adapter=adapter,
            metadata=_safe_page_metadata(authorized, frappe, dashboard_snapshot=dashboard_snapshot),
        )
        return result
    except PermissionDenied as error:
        return {"ok": False, "access_denied": True, "message": str(error), "questions": [], "actions": []}


def _safe_page_metadata(
    context: dict[str, Any],
    frappe: Any,
    *,
    dashboard_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read only compact structural metadata after route authorization.

    Only compact, permission-checked structural metadata and dashboard
    aggregates cross this endpoint. Raw document values, report rows and
    workspace content are never returned.
    """
    page_type = context.get("page_type")
    metadata: dict[str, Any] = {"current_date": _current_date(frappe)}
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
                    "link_fields": [
                        {
                            "label": str(getattr(field, "label", None) or getattr(field, "fieldname", ""))[:80],
                            "fieldname": str(getattr(field, "fieldname", ""))[:80],
                            "target": str(getattr(field, "options", None) or "")[:80],
                        }
                        for field in fields
                        if getattr(field, "fieldtype", "") in {"Link", "Dynamic Link"}
                    ][:10],
                    "table_fields": [
                        {
                            "label": str(getattr(field, "label", None) or getattr(field, "fieldname", ""))[:80],
                            "fieldname": str(getattr(field, "fieldname", ""))[:80],
                            "target": str(getattr(field, "options", None) or "")[:80],
                        }
                        for field in fields
                        if getattr(field, "fieldtype", "") in {"Table", "Table MultiSelect"}
                    ][:8],
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
        snapshot = dashboard_snapshot or build_dashboard_snapshot(
            context,
            frappe,
            user=getattr(getattr(frappe, "session", None), "user", None),
        )
        if snapshot:
            metadata["dashboard_snapshot"] = snapshot
            metadata["chart_count"] = len(snapshot.get("charts") or [])
            metadata["number_card_count"] = len(snapshot.get("number_cards") or [])
            metadata["card_count"] = metadata["chart_count"] + metadata["number_card_count"]
            metadata["chart_titles"] = [
                str(item.get("title") or "")[:120]
                for item in snapshot.get("charts") or []
                if item.get("title")
            ][:8]
            metadata["number_card_titles"] = [
                str(item.get("title") or "")[:120]
                for item in snapshot.get("number_cards") or []
                if item.get("title")
            ][:8]
    elif page_type == "Homepage":
        snapshot = context.get("homepage_snapshot")
        if isinstance(snapshot, dict):
            metadata["homepage_snapshot"] = snapshot
        metadata["briefing_scope"] = "user and company home context"
    elif page_type == "Workspace" and context.get("workspace_name"):
        try:
            workspace = frappe.get_doc("Workspace", context["workspace_name"])
            metadata["link_count"] = len(getattr(workspace, "links", []) or [])
            metadata["module"] = getattr(workspace, "module", None)
        except Exception:
            pass
    return metadata


def _current_date(frappe: Any) -> str:
    try:
        today = getattr(getattr(frappe, "utils", None), "today", None)
        if callable(today):
            return str(today())[:20]
    except Exception:
        pass
    return date.today().isoformat()
