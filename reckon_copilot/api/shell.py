"""Local configuration for the Phase 1 Copilot shell."""

from __future__ import annotations

from typing import Any

from reckon_copilot.api.preferences import get_preferences


PROMPTS = {
    "Form": ["Explain this document", "What should I review?"],
    "List": ["Summarize this list", "Which filters may help?"],
    "Report": ["Explain this report", "What does this report show?"],
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

    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def get_shell_config(page_type: str | None = None) -> dict[str, Any]:
    normalized_type = page_type if page_type in PROMPTS else "Page"
    return {
        "preferences": get_preferences(),
        "suggested_prompts": PROMPTS[normalized_type],
    }
