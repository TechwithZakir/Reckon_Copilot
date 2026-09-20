"""Whitelisted Phase 2 Desk context API."""

from __future__ import annotations

from typing import Any

from reckon_copilot.context.builders import build_context


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn

        return decorator

    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def get_context(route: Any = None, filters: Any = None) -> dict[str, Any]:
    """Return a sanitized, versioned context for the current Desk route."""
    return build_context(route=route, filters=filters)
