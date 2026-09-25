from __future__ import annotations

import json
from typing import Any

from reckon_copilot.actions.planner import plan_action
from reckon_copilot.actions.executor import ActionExecutionError, execute_confirmed_plan
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
        return _safe_error(str(error), access_denied=True)
    except (TypeError, ValueError) as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("The action preview could not be prepared. No ERP data was changed.")


@_whitelist(allow_guest=False)
def approve_preview(plan: Any = None) -> dict[str, Any]:
    """Confirm a visible preview and execute it once after native permission checks."""
    try:
        import frappe  # type: ignore
        payload = json.loads(plan) if isinstance(plan, str) else plan
        if not isinstance(payload, dict) or not payload.get("plan_hash"):
            return _safe_error("A valid action plan is required.")
        return execute_confirmed_plan(
            payload,
            frappe_module=frappe,
            user=frappe.session.user,
            site=getattr(frappe.local, "site", "default"),
        )
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (TypeError, ValueError) as error:
        return _safe_error(str(error))
    except ActionExecutionError as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("Action could not be completed. No changes were committed.")


def _safe_error(message: str, *, access_denied: bool = False) -> dict[str, Any]:
    result = {"ok": False, "message": str(message)[:500]}
    if access_denied:
        result["access_denied"] = True
    return result
