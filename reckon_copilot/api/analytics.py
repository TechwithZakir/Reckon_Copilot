from __future__ import annotations

import json
from typing import Any

from reckon_copilot.agents.analytics import AnalyticsError, FrappeAnalyticsDataSource, run_analytics
from reckon_copilot.context.builders import build_context
from reckon_copilot.context.dashboard import build_dashboard_snapshot, enrich_dashboard_context
from reckon_copilot.permissions import FrappePermissionAdapter, PermissionDenied
from reckon_copilot.providers.usage import FrappeUsageLogger


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        return lambda fn: fn
    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def run(
    question: str,
    context: dict[str, Any] | str | None = None,
    route: Any = None,
    filters: Any = None,
    page_type: str | None = None,
) -> dict[str, Any]:
    try:
        import frappe  # type: ignore

        payload = json.loads(context) if isinstance(context, str) else context
        if not isinstance(payload, dict):
            payload = build_context(route=route, filters=filters, page_type=page_type)
        user = getattr(frappe.session, "user", None)
        if payload.get("page_type") == "Dashboard":
            payload = enrich_dashboard_context(payload, frappe, user=user)
            payload["dashboard_snapshot"] = build_dashboard_snapshot(payload, frappe, user=user)
        return run_analytics(
            question,
            payload,
            user=user,
            permission_adapter=FrappePermissionAdapter(frappe),
            data_source=FrappeAnalyticsDataSource(frappe),
            usage_logger=FrappeUsageLogger(frappe),
        )
    except PermissionDenied as error:
        return {
            "ok": False,
            "access_denied": True,
            "agent": "analytics",
            "message": str(error),
        }
    except AnalyticsError as error:
        return {
            "ok": False,
            "agent": "analytics",
            "message": str(error),
        }
    except Exception:
        return {
            "ok": False,
            "agent": "analytics",
            "message": "Analytics could not complete for this page. No ERP data was changed.",
        }
