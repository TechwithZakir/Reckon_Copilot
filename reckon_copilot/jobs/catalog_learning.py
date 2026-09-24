"""Scheduled candidate generation for administrator review."""

from __future__ import annotations


def generate_candidates() -> None:
    """Refresh pending advisor candidates without publishing or executing actions."""
    try:
        import frappe  # type: ignore

        from reckon_copilot.advisor.catalog import default_catalog
        from reckon_copilot.advisor.learning import (
            FrappeCatalogLearningRepository,
            generate_candidates as build_candidates,
            validate_candidate,
        )
        from reckon_copilot.permissions.boundary import FrappePermissionAdapter

        repository = FrappeCatalogLearningRepository(frappe)
        catalog = default_catalog()
        adapter = FrappePermissionAdapter(frappe)
        user = "Administrator"
        for candidate in build_candidates(repository, catalog):
            metadata = _installed_metadata(candidate.doctype, frappe)
            repository.save_candidate(validate_candidate(candidate, catalog, metadata, adapter, user))
    except Exception:
        # Scheduler failures must not affect ERPNext jobs or user requests.
        return None


def _installed_metadata(doctype: str, frappe):
    if not doctype:
        return {}
    try:
        meta = frappe.get_meta(doctype)
        return {
            "field_names": [
                str(getattr(field, "fieldname", ""))
                for field in getattr(meta, "fields", []) or []
                if getattr(field, "fieldname", "")
            ]
        }
    except Exception:
        return {}
