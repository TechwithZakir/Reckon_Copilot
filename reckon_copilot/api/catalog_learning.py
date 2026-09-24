"""Admin-gated feedback learning endpoints for the advisor catalog."""

from __future__ import annotations

import json
from typing import Any

from reckon_copilot.advisor.catalog import default_catalog
from reckon_copilot.advisor.learning import (
    FrappeCatalogLearningRepository,
    generate_candidates,
    publish_candidate,
    record_feedback,
    validate_candidate,
)
from reckon_copilot.permissions.boundary import FrappePermissionAdapter, PermissionDenied, authorize_context


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        return lambda fn: fn
    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def record_suggestion_feedback(
    template_id: str | None = None,
    outcome: str | None = None,
    context: dict[str, Any] | str | None = None,
    catalog_version: str = "1",
) -> dict[str, Any]:
    """Record a coarse outcome without storing user, document or prompt data."""
    try:
        import frappe  # type: ignore

        payload = _json_object(context)
        adapter = FrappePermissionAdapter(frappe)
        safe_context = {}
        if payload:
            safe_context = authorize_context(payload, user=frappe.session.user, adapter=adapter).context
        repository = FrappeCatalogLearningRepository(frappe)
        aggregate = record_feedback(repository, str(template_id or ""), str(outcome or ""), safe_context, catalog_version)
        return {
            "ok": True,
            "recorded": True,
            "feedback_key": aggregate.feedback_key,
            "total_count": aggregate.total_count,
        }
    except (PermissionDenied, ValueError, TypeError):
        return {"ok": True, "recorded": False, "message": "Feedback was not recorded for this page."}
    except Exception:
        # Feedback is advisory telemetry and must never interrupt Desk work.
        return {"ok": True, "recorded": False, "message": "Feedback is temporarily unavailable."}


@_whitelist(allow_guest=False)
def generate_catalog_candidates() -> dict[str, Any]:
    """Generate and validate pending candidates; never publishes or writes ERP data."""
    try:
        import frappe  # type: ignore

        user = frappe.session.user
        if not _is_admin(frappe, user):
            return {"ok": False, "message": "Administrator approval is required."}
        repository = FrappeCatalogLearningRepository(frappe)
        catalog = default_catalog()
        adapter = FrappePermissionAdapter(frappe)
        candidates = generate_candidates(repository, catalog)
        known = {candidate.candidate_key for candidate in candidates}
        candidates.extend(
            candidate
            for candidate in repository.list_candidates()
            if candidate.status == "PENDING" and candidate.candidate_key not in known
        )
        validated = []
        for candidate in candidates:
            metadata = _installed_metadata(candidate.doctype, frappe)
            checked = validate_candidate(candidate, catalog, metadata, adapter, user)
            repository.save_candidate(checked)
            validated.append(checked.as_dict())
        return {"ok": True, "generated": len(validated), "candidates": validated}
    except Exception:
        return {"ok": False, "message": "Candidate generation is temporarily unavailable.", "candidates": []}


@_whitelist(allow_guest=False)
def approve_catalog_candidate(candidate_key: str | None = None) -> dict[str, Any]:
    """Publish exactly one validated candidate after a System Manager approval."""
    try:
        import frappe  # type: ignore

        user = frappe.session.user
        if not _is_admin(frappe, user):
            return {"ok": False, "message": "Only an administrator can publish a candidate."}
        repository = FrappeCatalogLearningRepository(frappe)
        candidate = repository.get_candidate(str(candidate_key or ""))
        if candidate is None:
            return {"ok": False, "message": "Candidate was not found."}
        template = publish_candidate(repository, candidate, approver=user, is_admin=True)
        return {"ok": True, "published": True, "template": template.key, "version": template.version}
    except (PermissionError, ValueError):
        return {"ok": False, "message": "Candidate is not validated or is already published."}
    except Exception:
        return {"ok": False, "message": "Candidate publication is temporarily unavailable."}


@_whitelist(allow_guest=False)
def reject_catalog_candidate(candidate_key: str | None = None) -> dict[str, Any]:
    try:
        import frappe  # type: ignore

        user = frappe.session.user
        if not _is_admin(frappe, user):
            return {"ok": False, "message": "Only an administrator can reject a candidate."}
        repository = FrappeCatalogLearningRepository(frappe)
        candidate = repository.get_candidate(str(candidate_key or ""))
        if candidate is None:
            return {"ok": False, "message": "Candidate was not found."}
        candidate.status = "REJECTED"
        repository.save_candidate(candidate)
        return {"ok": True, "rejected": True}
    except Exception:
        return {"ok": False, "message": "Candidate rejection is temporarily unavailable."}


@_whitelist(allow_guest=False)
def list_catalog_snapshots() -> dict[str, Any]:
    try:
        import frappe  # type: ignore

        if not _is_admin(frappe, frappe.session.user):
            return {"ok": False, "message": "Administrator access is required.", "snapshots": []}
        repository = FrappeCatalogLearningRepository(frappe)
        snapshots = repository.list_snapshots()
        return {
            "ok": True,
            "snapshots": [snapshot.as_dict() for snapshot in snapshots],
            "active": next((snapshot.snapshot_key for snapshot in snapshots if snapshot.status == "Published"), ""),
        }
    except Exception:
        return {"ok": False, "message": "Catalog snapshots are temporarily unavailable.", "snapshots": []}


@_whitelist(allow_guest=False)
def rollback_catalog_snapshot(snapshot_key: str | None = None) -> dict[str, Any]:
    try:
        import frappe  # type: ignore

        user = frappe.session.user
        if not _is_admin(frappe, user):
            return {"ok": False, "message": "Only an administrator can roll back a snapshot."}
        repository = FrappeCatalogLearningRepository(frappe)
        snapshot = repository.rollback_snapshot(str(snapshot_key or ""), published_by=user)
        if snapshot is None:
            return {"ok": False, "message": "Snapshot was not found."}
        return {"ok": True, "rolled_back": True, "snapshot": snapshot.as_dict()}
    except Exception:
        return {"ok": False, "message": "Snapshot rollback is temporarily unavailable."}


def _is_admin(frappe: Any, user: str) -> bool:
    return user == "Administrator" or "System Manager" in set(frappe.get_roles(user) or [])


def _installed_metadata(doctype: str, frappe: Any) -> dict[str, Any]:
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


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
