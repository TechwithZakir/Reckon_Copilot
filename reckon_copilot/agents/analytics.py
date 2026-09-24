from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Protocol

from reckon_copilot.analytics.metrics import summarize_dashboard_snapshot, summarize_rows
from reckon_copilot.analytics.query_tools import AnalyticsToolError, AnalyticsToolSpec, route_tool
from reckon_copilot.permissions.boundary import (
    CAPABILITY_RUN_ANALYTICS,
    PermissionAdapter,
    authorize_context,
)
from reckon_copilot.providers.usage import FrappeUsageLogger, InMemoryUsageLogger, UsageRecord


class AnalyticsDataSource(Protocol):
    def fetch_rows(self, context: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        ...


class AnalyticsError(ValueError):
    """A safe, user-facing analytics failure."""


@dataclass(frozen=True)
class AnalyticsLimits:
    max_rows: int = 500
    max_seconds: float = 3.0


class InMemoryAnalyticsDataSource:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = list(rows or [])

    def fetch_rows(self, context: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows[:limit]]


class FrappeAnalyticsDataSource:
    """Permission-safe row access using Frappe ORM, never generated SQL."""

    NUMERIC_TYPES = {"Currency", "Float", "Int", "Percent", "Check"}
    DIMENSION_TYPES = {"Select", "Link", "Data", "Date", "Datetime"}

    def __init__(self, frappe_module: Any):
        self.frappe = frappe_module

    def fetch_rows(self, context: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        doctype = str(context.get("doctype") or "")
        if not doctype:
            return []
        meta = self.frappe.get_meta(doctype)
        fields = self._fields(meta)
        filters = self._filters(context.get("filters"), fields)
        getter = getattr(self.frappe, "get_list", None) or getattr(self.frappe.db, "get_list")
        kwargs = {
            "fields": fields,
            "filters": filters,
            "limit_page_length": min(max(int(limit), 1), 500),
        }
        if any(field == "modified" for field in fields):
            kwargs["order_by"] = "modified desc"
        return [dict(row) for row in getter(doctype, **kwargs)]

    def _fields(self, meta) -> list[str]:
        fields = ["name"]
        for field in list(getattr(meta, "fields", []) or []):
            fieldname = str(getattr(field, "fieldname", "") or "")
            fieldtype = str(getattr(field, "fieldtype", "") or "")
            if not fieldname or fieldname in fields or fieldtype not in self.NUMERIC_TYPES | self.DIMENSION_TYPES:
                continue
            fields.append(fieldname)
            if len(fields) >= 6:
                break
        return fields

    def _filters(self, value, fields: list[str]) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        allowed = set(fields)
        clean = {}
        for key, item in list(value.items())[:8]:
            if str(key) not in allowed:
                continue
            if isinstance(item, (str, int, float, bool)):
                clean[str(key)] = item
            elif isinstance(item, list) and len(item) <= 20:
                clean[str(key)] = item
        return clean


def run_analytics(
    question: str,
    context: dict[str, Any],
    *,
    user: str | None = None,
    permission_adapter: PermissionAdapter | None = None,
    data_source: AnalyticsDataSource | None = None,
    usage_logger: InMemoryUsageLogger | FrappeUsageLogger | None = None,
    limits: AnalyticsLimits | None = None,
) -> dict[str, Any]:
    limits = limits or AnalyticsLimits()
    started = time.monotonic()
    authorized = authorize_context(
        context,
        capability=CAPABILITY_RUN_ANALYTICS,
        user=user,
        adapter=permission_adapter,
    ).context
    try:
        tool = route_tool(question, authorized)
    except AnalyticsToolError as error:
        raise AnalyticsError(str(error)) from error

    if authorized.get("page_type") == "Dashboard" and isinstance(authorized.get("dashboard_snapshot"), dict):
        result = summarize_dashboard_snapshot(authorized["dashboard_snapshot"])
    else:
        if data_source is None:
            raise AnalyticsError("Analytics data is not available for this page yet.")
        rows = data_source.fetch_rows(authorized, min(tool.max_rows, limits.max_rows))
        if time.monotonic() - started > limits.max_seconds:
            raise AnalyticsError("This analysis took too long. Narrow the page filters and try again.")
        result = summarize_rows(rows, intent=tool.intent)

    result.update(
        {
            "ok": True,
            "agent": "analytics",
            "agent_version": "phase10-v1",
            "tool": tool.name,
            "tool_label": tool.label,
            "intent": tool.intent,
            "source": "Current page",
            "limits": {"max_rows": limits.max_rows, "max_seconds": limits.max_seconds},
        }
    )
    if usage_logger:
        usage_logger.log(
            UsageRecord(
                provider="analytics",
                model="deterministic",
                capability=CAPABILITY_RUN_ANALYTICS,
                status="ok",
                cache_hit=False,
                latency_ms=round((time.monotonic() - started) * 1000),
                response_chars=len(str(result.get("narrative") or "")),
                metadata={"tool": tool.name, "engine": result.get("engine")},
            )
        )
    return result
