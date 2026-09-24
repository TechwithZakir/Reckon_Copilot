from __future__ import annotations

import json
from typing import Any

from reckon_copilot.advisor.service import get_advice
from reckon_copilot.permissions.boundary import FrappePermissionAdapter, PermissionDenied


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
        return get_advice(payload, user=frappe.session.user, permission_adapter=FrappePermissionAdapter(frappe))
    except PermissionDenied as error:
        return {"ok": False, "access_denied": True, "message": str(error), "questions": [], "actions": []}
