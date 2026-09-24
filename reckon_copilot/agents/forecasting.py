from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import time
from typing import Any

from reckon_copilot.agents.analytics import AnalyticsDataSource
from reckon_copilot.analytics.charts import build_chart
from reckon_copilot.permissions import boundary as permission_boundary
from reckon_copilot.providers.usage import FrappeUsageLogger, InMemoryUsageLogger, UsageRecord


# During a rolling bench deployment the API module can load before the new
# boundary module is available in every worker. Reuse the existing read-only
# analytics capability on those older workers instead of raising ImportError.
CAPABILITY_RUN_FORECASTING = getattr(
    permission_boundary,
    "CAPABILITY_RUN_FORECASTING",
    permission_boundary.CAPABILITY_RUN_ANALYTICS,
)
PermissionAdapter = permission_boundary.PermissionAdapter
authorize_context = permission_boundary.authorize_context


class ForecastingError(ValueError):
    """A safe, user-facing forecasting or anomaly analysis failure."""


@dataclass(frozen=True)
class ForecastingLimits:
    max_rows: int = 500
    max_seconds: float = 3.0
    horizon: int = 3
    min_points: int = 3
    max_points: int = 20


def run_forecasting(
    question: str,
    context: dict[str, Any],
    *,
    mode: str = "forecast",
    user: str | None = None,
    permission_adapter: PermissionAdapter | None = None,
    data_source: AnalyticsDataSource | None = None,
    usage_logger: InMemoryUsageLogger | FrappeUsageLogger | None = None,
    limits: ForecastingLimits | None = None,
) -> dict[str, Any]:
    limits = limits or ForecastingLimits()
    started = time.monotonic()
    authorized = authorize_context(
        context,
        capability=CAPABILITY_RUN_FORECASTING,
        user=user,
        adapter=permission_adapter,
    ).context
    intent = _route_intent(question, mode)
    series = _extract_dashboard_series(authorized.get("dashboard_snapshot"))
    source = "Current dashboard"
    if not series:
        if data_source is None:
            raise ForecastingError("Forecasting data is not available for this page yet.")
        rows = data_source.fetch_rows(authorized, min(limits.max_rows, 500))
        series = _extract_row_series(rows, limits.max_points)
        source = "Current page"

    if time.monotonic() - started > limits.max_seconds:
        raise ForecastingError("This analysis took too long. Narrow the page filters and try again.")

    if len(series) < limits.min_points:
        result = _insufficient_result(intent, len(series), limits, source)
    elif intent == "anomaly":
        result = _anomaly_result(series, limits, source)
    else:
        result = _forecast_result(series, limits, source)

    result.update(
        {
            "ok": True,
            "agent": "forecasting",
            "agent_version": "phase11-v1",
            "tool": "detect_current_page_anomalies" if intent == "anomaly" else "forecast_current_page",
            "tool_label": "Detect unusual values" if intent == "anomaly" else "Forecast the current page",
            "intent": intent,
            "source": source,
            "limits": {
                "max_rows": limits.max_rows,
                "max_seconds": limits.max_seconds,
                "horizon": limits.horizon,
                "min_points": limits.min_points,
            },
            "safety": {
                "read_only": True,
                "writes": False,
                "model_training": False,
                "method": "deterministic bounded calculation",
            },
        }
    )
    if usage_logger:
        usage_logger.log(
            UsageRecord(
                provider="forecasting",
                model="deterministic",
                capability=CAPABILITY_RUN_FORECASTING,
                status="ok",
                cache_hit=False,
                latency_ms=round((time.monotonic() - started) * 1000),
                response_chars=len(str(result.get("narrative") or "")),
                metadata={"tool": result["tool"], "points": len(series)},
            )
        )
    return result


def _route_intent(question: str, mode: str) -> str:
    explicit = str(mode or "").strip().lower()
    if explicit in {"anomaly", "anomalies", "outlier", "exceptions"}:
        return "anomaly"
    text = str(question or "").lower()
    return "anomaly" if any(term in text for term in ("anomal", "outlier", "unusual", "exception", "spike", "drop")) else "forecast"


