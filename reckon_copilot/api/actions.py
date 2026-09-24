from __future__ import annotations

import json
from typing import Any

from reckon_copilot.actions.planner import plan_action
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
