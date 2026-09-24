from __future__ import annotations

from datetime import date, datetime
from typing import Any


DEFAULT_MAX_POINTS = 20


def build_chart(
    *,
    chart_type: str,
    title: str,
    labels: list[Any],
    dataset_label: str,
    values: list[Any],
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, Any] | None:
    """Build a compact, JSON-safe chart payload for the Copilot UI."""
    safe_labels = [_safe_value(value) for value in labels[:max_points]]
    safe_values = [_safe_value(value) for value in values[:max_points]]
    if not safe_labels or not safe_values:
        return None
    size = min(len(safe_labels), len(safe_values))
    return {
        "type": "line" if chart_type == "line" else "bar",
        "title": str(title or "Chart")[:120],
        "labels": safe_labels[:size],
        "datasets": [{"label": str(dataset_label or "Series")[:80], "data": safe_values[:size]}],
    }


def build_snapshot_chart(chart: dict[str, Any], max_points: int = DEFAULT_MAX_POINTS) -> dict[str, Any] | None:
    data = chart.get("data") if isinstance(chart.get("data"), dict) else {}
    labels = data.get("labels") if isinstance(data.get("labels"), list) else []
    series = data.get("series") if isinstance(data.get("series"), list) else []
    prepared = []
    for item in series[:3]:
        if not isinstance(item, dict):
            continue
        values = item.get("values") if isinstance(item.get("values"), list) else []
        if values:
            prepared.append((str(item.get("name") or "Series"), values[:max_points]))
    if not labels or not prepared:
        return None
    size = min(len(labels), *(len(values) for _, values in prepared), max_points)
    if size < 1:
        return None
    chart_type = "line" if str(chart.get("kind") or "").lower() in {"line", "line chart"} else "bar"
    return {
        "type": chart_type,
        "title": str(chart.get("title") or "Chart")[:120],
        "labels": [_safe_value(value) for value in labels[:size]],
        "datasets": [
            {
                "label": label[:80],
                "data": [_safe_value(value) for value in values[:size]],
            }
            for label, values in prepared
        ],
    }


def _safe_value(value: Any) -> Any:
    if value is None or value == "":
        return "Unavailable"
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)[:160]
