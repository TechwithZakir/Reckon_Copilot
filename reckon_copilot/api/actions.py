from __future__ import annotations

import json
from typing import Any

from reckon_copilot.actions.planner import plan_action
from reckon_copilot.actions.approval import issue_approval_token
from reckon_copilot.actions.executor import (
    ActionExecutionError,
    assert_same_form_target,
    execute_approved_plan,
)
from reckon_copilot.permissions.boundary import CopilotPermissionBoundary, FrappePermissionAdapter, PermissionDenied


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        return lambda fn: fn
    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def preview_action(context: Any = None, action: str = "", values: Any = None) -> dict[str, Any]:
    try:
        import frappe  # type: ignore
        ctx = json.loads(context) if isinstance(context, str) else context
        payload = json.loads(values) if isinstance(values, str) else values
        safe_context = ctx if isinstance(ctx, dict) else {}
        return plan_action(
            safe_context,
            action,
            values=payload if isinstance(payload, dict) else {},
            editable_fields=_editable_fields(frappe, safe_context),
            user=frappe.session.user,
            permission_adapter=FrappePermissionAdapter(frappe),
        )
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (TypeError, ValueError) as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("The action preview could not be prepared. No ERP data was changed.")


@_whitelist(allow_guest=False)
def approve_preview(plan: Any = None, context: Any = None) -> dict[str, Any]:
    """Issue a scoped approval token after rechecking the exact target."""
    try:
        import frappe  # type: ignore
        payload = json.loads(plan) if isinstance(plan, str) else plan
        if not isinstance(payload, dict) or not payload.get("plan_hash"):
            return _safe_error("A valid action plan is required.")
        current_context = _decode_dict(context)
        assert_same_form_target(payload, current_context)
        target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
        permission_context = {
            "page_type": "Form",
            "doctype": target.get("doctype"),
            "document_name": target.get("document_name"),
        }
        CopilotPermissionBoundary(FrappePermissionAdapter(frappe)).authorize_action(
            permission_context,
            str(payload.get("action") or ""),
            user=frappe.session.user,
        )
        secret = str(getattr(frappe, "conf", {}).get("encryption_key") or "")
        if not secret:
            return _safe_error("Approval signing is not configured for this site.")
        token = issue_approval_token(
            payload,
            user=frappe.session.user,
            site=getattr(frappe.local, "site", "default"),
            secret=secret,
        )
        return {"ok": True, "approved": True, "execution": "ready_to_execute", "approval_token": token}
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (TypeError, ValueError) as error:
        return _safe_error(str(error))
    except ActionExecutionError as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("Approval could not be recorded. No ERP data was changed.")


@_whitelist(allow_guest=False)
def execute_action(
    plan: Any = None,
    approval_token: str = "",
    context: Any = None,
) -> dict[str, Any]:
    """Execute only an unchanged plan with a user-scoped approval token."""
    try:
        import frappe  # type: ignore
        payload = json.loads(plan) if isinstance(plan, str) else plan
        if not isinstance(payload, dict) or not payload.get("plan_hash"):
            return {"ok": False, "message": "A valid approved plan is required."}
        current_context = _decode_dict(context)
        secret = str(getattr(frappe, "conf", {}).get("encryption_key") or "")
        if not secret:
            return {"ok": False, "message": "Approval signing is not configured."}
        return execute_approved_plan(
            payload,
            approval_token,
            frappe_module=frappe,
            user=frappe.session.user,
            site=getattr(frappe.local, "site", "default"),
            secret=secret,
            current_context=current_context,
        )
    except PermissionDenied as error:
        return {"ok": False, "access_denied": True, "message": str(error)}
    except (ActionExecutionError, ValueError) as error:
        return {"ok": False, "message": str(error)}
    except Exception:
        return {"ok": False, "message": "Action could not be completed. No changes were committed."}


def _safe_error(message: str, *, access_denied: bool = False) -> dict[str, Any]:
    result = {"ok": False, "message": str(message)[:500]}
    if access_denied:
        result["access_denied"] = True
    return result


def _decode_dict(value: Any) -> dict[str, Any] | None:
    payload = json.loads(value) if isinstance(value, str) else value
    return payload if isinstance(payload, dict) else None


def _editable_fields(frappe: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return safe field metadata for the explicit create/update editor."""
    doctype = str(context.get("doctype") or "").strip()
    if not doctype:
        return []
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return []
    fields = []
    for field in list(getattr(meta, "fields", []) or []):
        fieldtype = str(getattr(field, "fieldtype", "") or "")
        if fieldtype in {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table", "Table MultiSelect", "Attach", "Attach Image"}:
            continue
        fields.append({
            "fieldname": getattr(field, "fieldname", ""),
            "label": getattr(field, "label", ""),
            "fieldtype": fieldtype,
            "read_only": bool(getattr(field, "read_only", False)),
        })
    return fields
