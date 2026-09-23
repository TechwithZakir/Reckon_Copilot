from __future__ import annotations

import json
from typing import Any

from reckon_copilot.context.builders import build_context
from reckon_copilot.insights.service import generate_insights
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
def get_insights(
    context: Any = None,
    route: Any = None,
    filters: Any = None,
    page_type: Any = None,
    evidence: Any = None,
) -> dict[str, Any]:
    ctx = _parse_json(context) if context else build_context(route=route, filters=filters, page_type=page_type)
    ev = _parse_json(evidence) if evidence else []
    try:
        return generate_insights(ctx, ev if isinstance(ev, list) else [])
    except Exception as error:
        if not _is_permission_denial(error):
            raise
        return {
            "ok": False,
            "access_denied": True,
            "message": str(error),
            "counts": {"critical": 0, "warning": 1, "info": 0},
            "findings": [
                {
                    "finding_id": "access-denied",
                    "title": "Copilot access is limited",
                    "summary": str(error),
                    "severity": "warning",
                    "source": "permission",
                    "confidence": "high",
                    "suggested_prompts": [],
                    "suggested_actions": [],
                    "evidence_refs": [],
                }
            ],
        }


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value) if value.strip() else {}
    return value


def _is_permission_denial(error: Exception) -> bool:
    return isinstance(error, (PermissionDenied, PermissionError)) or error.__class__.__name__ in {
        "PermissionDenied",
        "PermissionError",
    }
