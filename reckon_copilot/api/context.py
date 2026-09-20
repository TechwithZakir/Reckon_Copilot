"""Whitelisted Phase 2 Desk context API."""

from __future__ import annotations

from typing import Any

from reckon_copilot.context.builders import build_context, fingerprint_context
from reckon_copilot.permissions import authorize_context


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn

        return decorator

    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def get_context(
    route: Any = None,
    filters: Any = None,
    page_type: Any = None,
) -> dict[str, Any]:
    """Return a sanitized, permission-authorized context for the current Desk route."""
    context = build_context(route=route, filters=filters, page_type=page_type)
    authorized = authorize_context(context)
    result = authorized.context
    result["fingerprint"] = fingerprint_context(result)
    return result
