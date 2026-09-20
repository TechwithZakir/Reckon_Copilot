"""Authenticated per-user preferences for the Copilot shell."""

from __future__ import annotations

from typing import Any


DEFAULT_PREFERENCES = {
    "enabled": True,
    "notifications_enabled": True,
    "response_sound_enabled": False,
}
PREFERENCE_FIELDS = frozenset(DEFAULT_PREFERENCES)


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn

        return decorator

    return frappe.whitelist(**kwargs)


def require_authenticated_user(user: str | None) -> str:
    if not user or user == "Guest":
        raise PermissionError("Authentication is required")
    return user


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, "0", "false", "False"):
        return False
    if value in (1, "1", "true", "True"):
        return True
    raise ValueError("Preference values must be boolean")


def normalize_preference_updates(values: dict[str, Any]) -> dict[str, bool]:
    unknown = set(values) - PREFERENCE_FIELDS
    if unknown:
        raise ValueError(f"Unsupported preference fields: {', '.join(sorted(unknown))}")
    return {key: _as_bool(value) for key, value in values.items() if value is not None}


def _frappe_and_user():
    import frappe  # type: ignore

    try:
        user = require_authenticated_user(frappe.session.user)
    except PermissionError as exc:
        raise frappe.PermissionError(str(exc)) from exc
    return frappe, user


def _serialize(doc: Any | None) -> dict[str, bool]:
    if doc is None:
        return dict(DEFAULT_PREFERENCES)
    return {field: bool(doc.get(field)) for field in PREFERENCE_FIELDS}


@_whitelist(allow_guest=False)
def get_preferences() -> dict[str, bool]:
    frappe, user = _frappe_and_user()
    name = frappe.db.exists("Copilot User Preference", {"user": user})
    doc = frappe.get_doc("Copilot User Preference", name) if name else None
    return _serialize(doc)


@_whitelist(allow_guest=False, methods=["POST"])
def update_preferences(
    enabled: Any = None,
    notifications_enabled: Any = None,
    response_sound_enabled: Any = None,
) -> dict[str, bool]:
    frappe, user = _frappe_and_user()
    updates = normalize_preference_updates(
        {
            key: value
            for key, value in {
                "enabled": enabled,
                "notifications_enabled": notifications_enabled,
                "response_sound_enabled": response_sound_enabled,
            }.items()
            if value is not None
        }
    )

    name = frappe.db.exists("Copilot User Preference", {"user": user})
    if name:
        doc = frappe.get_doc("Copilot User Preference", name)
    else:
        doc = frappe.new_doc("Copilot User Preference")
        doc.user = user

    for field, value in updates.items():
        doc.set(field, value)

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    return _serialize(doc)
