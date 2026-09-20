"""Health/status endpoint for the Reckon Copilot app."""

from __future__ import annotations

from typing import Any

from reckon_copilot import __version__


def _frappe_version() -> str | None:
    try:
        import frappe  # type: ignore
    except Exception:
        return None

    return getattr(frappe, "__version__", None)


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn

        return decorator

    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def status() -> dict[str, Any]:
    """Return a small app health payload without touching ERPNext data."""
    return {
        "ok": True,
        "app": "reckon_copilot",
        "app_name": "Reckon Copilot",
        "version": __version__,
        "target": {
            "frappe": "v16+",
            "erpnext": "v16+",
        },
        "runtime": {
            "frappe_version": _frappe_version(),
        },
    }

