from __future__ import annotations

import json
from typing import Any

from reckon_copilot.context.builders import build_context
from reckon_copilot.notifications.service import generate_notifications
from reckon_copilot.permissions import PermissionDenied


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn

        return decorator

    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def get_notifications(
    context: Any = None,
    route: Any = None,
    filters: Any = None,
    page_type: Any = None,
    evidence: Any = None,
    enabled: Any = True,
) -> dict[str, Any]:
    ctx = _parse_json(context) if context else build_context(route=route, filters=filters, page_type=page_type)
    ev = _parse_json(evidence) if evidence else []
    try:
        return generate_notifications(
            ctx,
            ev if isinstance(ev, list) else [],
            enabled=_as_bool(enabled),
        )
    except Exception as error:
        if not _is_permission_denial(error):
            raise
        return {
            "ok": False,
            "access_denied": True,
            "enabled": True,
            "counts": {"critical": 0, "warning": 1, "info": 0},
            "notifications": [
                {
                    "notification_id": "access-denied",
                    "title": "Copilot access is limited",
                    "message": str(error),
                    "level": "warning",
                    "source": "permission",
                    "source_id": "",
                    "action_label": "Review access",
                    "action_prompt": "Why is Copilot access limited?",
                    "dismissible": True,
                }
            ],
        }


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value) if value.strip() else {}
    return value


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() not in {"0", "false", "no"}


def _is_permission_denial(error: Exception) -> bool:
    return isinstance(error, (PermissionDenied, PermissionError)) or error.__class__.__name__ in {
        "PermissionDenied",
        "PermissionError",
    }
