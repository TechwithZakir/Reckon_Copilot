"""Local configuration for the Phase 1 Copilot shell."""

from __future__ import annotations

from typing import Any

from reckon_copilot.api.preferences import get_preferences


PROMPTS = {
    "Form": ["Explain this document", "What should I review?"],
    "List": ["Summarize this list", "Which filters may help?"],
    "Report": ["Explain this report", "What does this report show?"],
    "Dashboard": ["Explain these metrics", "What changed recently?"],
    "Workspace": ["What can I do here?", "Show common tasks"],
    "Page": ["What is this page?", "Show available help"],
}


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        def decorator(fn):
            return fn

        return decorator

    whitelist = getattr(frappe, "whitelist", None)
    if not callable(whitelist):
        def decorator(fn):
            return fn

        return decorator
    return whitelist(**kwargs)


@_whitelist(allow_guest=False)
def get_shell_config(page_type: str | None = None) -> dict[str, Any]:
    normalized_type = page_type if page_type in PROMPTS else "Page"
    try:
        from reckon_copilot.providers.manager import provider_config_from_frappe
        provider = provider_config_from_frappe()
        models = list(provider.allowed_models or ((provider.model,) if provider.model else ()))
    except Exception:
        models = []
    return {
        "preferences": get_preferences(),
        "suggested_prompts": PROMPTS[normalized_type],
        "models": models,
    }


def can_access_copilot_app() -> bool:
    try:
        import frappe  # type: ignore
    except Exception:
        return False
    user = getattr(frappe.session, "user", "Guest")
    if user == "Administrator":
        return True
    return "System Manager" in set(frappe.get_roles(user) or [])
