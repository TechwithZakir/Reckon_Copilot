from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AnalyticsToolError(ValueError):
    """Raised when a request does not match an allowlisted analytics tool."""


@dataclass(frozen=True)
class AnalyticsToolSpec:
    name: str
    intent: str
    label: str
    allowed_page_types: frozenset[str]
    max_rows: int = 500


TOOL_SPECS = {
    "summarize_current_page": AnalyticsToolSpec(
        name="summarize_current_page",
        intent="summary",
        label="Summary",
        allowed_page_types=frozenset({"List", "Form", "Dashboard"}),
    ),
    "breakdown_current_page": AnalyticsToolSpec(
        name="breakdown_current_page",
        intent="breakdown",
        label="Breakdown",
        allowed_page_types=frozenset({"List", "Form", "Dashboard"}),
    ),
    "trend_current_page": AnalyticsToolSpec(
        name="trend_current_page",
        intent="trend",
        label="Trend",
        allowed_page_types=frozenset({"List", "Form", "Dashboard"}),
    ),
}


def route_tool(question: str, context: dict[str, Any]) -> AnalyticsToolSpec:
    """Route language to a fixed tool; user text never becomes executable code."""
    page_type = str(context.get("page_type") or "")
    text = str(question or "").lower()
    if any(term in text for term in ("trend", "over time", "monthly", "daily", "weekly", "growth")):
        spec = TOOL_SPECS["trend_current_page"]
    elif any(term in text for term in ("breakdown", "by ", "per ", "group", "distribution", "compare")):
        spec = TOOL_SPECS["breakdown_current_page"]
    else:
        spec = TOOL_SPECS["summarize_current_page"]
    if page_type not in spec.allowed_page_types:
        raise AnalyticsToolError(f"Analytics is not available for this {page_type.lower() or 'page'} context.")
    return spec


def get_tool(name: str) -> AnalyticsToolSpec:
    try:
        return TOOL_SPECS[str(name)]
    except KeyError as error:
        raise AnalyticsToolError("That analytics operation is not available.") from error
