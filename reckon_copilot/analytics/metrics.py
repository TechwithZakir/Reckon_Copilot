from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from reckon_copilot.analytics.charts import build_chart, build_snapshot_chart

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - availability depends on the bench image
    pd = None


MAX_COLUMNS = 6
MAX_TABLE_ROWS = 20
MAX_CHART_POINTS = 20


def summarize_rows(rows: list[dict[str, Any]], intent: str = "summary") -> dict[str, Any]:
    safe_rows = [row for row in rows if isinstance(row, dict)][:500]
    if not safe_rows:
        return {
            "narrative": "No permitted records were found for this page and its current filters.",
            "row_count": 0,
            "metrics": [],
            "table": {"columns": [], "rows": []},
            "chart": None,
            "engine": "pandas" if pd is not None else "python",
        }

    fields = _field_names(safe_rows)
    numeric_fields = [field for field in fields if _is_numeric_field(safe_rows, field)]
    date_field = _date_field(safe_rows, fields)
    dimension_field = date_field if intent == "trend" and date_field else _dimension_field(safe_rows, fields, numeric_fields)
    metrics = _metrics(safe_rows, numeric_fields)

    if intent in {"breakdown", "trend"} and dimension_field:
        table, chart, narrative = _grouped_result(
            safe_rows,
            intent,
            dimension_field,
            numeric_fields[0] if numeric_fields else None,
        )
    else:
        table = _table(safe_rows, fields)
        chart = None
        narrative = _summary_narrative(len(safe_rows), metrics)

    return {
        "narrative": narrative,
        "row_count": len(safe_rows),
        "metrics": metrics,
        "table": table,
        "chart": chart,
        "engine": "pandas" if pd is not None else "python",
    }


def summarize_dashboard_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    title = str(snapshot.get("title") or "this dashboard")
    cards = [item for item in snapshot.get("number_cards") or [] if isinstance(item, dict)]
    charts = [item for item in snapshot.get("charts") or [] if isinstance(item, dict)]
    table_rows = []
    metrics = []
    for card in cards[:MAX_TABLE_ROWS]:
        label = str(card.get("title") or "Metric")[:120]
        value = _safe_value(card.get("value"))
        table_rows.append({"metric": label, "value": value})
        metrics.append({"label": label, "value": value})

    chart = _snapshot_chart(charts[0]) if charts else None
    visible = []
    if cards:
        visible.append(f"{len(cards)} KPI card(s)")
    if charts:
        visible.append(f"{len(charts)} chart(s)")
    if not visible:
        narrative = f"{title} has no readable KPI cards or charts for this user."
    else:
        narrative = f"{title} contains { ' and '.join(visible) }."
        if metrics:
            available = [f"{item['label']}: {item['value']}" for item in metrics if item["value"] != "Unavailable"]
            if available:
                narrative += " Visible values: " + "; ".join(available[:5]) + "."

    return {
        "narrative": narrative,
        "row_count": len(cards),
        "metrics": metrics,
        "table": {
            "columns": [
                {"key": "metric", "label": "Metric"},
                {"key": "value", "label": "Value"},
            ] if table_rows else [],
            "rows": table_rows,
        },
        "chart": chart,
        "engine": "dashboard_snapshot",
    }


def _grouped_result(rows, intent, dimension_field, numeric_field):
    groups: OrderedDict[str, list[float]] = OrderedDict()
    for row in rows:
        label = _group_label(row.get(dimension_field))
        groups.setdefault(label, [])
        if numeric_field:
            number = _number(row.get(numeric_field))
            if number is not None:
                groups[label].append(number)

    values = []
    for label, numbers in list(groups.items())[:MAX_CHART_POINTS]:
        values.append({"label": label, "value": round(sum(numbers), 2) if numeric_field else len(numbers)})
    metric_label = _label(numeric_field) if numeric_field else "Records"
    direction = "over time" if intent == "trend" else f"by {_label(dimension_field)}"
    highest = max(values, key=lambda item: item["value"], default=None)
    narrative = f"I found {len(rows)} permitted records and grouped {metric_label} {direction}."
    if highest:
        narrative += f" The highest group is {highest['label']} at {highest['value']}."
    return (
        {
            "columns": [
                {"key": "group", "label": _label(dimension_field)},
                {"key": "value", "label": metric_label},
            ],
            "rows": [{"group": item["label"], "value": item["value"]} for item in values],
        },
        build_chart(
            chart_type="line" if intent == "trend" else "bar",
            title=f"{metric_label} {direction}",
            labels=[item["label"] for item in values],
            dataset_label=metric_label,
            values=[item["value"] for item in values],
        ),
        narrative,
    )


def _metrics(rows, numeric_fields):
    result = [{"label": "Records", "value": len(rows)}]
    for field in numeric_fields[:3]:
        numbers = _numeric_summary_with_pandas(rows, field)
        if numbers is None:
            numbers = [_number(row.get(field)) for row in rows]
            numbers = [value for value in numbers if value is not None]
        if not numbers:
            continue
        result.extend(
            [
                {"label": f"Total {_label(field)}", "value": round(sum(numbers), 2)},
                {"label": f"Average {_label(field)}", "value": round(sum(numbers) / len(numbers), 2)},
            ]
        )
    return result[:7]


def _summary_narrative(row_count, metrics):
    parts = [f"I found {row_count} permitted records on this page."]
    for item in metrics[1:3]:
        parts.append(f"{item['label']}: {item['value']}.")
    return " ".join(parts)


def _table(rows, fields):
    fields = fields[:MAX_COLUMNS]
    return {
        "columns": [{"key": field, "label": _label(field)} for field in fields],
        "rows": [{field: _safe_value(row.get(field)) for field in fields} for row in rows[:MAX_TABLE_ROWS]],
    }


def _snapshot_chart(chart):
    return build_snapshot_chart(chart, max_points=MAX_CHART_POINTS)


def _field_names(rows):
    names = []
    for row in rows:
        for field in row:
            if field not in names and len(names) < MAX_COLUMNS:
                names.append(str(field))
    return names


def _numeric_summary_with_pandas(rows, field):
    if pd is None:
        return None
    try:
        series = pd.to_numeric(pd.DataFrame(rows).get(field), errors="coerce").dropna()
        return [float(value) for value in series.tolist()]
    except Exception:
        return None


def _is_numeric_field(rows, field):
    values = _numeric_summary_with_pandas(rows, field)
    if values is not None:
        return bool(values)
    return any(_number(row.get(field)) is not None for row in rows)


def _date_field(rows, fields):
    for field in fields:
        if any(_is_date(value) for value in (row.get(field) for row in rows)):
            return field
    return next((field for field in fields if any(token in field.lower() for token in ("date", "month", "year"))), None)


def _dimension_field(rows, fields, numeric_fields):
    for field in fields:
        if field in numeric_fields or field in {"name", "modified", "creation"}:
            continue
        values = {_label(row.get(field)) for row in rows}
        if 1 < len(values) <= MAX_CHART_POINTS:
            return field
    return None


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        text = str(value).replace(",", "").strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def _is_date(value):
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value[:10])
        return len(value) >= 8
    except ValueError:
        return False


def _label(value):
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return text.title() if text else "Unavailable"


def _group_label(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:19]
    if isinstance(value, str) and _is_date(value):
        return value[:19]
    return _label(value)


def _safe_value(value):
    if value is None or value == "":
        return "Unavailable"
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)[:160]
