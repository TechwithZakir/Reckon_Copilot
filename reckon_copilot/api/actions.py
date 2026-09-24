from __future__ import annotations

import json
from typing import Any

from reckon_copilot.actions.planner import plan_action
from reckon_copilot.actions.approval import issue_approval_token
from reckon_copilot.actions.executor import ActionExecutionError, execute_approved_plan
from reckon_copilot.permissions.boundary import FrappePermissionAdapter, PermissionDenied


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
        return plan_action(
            ctx if isinstance(ctx, dict) else {},
            action,
            values=payload if isinstance(payload, dict) else {},
            user=frappe.session.user,
            permission_adapter=FrappePermissionAdapter(frappe),
        )
    except PermissionDenied as error:
        return {"ok": False, "access_denied": True, "message": str(error)}


@_whitelist(allow_guest=False)
def approve_preview(plan: Any = None) -> dict[str, Any]:
    """Issue scoped approval only; this endpoint never executes a write."""
    import frappe  # type: ignore
    payload = json.loads(plan) if isinstance(plan, str) else plan
    if not isinstance(payload, dict) or not payload.get("plan_hash"):
        return {"ok": False, "message": "A valid action plan is required."}
    secret = str(getattr(frappe, "conf", {}).get("encryption_key") or "")
    if not secret:
        return {"ok": False, "message": "Approval signing is not configured."}
    token = issue_approval_token(
        payload,
        user=frappe.session.user,
        site=getattr(frappe.local, "site", "default"),
        secret=secret,
    )
    return {"ok": True, "approved": True, "execution": "disabled", "approval_token": token}


@_whitelist(allow_guest=False)
def execute_action(plan: Any = None, approval_token: str = "") -> dict[str, Any]:
    """Execute only an unchanged plan with a user-scoped approval token."""
    import frappe  # type: ignore

    payload = json.loads(plan) if isinstance(plan, str) else plan
    if not isinstance(payload, dict) or not payload.get("plan_hash"):
        return {"ok": False, "message": "A valid approved plan is required."}
    secret = str(getattr(frappe, "conf", {}).get("encryption_key") or "")
    if not secret:
        return {"ok": False, "message": "Approval signing is not configured."}
    try:
        return execute_approved_plan(
            payload,
            approval_token,
            frappe_module=frappe,
            user=frappe.session.user,
            site=getattr(frappe.local, "site", "default"),
            secret=secret,
        )
    except PermissionDenied as error:
        return {"ok": False, "access_denied": True, "message": str(error)}
    except (ActionExecutionError, ValueError) as error:
        return {"ok": False, "message": str(error)}
    except Exception:
        return {"ok": False, "message": "Action could not be completed. No changes were committed."}
