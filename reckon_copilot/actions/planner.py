from __future__ import annotations

from typing import Any

from reckon_copilot.context.builders import canonical_json
from reckon_copilot.knowledge.models import stable_hash
from reckon_copilot.permissions.boundary import (
    CopilotPermissionBoundary,
    FrappePermissionAdapter,
    PermissionDenied,
    PermissionAdapter,
)

ACTION_TYPES = {"create", "update", "delete", "submit", "approve"}
HIGH_RISK = {"delete", "submit", "approve"}


def plan_action(
    context: dict[str, Any],
    action: str,
    *,
    values: dict[str, Any] | None = None,
    editable_fields: list[dict[str, Any]] | None = None,
    user: str | None = None,
    permission_adapter: PermissionAdapter | None = None,
) -> dict[str, Any]:
    action_name = str(action or "").strip().lower()
    if action_name not in ACTION_TYPES:
        raise ValueError("Unsupported Copilot action")
    boundary = CopilotPermissionBoundary(permission_adapter or FrappePermissionAdapter())
    authorize_action = getattr(boundary, "authorize_action", None)
    if not callable(authorize_action):
        raise PermissionDenied("Copilot action permissions are updating; please retry shortly")
    authorized = authorize_action(context, action_name, user=user).context
    target = {
        "doctype": authorized.get("doctype"),
        "document_name": authorized.get("document_name"),
    }
    safe_values = _safe_values(values or {})
    plan = {
        "version": "v1",
        "action": action_name,
        "target": target,
        "values": safe_values,
        "requires_confirmation": True,
        "high_risk": action_name in HIGH_RISK,
        "execution": "preview_only",
        "user": user,
        "editable_fields": _safe_editable_fields(editable_fields or []),
    }
    plan["plan_hash"] = stable_hash(canonical_json(plan))
    return {"ok": True, "plan": plan}


def _safe_editable_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    protected = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "parent", "parentfield", "parenttype", "idx"}
    for item in fields[:40]:
        if not isinstance(item, dict):
            continue
        fieldname = str(item.get("fieldname") or "").strip()
        if not fieldname or fieldname in protected or item.get("read_only"):
            continue
        result.append({
            "fieldname": fieldname[:80],
            "label": str(item.get("label") or fieldname).strip()[:120],
            "fieldtype": str(item.get("fieldtype") or "Data")[:40],
        })
    return result


def _safe_values(values: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in list(values.items())[:30]:
        if str(key).lower() in {"password", "api_key", "token", "secret"}:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[str(key)[:80]] = value
        elif isinstance(value, list):
            clean[str(key)[:80]] = [str(item)[:160] for item in value[:10]]
    return clean