def _extract_row_series(rows: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    safe_rows = [row for row in rows if isinstance(row, dict)][:500]
    if not safe_rows:
        return []
    fields = []
    for row in safe_rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    date_field = _choose_date_field(safe_rows, fields)
    if not date_field:
        return []
    numeric_fields = [
        field for field in fields
        if field != date_field and field not in {"name", "modified", "creation"}
        and sum(_number(row.get(field)) is not None for row in safe_rows) >= 2
    ]
    if not numeric_fields:
        return []
    value_field = numeric_fields[0]
    grouped: dict[str, list[float]] = {}
    for row in safe_rows:
        parsed = _parse_date(row.get(date_field))
        value = _number(row.get(value_field))
        if parsed is None or value is None or not math.isfinite(value):
            continue
        grouped.setdefault(parsed.isoformat(), []).append(value)
    return [
        {"label": label, "date": date.fromisoformat(label), "value": round(sum(values) / len(values), 6), "measure": value_field}
        for label, values in sorted(grouped.items())[:max_points]
    ]


def _extract_dashboard_series(snapshot: Any) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return []
    for chart in snapshot.get("charts") or []:
        if not isinstance(chart, dict):
            continue
        data = chart.get("data") if isinstance(chart.get("data"), dict) else {}
        labels = data.get("labels") if isinstance(data.get("labels"), list) else []
        series = data.get("series") if isinstance(data.get("series"), list) else []
        if not labels or not series or not isinstance(series[0], dict):
            continue
        values = series[0].get("values") if isinstance(series[0].get("values"), list) else []
        points = []
        for label, value in zip(labels, values):
            number = _number(value)
            if number is None or not math.isfinite(number):
                continue
            parsed = _parse_date(label)
            points.append({"label": str(label)[:80], "date": parsed, "value": round(number, 6), "measure": str(series[0].get("name") or chart.get("title") or "Value")[:120]})
        if len(points) >= 1:
            return points[:20]
    return []


def _choose_date_field(rows: list[dict[str, Any]], fields: list[str]) -> str | None:
    candidates = [field for field in fields if any(token in field.lower() for token in ("date", "month", "year", "period", "time"))]
    candidates += [field for field in fields if field not in candidates]
    return next((field for field in candidates if sum(_parse_date(row.get(field)) is not None for row in rows) >= 2), None)


def _forecast_result(series: list[dict[str, Any]], limits: ForecastingLimits, source: str) -> dict[str, Any]:
    values = [float(point["value"]) for point in series]
    last = values[-1]
    slope = (values[-1] - values[0]) / max(len(values) - 1, 1)
    horizon = min(max(limits.horizon, 1), 6)
    forecast_values = [round(last + slope * step, 2) for step in range(1, horizon + 1)]
    labels = [_future_label(series, step) for step in range(1, horizon + 1)]
    measure = series[-1].get("measure") or "value"
    direction = "increase" if slope > 0 else "decrease" if slope < 0 else "remain broadly stable"
    narrative = f"Based on {len(series)} permitted {measure} observations from {source.lower()}, the short-term outlook is expected to {direction}."
    if slope:
        narrative += f" The estimated change per period is {round(slope, 2)}."
    return {
        "narrative": narrative,
        "metrics": [
            {"label": "Historical points", "value": len(series)},
            {"label": "Latest value", "value": round(last, 2)},
            {"label": "Estimated change", "value": round(slope, 2)},
        ],
        "table": {
            "columns": [{"key": "period", "label": "Forecast period"}, {"key": "value", "label": str(measure).replace("_", " ").title()}],
            "rows": [{"period": label, "value": value} for label, value in zip(labels, forecast_values)],
        },
        "chart": build_chart(chart_type="line", title=f"Forecast: {str(measure).replace('_', ' ').title()}", labels=labels, dataset_label="Forecast", values=forecast_values),
        "forecast": {"method": "bounded linear trend", "horizon": horizon, "values": forecast_values, "confidence": "directional"},
        "anomalies": [],
    }


def _anomaly_result(series: list[dict[str, Any]], limits: ForecastingLimits, source: str) -> dict[str, Any]:
    anomalies = []
    for index in range(2, len(series)):
        history = [float(point["value"]) for point in series[max(0, index - 3):index]]
        expected = sum(history) / len(history)
        deviation = abs(float(series[index]["value"]) - expected)
        threshold = max(abs(expected) * 0.5, _standard_deviation(history) * 3, 1.0)
        if deviation <= threshold:
            continue
        score = round(deviation / threshold, 2)
        anomalies.append({
            "period": series[index]["label"],
            "value": round(float(series[index]["value"]), 2),
            "expected": round(expected, 2),
            "score": score,
            "severity": "high" if score >= 2 else "medium",
            "reason": "The value is materially outside its recent permitted history.",
        })
    measure = series[-1].get("measure") or "value"
    if anomalies:
        narrative = f"I found {len(anomalies)} unusual {measure} observation(s) in the permitted history from {source.lower()}. Review the flagged periods before relying on the trend."
    else:
        narrative = f"I found no material anomalies in the {len(series)} permitted {measure} observations reviewed from {source.lower()}."
    values = [point["value"] for point in series]
    return {
        "narrative": narrative,
        "metrics": [{"label": "Points reviewed", "value": len(series)}, {"label": "Anomalies", "value": len(anomalies)}],
        "table": {
            "columns": [{"key": "period", "label": "Period"}, {"key": "value", "label": str(measure).replace("_", " ").title()}],
            "rows": [{"period": point["label"], "value": point["value"]} for point in series[-limits.max_points:]],
        },
        "chart": build_chart(chart_type="line", title=f"Observed: {str(measure).replace('_', ' ').title()}", labels=[point["label"] for point in series], dataset_label="Observed", values=values),
        "forecast": {},
        "anomalies": anomalies[:limits.max_points],
    }


def _insufficient_result(intent: str, points: int, limits: ForecastingLimits, source: str) -> dict[str, Any]:
    action = "detect an anomaly" if intent == "anomaly" else "prepare a forecast"
    return {
        "narrative": f"I could not {action} yet. Only {points} permitted time points were available from {source.lower()}; at least {limits.min_points} are needed.",
        "metrics": [{"label": "Points available", "value": points}, {"label": "Points needed", "value": limits.min_points}],
        "table": {"columns": [], "rows": []},
        "chart": None,
        "forecast": {},
        "anomalies": [],
    }


def _future_label(series: list[dict[str, Any]], step: int) -> str:
    last_date = series[-1].get("date")
    if isinstance(last_date, date):
        interval = 1
        if len(series) > 1 and isinstance(series[-2].get("date"), date):
            interval = max(1, (last_date - series[-2]["date"]).days)
        return (last_date + timedelta(days=interval * step)).isoformat()
    return f"Forecast {step}"


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
