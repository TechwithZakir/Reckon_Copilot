"""Whitelisted Phase 2 Desk context API."""

from __future__ import annotations

import re
from typing import Any

from reckon_copilot.context.builders import (
    build_context,
    canonicalize_workspace_routes,
    fingerprint_context,
    promote_workspace_slug_to_doctype,
)
from reckon_copilot.context.dashboard import enrich_dashboard_context
from reckon_copilot.permissions import PermissionDenied, authorize_context


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn

        return decorator

    return frappe.whitelist(**kwargs)


def _canonicalize_with_frappe(context: dict[str, Any]) -> dict[str, Any]:
    try:
        import frappe  # type: ignore
    except Exception:
        return context

    def workspace_exists(name: str) -> bool:
        return bool(frappe.db.exists("Workspace", name))

    def resolve_workspace(name: str) -> str | None:
        candidate = str(name or "").strip()
        if not candidate:
            return None

        exact = frappe.db.exists("Workspace", candidate)
        if exact:
            return str(exact if isinstance(exact, str) else candidate)

        # Private workspace URLs use a slug while the record keeps its title.
        # Compare normalized names without exposing workspace contents.
        wanted = _workspace_slug(candidate)
        try:
            records = frappe.get_all(
                "Workspace",
                fields=["name"],
                limit_page_length=0,
            )
        except Exception:
            return None
        for record in records or []:
            record_name = str(record.get("name") or "")
            if record_name and _workspace_slug(record_name) == wanted:
                return record_name
        return None

    def doctype_exists(name: str) -> bool:
        return bool(frappe.db.exists("DocType", name))

    def is_tree_doctype(name: str) -> bool:
        try:
            return bool(frappe.get_meta(name).is_tree)
        except Exception:
            return False

    canonical = canonicalize_workspace_routes(
        context,
        resolve_workspace=resolve_workspace,
        doctype_exists=doctype_exists,
    )
    return promote_workspace_slug_to_doctype(
        canonical,
        workspace_exists=workspace_exists,
        doctype_exists=doctype_exists,
        is_tree_doctype=is_tree_doctype,
    )


def _workspace_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


@_whitelist(allow_guest=False)
def get_context(
    route: Any = None,
    filters: Any = None,
    page_type: Any = None,
) -> dict[str, Any]:
    """Return a sanitized, permission-authorized context for the current Desk route."""
    context = build_context(route=route, filters=filters, page_type=page_type)
    context = _canonicalize_with_frappe(context)
    try:
        authorized = authorize_context(context)
    except Exception as error:
        if not _is_permission_denial(error):
            raise
        context["access_denied"] = True
        context["permission"] = {
            "mode": "frappe_boundary",
            "enforcement": "phase_3",
            "allowed": False,
            "reason": str(error),
        }
        context["fingerprint"] = fingerprint_context(context)
        return context
    result = authorized.context
    result = enrich_dashboard_context(
        result,
        _frappe_module(),
        user=_frappe_user(),
    )
    result["fingerprint"] = fingerprint_context(result)
    return result


def _frappe_module() -> Any:
    import frappe  # type: ignore

    return frappe


def _frappe_user() -> str | None:
    frappe = _frappe_module()
    return getattr(getattr(frappe, "session", None), "user", None)


def _is_permission_denial(error: Exception) -> bool:
    return isinstance(error, (PermissionDenied, PermissionError)) or error.__class__.__name__ in {
        "PermissionDenied",
        "PermissionError",
    }
