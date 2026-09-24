from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from reckon_copilot.actions.approval import validate_approval_token
from reckon_copilot.context.builders import canonical_json
from reckon_copilot.knowledge.models import stable_hash
from reckon_copilot.permissions.boundary import (
    CopilotPermissionBoundary,
    FrappePermissionAdapter,
    PermissionAdapter,
)


ACTION_TYPES = {"create", "update", "delete", "submit", "approve"}
PROTECTED_FIELDS = {
    "name",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "parent",
    "parentfield",
    "parenttype",
    "idx",
}


class ActionExecutionError(RuntimeError):
    """Raised when an approved action cannot be applied safely."""


SAME_TARGET_MESSAGE = (
    "This action belongs to the same Form and record that created the preview. "
    "Open that DocType and document, then prepare the action again. No ERP data was changed."
)


class AuditStore(Protocol):
    def find(self, plan_hash: str, user: str, site: str) -> dict[str, Any] | None:
        ...

    def start(self, record: dict[str, Any]) -> str:
        ...

    def complete(self, audit_id: str, result_name: str | None) -> None:
        ...

    def fail(self, audit_id: str, message: str) -> None:
        ...


@dataclass
class InMemoryAuditStore:
    records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def find(self, plan_hash: str, user: str, site: str) -> dict[str, Any] | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.get("plan_hash") == plan_hash
                and record.get("user") == user
                and record.get("site") == site
            ),
            None,
        )

    def start(self, record: dict[str, Any]) -> str:
        audit_id = str(record["plan_hash"])
        self.records[audit_id] = {**record, "status": "started"}
        return audit_id

    def complete(self, audit_id: str, result_name: str | None) -> None:
        self.records[audit_id].update({"status": "completed", "result_name": result_name})

    def fail(self, audit_id: str, message: str) -> None:
        self.records[audit_id].update({"status": "failed", "error": message})


class FrappeActionAuditStore:
    """Small Frappe-backed audit adapter kept behind the executor boundary."""

    doctype = "Copilot Action Audit"

    def __init__(self, frappe_module: Any):
        self.frappe = frappe_module

    def find(self, plan_hash: str, user: str, site: str) -> dict[str, Any] | None:
        rows = self.frappe.get_all(
            self.doctype,
            filters={"plan_hash": plan_hash, "user": user, "site": site},
            fields=["name", "status", "result_name"],
            order_by="creation desc",
            limit_page_length=1,
        )
        return rows[0] if rows else None

    def start(self, record: dict[str, Any]) -> str:
        doc = self.frappe.get_doc(
            {
                "doctype": self.doctype,
                **record,
                "status": "started",
            }
        )
        doc.insert(ignore_permissions=True)
        return str(doc.name)

    def complete(self, audit_id: str, result_name: str | None) -> None:
        self.frappe.db.set_value(
            self.doctype,
            audit_id,
            {"status": "completed", "result_name": result_name or ""},
            update_modified=False,
        )

    def fail(self, audit_id: str, message: str) -> None:
        self.frappe.db.set_value(
            self.doctype,
            audit_id,
            {"status": "failed", "error": str(message)[:500]},
            update_modified=False,
        )


def execute_approved_plan(
    plan: dict[str, Any],
    approval_token: str,
    *,
    frappe_module: Any,
    user: str,
    site: str,
    secret: str,
    current_context: dict[str, Any] | None = None,
    permission_adapter: PermissionAdapter | None = None,
    audit_store: AuditStore | None = None,
) -> dict[str, Any]:
    """Execute one unchanged, approved plan exactly once.

    The plan hash and approval token are checked before the native Frappe
    permission boundary is called again immediately before mutation.
    """
    normalized = _validate_plan(plan)
    assert_same_form_target(normalized, current_context)
    plan_hash = normalized["plan_hash"]
    expected_hash = stable_hash(canonical_json({key: value for key, value in normalized.items() if key != "plan_hash"}))
    if expected_hash != plan_hash:
        raise ActionExecutionError("The approved plan changed and must be reviewed again.")

    validate_approval_token(
        approval_token,
        plan_hash=plan_hash,
        user=user,
        site=site,
        secret=secret,
    )
    if normalized.get("user") and normalized["user"] != user:
        raise ActionExecutionError("The approved plan belongs to a different user.")

    target = normalized["target"]
    action = normalized["action"]
    permission_context = {
        "page_type": "Form",
        "doctype": target["doctype"],
        "document_name": target.get("document_name"),
    }
    boundary = CopilotPermissionBoundary(permission_adapter or FrappePermissionAdapter(frappe_module))
    boundary.authorize_action(permission_context, action, user=user)

    store = audit_store or FrappeActionAuditStore(frappe_module)
    existing = store.find(plan_hash, user, site)
    if existing and existing.get("status") == "completed":
        return {
            "ok": True,
            "execution": "completed",
            "idempotent": True,
            "audit_id": existing.get("name"),
            "result_name": existing.get("result_name") or None,
        }
    if existing and existing.get("status") == "started":
        raise ActionExecutionError("This approved action is already in progress.")

    audit_id = store.start(
        {
            "plan_hash": plan_hash,
            "action": action,
            "target_doctype": target["doctype"],
            "target_name": target.get("document_name") or "",
            "user": user,
            "site": site,
            "plan_payload": json.dumps(normalized, sort_keys=True, ensure_ascii=True),
        }
    )
    try:
        result_name = _mutate(frappe_module, normalized)
        store.complete(audit_id, result_name)
        return {
            "ok": True,
            "execution": "completed",
            "idempotent": False,
            "audit_id": audit_id,
            "result_name": result_name,
        }
    except Exception as error:
        _rollback(frappe_module)
        store.fail(audit_id, str(error))
        if isinstance(error, ActionExecutionError):
            raise
        raise ActionExecutionError("Action failed; no changes were committed.") from error


