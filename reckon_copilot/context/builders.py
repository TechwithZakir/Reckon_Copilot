from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


CONTEXT_VERSION = "v1"
SUPPORTED_ROUTE_TYPES = {"Form", "List", "Report", "Dashboard", "Workspace"}
MAX_ROUTE_PARTS = 8
MAX_VALUE_LENGTH = 160
MAX_FILTERS = 20


@dataclass(frozen=True)
class ContextInput:
    route: tuple[str, ...]
    filters: dict[str, Any]
    page_type: str | None


def sanitize_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value).strip()
    if len(text) > MAX_VALUE_LENGTH:
        return f"{text[:MAX_VALUE_LENGTH]}..."
    return text


def sanitize_route(route: Any) -> tuple[str, ...]:
    if not isinstance(route, list | tuple):
        return ()

    parts: list[str] = []
    for value in route[:MAX_ROUTE_PARTS]:
        scalar = sanitize_scalar(value)
        if scalar is None:
            continue
        parts.append(str(scalar))
    return tuple(parts)


def sanitize_filters(filters: Any) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}

    clean: dict[str, Any] = {}
    for key in sorted(filters)[:MAX_FILTERS]:
        clean_key = str(sanitize_scalar(key) or "")
        if not clean_key:
            continue
        value = filters[key]
        if isinstance(value, list | tuple):
            clean[clean_key] = [sanitize_scalar(item) for item in value[:10]]
        elif isinstance(value, dict):
            clean[clean_key] = {
                str(sanitize_scalar(inner_key) or ""): sanitize_scalar(inner_value)
                for inner_key, inner_value in list(value.items())[:10]
            }
        else:
            clean[clean_key] = sanitize_scalar(value)
    return clean


def sanitize_page_type(page_type: Any = None) -> str | None:
    text = sanitize_scalar(page_type)
    if not isinstance(text, str):
        return None
    return text if text in SUPPORTED_ROUTE_TYPES else None


def normalize_context_input(
    route: Any = None,
    filters: Any = None,
    page_type: Any = None,
) -> ContextInput:
    return ContextInput(
        route=sanitize_route(route),
        filters=sanitize_filters(filters),
        page_type=sanitize_page_type(page_type),
    )


def route_type_for(parts: tuple[str, ...]) -> str:
    if not parts:
        return "Page"
    route_type = parts[0]
    return route_type if route_type in SUPPORTED_ROUTE_TYPES else "Page"


def humanize_slug(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(part.capitalize() for part in value.replace("_", "-").split("-") if part)


def _form_context(parts: tuple[str, ...], filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_type": "Form",
        "doctype": parts[1] if len(parts) > 1 else None,
        "document_name": parts[2] if len(parts) > 2 else None,
        "filters": filters,
    }


def _list_context(parts: tuple[str, ...], filters: dict[str, Any]) -> dict[str, Any]:
    doctype = parts[1] if len(parts) > 1 else None
    if len(parts) == 1:
        doctype = humanize_slug(parts[0])
    return {
        "page_type": "List",
        "doctype": doctype,
        "view": parts[2] if len(parts) > 2 else None,
        "filters": filters,
    }


def _report_context(parts: tuple[str, ...], filters: dict[str, Any]) -> dict[str, Any]:
    report_name = parts[1] if len(parts) > 1 else None
    if len(parts) == 1:
        report_name = humanize_slug(parts[0])
    return {
        "page_type": "Report",
        "report_name": report_name,
        "filters": filters,
    }


def _dashboard_context(parts: tuple[str, ...], filters: dict[str, Any]) -> dict[str, Any]:
    dashboard_name = parts[1] if len(parts) > 1 else None
    if len(parts) == 1:
        dashboard_name = humanize_slug(parts[0])
    return {
        "page_type": "Dashboard",
        "dashboard_name": dashboard_name,
        "filters": filters,
    }


def _workspace_context(parts: tuple[str, ...], filters: dict[str, Any]) -> dict[str, Any]:
    workspace_name = parts[1] if len(parts) > 1 else None
    if len(parts) == 1:
        workspace_name = humanize_slug(parts[0])
    return {
        "page_type": "Workspace",
        "workspace_name": workspace_name,
        "filters": filters,
    }


def _page_context(parts: tuple[str, ...], filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_type": "Page",
        "page_name": parts[0] if parts else None,
        "filters": filters,
    }


ADAPTERS = {
    "Form": _form_context,
    "List": _list_context,
    "Report": _report_context,
    "Dashboard": _dashboard_context,
    "Workspace": _workspace_context,
    "Page": _page_context,
}


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint_context(context: dict[str, Any]) -> str:
    payload = {key: value for key, value in context.items() if key != "fingerprint"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_context(route: Any = None, filters: Any = None, page_type: Any = None) -> dict[str, Any]:
    normalized = normalize_context_input(route=route, filters=filters, page_type=page_type)
    route_type = normalized.page_type or route_type_for(normalized.route)
    adapter = ADAPTERS[route_type]
    context = {
        "version": CONTEXT_VERSION,
        "source": "desk_route",
        "route": list(normalized.route),
        "permission": {
            "mode": "sanitized_route_only",
            "enforcement": "phase_3",
        },
        **adapter(normalized.route, normalized.filters),
    }
    context["fingerprint"] = fingerprint_context(context)
    return context
