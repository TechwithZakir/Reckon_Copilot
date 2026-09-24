"""Compact, permission-aware snapshots for Desk dashboards.

Dashboard routes are useful to a person only when Copilot can name the visible
charts and KPI cards. This module deliberately returns aggregates and layout
metadata, never document rows or raw dashboard records.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

from reckon_copilot.context.builders import fingerprint_context


MAX_COMPONENTS = 8
MAX_DATA_POINTS = 8
MAX_TEXT = 120


def enrich_dashboard_context(
    context: dict[str, Any],
    frappe_module: Any,
    *,
    user: str | None = None,
) -> dict[str, Any]:
    """Attach a fresh dashboard snapshot to an already authorized context."""

    if context.get("page_type") != "Dashboard":
        return context

    snapshot = build_dashboard_snapshot(context, frappe_module, user=user)
    if not snapshot:
        return context

    enriched = dict(context)
    enriched["dashboard_snapshot"] = snapshot
    enriched["fingerprint"] = fingerprint_context(enriched)
    return enriched


def build_dashboard_snapshot(
    context: dict[str, Any],
    frappe_module: Any,
    *,
    user: str | None = None,
) -> dict[str, Any]:
    """Read visible dashboard blocks and small aggregate results from Frappe.

    Frappe v16 stores modern Desk dashboards as Workspace content. Older
    installations can still expose Dashboard child tables, so both shapes are
    supported. Linked chart/card documents are checked before they are read.
    """

    dashboard_name = str(context.get("dashboard_name") or "").strip()
    if not dashboard_name:
        return {}

    dashboard = _load_permitted_doc(frappe_module, "Dashboard", dashboard_name, user)
    source = "Dashboard"
    component_names = _component_names(dashboard) if dashboard is not None else ([], [])
    if dashboard is None or not any(component_names):
        workspace = _load_permitted_doc(frappe_module, "Workspace", dashboard_name, user)
        if workspace is not None:
            dashboard = workspace
            source = "Workspace"
    if dashboard is None:
        return {}

    chart_names, number_card_names = _component_names(dashboard)
    charts = []
    for name in chart_names[:MAX_COMPONENTS]:
        chart = _load_permitted_doc(frappe_module, "Dashboard Chart", name, user)
        if chart is None:
            continue
        item = _chart_summary(chart)
        data = _chart_data(frappe_module, name, chart, context.get("filters") or {})
        if data:
            item["data"] = data
        charts.append(item)

    number_cards = []
    for name in number_card_names[:MAX_COMPONENTS]:
        card = _load_permitted_doc(frappe_module, "Number Card", name, user)
        if card is None:
            continue
        item = _number_card_summary(card)
        value = _number_card_value(frappe_module, card, context.get("filters") or {})
        if value is not None:
            item["value"] = value
            item["status"] = "available"
        number_cards.append(item)

    if not charts and not number_cards:
        return {
            "title": dashboard_name,
            "source": source,
            "filters": _compact_filters(context.get("filters") or {}),
            "charts": [],
            "number_cards": [],
            "summary": f"{dashboard_name} dashboard has no readable chart or KPI data.",
        }

    visible_parts = []
    if number_cards:
        visible_parts.append(f"{len(number_cards)} KPI card(s)")
    if charts:
        visible_parts.append(f"{len(charts)} chart(s)")
    summary = f"{dashboard_name} dashboard contains " + " and ".join(visible_parts) + "."
    values = [
        f"{item['title']}: {item['value']}"
        for item in number_cards
        if item.get("value") is not None
    ]
    if values:
        summary += " Visible KPI values: " + "; ".join(values[:5]) + "."
    chart_titles = [str(item.get("title") or "") for item in charts if item.get("title")]
    if chart_titles:
        summary += " Charts: " + ", ".join(chart_titles[:5]) + "."

    return {
        "title": dashboard_name,
        "source": source,
        "filters": _compact_filters(context.get("filters") or {}),
        "charts": charts,
        "number_cards": number_cards,
        "summary": summary[:900],
    }


def _component_names(dashboard: Any) -> tuple[list[str], list[str]]:
    charts: list[str] = []
    cards: list[str] = []
    for row in list(getattr(dashboard, "charts", []) or []):
        _append_name(charts, _row_value(row, "chart_name", "chart", "dashboard_chart"))
    for row in list(getattr(dashboard, "cards", []) or []):
        _append_name(cards, _row_value(row, "number_card_name", "card", "number_card"))
    for row in list(getattr(dashboard, "number_cards", []) or []):
        _append_name(cards, _row_value(row, "number_card_name", "card", "number_card"))

    content = _parse_json(getattr(dashboard, "content", None))
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").lower()
            data = block.get("data") if isinstance(block.get("data"), dict) else block
            if block_type == "chart":
                _append_name(charts, _row_value(data, "chart_name", "chart", "name"))
            elif block_type in {"number_card", "number-card", "card"}:
                _append_name(cards, _row_value(data, "number_card_name", "card", "name"))
    return charts, cards


def _chart_summary(chart: Any) -> dict[str, Any]:
    name = str(getattr(chart, "name", "") or "")
    return {
        "name": name[:MAX_TEXT],
        "title": str(getattr(chart, "chart_name", None) or name)[:MAX_TEXT],
        "kind": str(getattr(chart, "type", None) or getattr(chart, "chart_type", None) or "unknown")[:40],
        "aggregation": str(getattr(chart, "chart_type", None) or "")[:40],
        "source_doctype": str(getattr(chart, "document_type", None) or "")[:MAX_TEXT],
        "report_name": str(getattr(chart, "report_name", None) or "")[:MAX_TEXT],
        "measure": str(getattr(chart, "based_on", None) or getattr(chart, "value_based_on", None) or "")[:MAX_TEXT],
        "group_by": str(getattr(chart, "group_by", None) or "")[:MAX_TEXT],
        "timespan": str(getattr(chart, "timespan", None) or "")[:40],
        "time_interval": str(getattr(chart, "time_interval", None) or "")[:40],
        "status": "configured",
    }


def _number_card_summary(card: Any) -> dict[str, Any]:
    name = str(getattr(card, "name", "") or "")
    return {
        "name": name[:MAX_TEXT],
        "title": str(getattr(card, "label", None) or name)[:MAX_TEXT],
        "kind": str(getattr(card, "type", None) or "unknown")[:40],
        "source_doctype": str(getattr(card, "document_type", None) or "")[:MAX_TEXT],
        "function": str(getattr(card, "function", None) or "")[:40],
        "measure": str(getattr(card, "aggregate_function_based_on", None) or "")[:MAX_TEXT],
        "status": "configured",
    }


def _chart_data(frappe_module: Any, name: str, chart: Any, filters: Any) -> dict[str, Any]:
    try:
        chart_api = importlib.import_module("frappe.desk.doctype.dashboard_chart.dashboard_chart")
        getter = getattr(chart_api, "get")
        chart_filters = _parse_json(getattr(chart, "filters_json", None)) or []
        if not isinstance(chart_filters, list):
            chart_filters = []
        document_type = str(getattr(chart, "document_type", None) or "")
        if isinstance(filters, dict) and document_type:
            chart_filters.extend(
                [[document_type, key, "=", value] for key, value in list(filters.items())[:8]]
            )
        result = getter(chart_name=name, filters=json.dumps(chart_filters))
    except Exception:
        return {}
    if not isinstance(result, dict):
        return {}
    compact: dict[str, Any] = {}
    labels = result.get("labels")
    if isinstance(labels, list):
        compact["labels"] = [_safe_value(value) for value in labels[:MAX_DATA_POINTS]]
    datasets = result.get("datasets")
    if isinstance(datasets, list):
        series = []
        for dataset in datasets[:4]:
            if not isinstance(dataset, dict):
                continue
            values = dataset.get("values") if isinstance(dataset.get("values"), list) else dataset.get("data")
            if not isinstance(values, list):
                continue
            series.append(
                {
                    "name": str(dataset.get("name") or dataset.get("label") or "Series")[:MAX_TEXT],
                    "values": [_safe_value(value) for value in values[:MAX_DATA_POINTS]],
                }
            )
        if series:
            compact["series"] = series
    if "value" in result and isinstance(result.get("value"), int | float):
        compact["value"] = result["value"]
    points = result.get("dataPoints")
    if isinstance(points, dict):
        compact["points"] = [
            {"date": str(key)[:40], "value": _safe_number(value)}
            for key, value in list(points.items())[:MAX_DATA_POINTS]
        ]
    return compact


def _number_card_value(frappe_module: Any, card: Any, page_filters: Any) -> int | float | None:
    if str(getattr(card, "type", "Document Type") or "Document Type") != "Document Type":
        return None
    document_type = str(getattr(card, "document_type", None) or "")
    function = str(getattr(card, "function", None) or "")
    if not document_type or not function:
        return None
    try:
        module = importlib.import_module("frappe.desk.doctype.number_card.number_card")
        getter = getattr(module, "get_result")
        doc = card.as_dict() if callable(getattr(card, "as_dict", None)) else card
        filters = _parse_json(getattr(card, "filters_json", None)) or []
        if not filters and isinstance(page_filters, dict):
            filters = [[document_type, key, "=", value] for key, value in list(page_filters.items())[:8]]
        value = getter(doc=doc, filters=filters)
    except Exception:
        return None
    return _safe_number(value)


def _load_permitted_doc(frappe_module: Any, doctype: str, name: str, user: str | None) -> Any | None:
    if not _has_permission(frappe_module, doctype, name, user):
        return None
    try:
        return frappe_module.get_doc(doctype, name)
    except Exception:
        return None


def _has_permission(frappe_module: Any, doctype: str, name: str, user: str | None) -> bool:
    checker = getattr(frappe_module, "has_permission", None)
    if not callable(checker):
        return True
    try:
        return bool(checker(doctype, ptype="read", doc=name, user=user))
    except TypeError:
        try:
            return bool(checker(doctype, doc=name, user=user))
        except Exception:
            return False
    except Exception:
        return False


def _row_value(row: Any, *keys: str) -> Any:
    if isinstance(row, dict):
        return next((row.get(key) for key in keys if row.get(key)), None)
    return next((getattr(row, key, None) for key in keys if getattr(row, key, None)), None)


def _append_name(names: list[str], value: Any) -> None:
    name = str(value or "").strip()
    if name and name not in names:
        names.append(name)


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def _compact_filters(filters: Any) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}
    return {str(key)[:MAX_TEXT]: _safe_value(value) for key, value in list(filters.items())[:8]}


def _safe_value(value: Any) -> Any:
    number = _safe_number(value)
    if number is not None:
        return number
    if isinstance(value, bool):
        return value
    return str(value or "")[:MAX_TEXT]


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number