def assert_same_form_target(plan: dict[str, Any], current_context: dict[str, Any] | None) -> None:
    """Require execution from the exact Form target used by the preview."""
    if not isinstance(current_context, dict) or current_context.get("page_type") != "Form":
        raise ActionExecutionError(SAME_TARGET_MESSAGE)

    target = plan.get("target") if isinstance(plan.get("target"), dict) else {}
    expected_doctype = str(target.get("doctype") or "").strip()
    current_doctype = str(current_context.get("doctype") or "").strip()
    if not expected_doctype or expected_doctype != current_doctype:
        raise ActionExecutionError(SAME_TARGET_MESSAGE)

    expected_name = str(target.get("document_name") or "").strip()
    current_name = str(current_context.get("document_name") or "").strip()
    if expected_name and expected_name != current_name:
        raise ActionExecutionError(SAME_TARGET_MESSAGE)


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("version") != "v1":
        raise ActionExecutionError("A valid approved plan is required.")
    action = str(plan.get("action") or "").strip().lower()
    target = plan.get("target")
    values = plan.get("values")
    if action not in ACTION_TYPES or not isinstance(target, dict) or not isinstance(values, dict):
        raise ActionExecutionError("The approved plan is incomplete.")
    doctype = str(target.get("doctype") or "").strip()
    if not doctype or any(char in doctype for char in "\r\n"):
        raise ActionExecutionError("The approved plan has no valid target DocType.")
    plan_hash = str(plan.get("plan_hash") or "").strip()
    if len(plan_hash) != 64:
        raise ActionExecutionError("The approved plan has an invalid hash.")
    clean = dict(plan)
    clean["action"] = action
    clean["target"] = {"doctype": doctype, "document_name": target.get("document_name")}
    clean["values"] = values
    return clean


def _mutate(frappe_module: Any, plan: dict[str, Any]) -> str | None:
    action = plan["action"]
    target = plan["target"]
    doctype = target["doctype"]
    document_name = target.get("document_name")
    values = plan["values"]

    if action == "create":
        if not values:
            raise ActionExecutionError("Add the fields to create before executing this plan.")
        doc = frappe_module.new_doc(doctype)
        _apply_values(doc, values)
        doc.insert(ignore_permissions=False)
        return str(getattr(doc, "name", "") or "") or None

    doc = frappe_module.get_doc(doctype, document_name)
    if action == "update":
        if not values:
            raise ActionExecutionError("Add the fields to update before executing this plan.")
        _apply_values(doc, values)
        doc.save(ignore_permissions=False)
    elif action == "delete":
        doc.delete(ignore_permissions=False)
    elif action == "submit":
        doc.submit()
    elif action == "approve":
        _apply_workflow(frappe_module, doc, str(plan.get("workflow_action") or "Approve"))
    return str(getattr(doc, "name", "") or document_name or "") or None


def _apply_values(doc: Any, values: dict[str, Any]) -> None:
    meta = getattr(doc, "meta", None)
    fields = {str(getattr(field, "fieldname", "")) for field in getattr(meta, "fields", [])}
    unknown = [key for key in values if str(key) in PROTECTED_FIELDS or (fields and str(key) not in fields)]
    if unknown:
        raise ActionExecutionError(f"The approved plan contains unsupported fields: {', '.join(map(str, unknown[:5]))}.")
    for key, value in values.items():
        setter = getattr(doc, "set", None)
        if callable(setter):
            setter(str(key), value)
        else:
            setattr(doc, str(key), value)


def _apply_workflow(frappe_module: Any, doc: Any, action: str) -> None:
    if not action or len(action) > 80:
        raise ActionExecutionError("A valid workflow action is required.")
    try:
        from frappe.model.workflow import apply_workflow  # type: ignore
    except Exception as error:
        raise ActionExecutionError("Workflow approval is not available on this site.") from error
    apply_workflow(doc, action)


def _rollback(frappe_module: Any) -> None:
    rollback = getattr(getattr(frappe_module, "db", None), "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception:
            pass
