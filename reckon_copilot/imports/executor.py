from __future__ import annotations

import hmac
import json
import time
from typing import Any

from reckon_copilot.actions.approval import hash_approval_token, validate_approval_token
from reckon_copilot.actions.executor import AuditStore, FrappeActionAuditStore
from reckon_copilot.context.builders import canonical_json
from reckon_copilot.imports.extraction import build_field_extraction_preview
from reckon_copilot.imports.mapping import build_extracted_import_plan, build_import_plan
from reckon_copilot.imports.preview import build_document_preview
from reckon_copilot.knowledge.models import stable_hash
from reckon_copilot.permissions.boundary import CopilotPermissionBoundary, FrappePermissionAdapter, PermissionAdapter


MAX_IMPORT_ROWS = 100
PROTECTED_FIELDS = {
    "name", "owner", "creation", "modified", "modified_by", "docstatus",
    "parent", "parentfield", "parenttype", "idx",
}


class ImportExecutionError(RuntimeError):
    """Raised when an approved document import cannot be applied safely."""


def record_import_approval(
    plan: dict[str, Any],
    approval_token: str,
    *,
    user: str,
    site: str,
    audit_store: AuditStore,
) -> str:
    normalized = _validate_import_plan(plan)
    plan_hash = normalized["plan_hash"]
    payload = validate_approval_token(approval_token, plan_hash=plan_hash, user=user, site=site)
    existing = audit_store.find(plan_hash, user, site)
    if existing and existing.get("status") == "completed":
        raise ImportExecutionError("This import has already been completed.")
    return audit_store.approve(
        {
            "plan_hash": plan_hash,
            "action": "import",
            "target_doctype": normalized["target_doctype"],
            "target_name": normalized["source_preview_id"],
            "user": user,
            "site": site,
            "approval_token_hash": hash_approval_token(approval_token),
            "approval_expires_at": int(payload["expires_at"]),
            "approved_by": user,
            "plan_payload": json.dumps(normalized, sort_keys=True, ensure_ascii=True),
        }
    )


def record_extracted_import_approval(
    plan: dict[str, Any],
    approval_token: str,
    *,
    user: str,
    site: str,
    audit_store: AuditStore,
) -> str:
    normalized = _validate_extracted_import_plan(plan)
    payload = validate_approval_token(approval_token, plan_hash=normalized["plan_hash"], user=user, site=site)
    existing = audit_store.find(normalized["plan_hash"], user, site)
    if existing and existing.get("status") == "completed":
        raise ImportExecutionError("This import has already been completed.")
    return audit_store.approve(
        {
            "plan_hash": normalized["plan_hash"],
            "action": "import",
            "target_doctype": normalized["target_doctype"],
            "target_name": normalized["source_preview_id"],
            "user": user,
            "site": site,
            "approval_token_hash": hash_approval_token(approval_token),
            "approval_expires_at": int(payload["expires_at"]),
            "approved_by": user,
            "plan_payload": json.dumps(normalized, sort_keys=True, ensure_ascii=True),
        }
    )


def execute_import_plan(
    plan: dict[str, Any],
    approval_token: str,
    *,
    file_name: str,
    content: bytes,
    mime_type: str,
    frappe_module: Any,
    user: str,
    site: str,
    permission_adapter: PermissionAdapter | None = None,
    audit_store: AuditStore | None = None,
) -> dict[str, Any]:
    """Revalidate and execute one approved import plan exactly once."""
    normalized = _validate_import_plan(plan)
    plan_hash = normalized["plan_hash"]
    store = audit_store or FrappeActionAuditStore(frappe_module)
    existing = store.find(plan_hash, user, site)
    if not existing or existing.get("status") not in {"approved", "started", "completed"}:
        raise ImportExecutionError("Approve this import before executing it.")
    validate_approval_token(approval_token, plan_hash=plan_hash, user=user, site=site)
    if not hmac.compare_digest(hash_approval_token(approval_token), str(existing.get("approval_token_hash") or "")):
        raise ImportExecutionError("This approval token is not valid for the selected import.")
    if int(existing.get("approval_expires_at") or 0) < int(time.time()):
        raise ImportExecutionError("Approval expired. Prepare the import again.")

    permission_context = {
        "page_type": "Form",
        "doctype": normalized["target_doctype"],
        "document_name": f"new-import-{normalized['source_preview_id'][:16]}",
    }
    boundary = CopilotPermissionBoundary(permission_adapter or FrappePermissionAdapter(frappe_module))
    boundary.authorize_action(permission_context, "create", user=user)

    if existing.get("status") == "completed":
        return {
            "ok": True,
            "execution": "completed",
            "idempotent": True,
            "audit_id": existing.get("name"),
            "result_name": existing.get("result_name") or None,
        }
    if existing.get("status") == "started":
        raise ImportExecutionError("This approved import is already in progress.")

    audit_id = store.start(
        {
            "plan_hash": plan_hash,
            "action": "import",
            "target_doctype": normalized["target_doctype"],
            "target_name": normalized["source_preview_id"],
            "user": user,
            "site": site,
            "plan_payload": json.dumps(normalized, sort_keys=True, ensure_ascii=True),
        }
    )
    try:
        preview = build_document_preview(file_name, content, mime_type=mime_type)
        rebuilt = build_import_plan(
            preview,
            normalized["target_doctype"],
            _target_schema(frappe_module, normalized["target_doctype"]),
            field_map={item["source"]: item["target"] for item in normalized["mappings"]},
        )
        if rebuilt["plan_hash"] != plan_hash:
            raise ImportExecutionError("The attachment or target fields changed; prepare the import again.")
        if not rebuilt["ready_for_approval"]:
            raise ImportExecutionError("The import is no longer valid after revalidation.")
        names = _insert_rows(frappe_module, normalized["target_doctype"], rebuilt, preview["records"])
        result_name = _result_summary(names)
        store.complete(audit_id, result_name)
        return {
            "ok": True,
            "execution": "completed",
            "idempotent": False,
            "audit_id": audit_id,
            "result_name": result_name,
            "created_count": len(names),
        }
    except Exception as error:
        _rollback(frappe_module)
        store.fail(audit_id, str(error))
        if isinstance(error, ImportExecutionError):
            raise
        raise ImportExecutionError("Import failed; no changes were committed.") from error


def execute_extracted_import_plan(
    plan: dict[str, Any],
    approval_token: str,
    *,
    file_name: str,
    content: bytes,
    mime_type: str,
    frappe_module: Any,
    user: str,
    site: str,
    permission_adapter: PermissionAdapter | None = None,
    audit_store: AuditStore | None = None,
) -> dict[str, Any]:
    """Revalidate a reviewed PDF/DOCX plan, then execute it once after approval."""
    normalized = _validate_extracted_import_plan(plan)
    plan_hash = normalized["plan_hash"]
    store = audit_store or FrappeActionAuditStore(frappe_module)
    existing = store.find(plan_hash, user, site)
    if not existing or existing.get("status") not in {"approved", "started", "completed"}:
        raise ImportExecutionError("Confirm this document import before creating it.")
    validate_approval_token(approval_token, plan_hash=plan_hash, user=user, site=site)
    if not hmac.compare_digest(hash_approval_token(approval_token), str(existing.get("approval_token_hash") or "")):
        raise ImportExecutionError("This approval token is not valid for the selected document import.")
    if int(existing.get("approval_expires_at") or 0) < int(time.time()):
        raise ImportExecutionError("Approval expired. Prepare the document import again.")

    permission_context = {
        "page_type": "Form",
        "doctype": normalized["target_doctype"],
        "document_name": f"new-import-{normalized['source_preview_id'][:16]}",
    }
    boundary = CopilotPermissionBoundary(permission_adapter or FrappePermissionAdapter(frappe_module))
    boundary.authorize_action(permission_context, "create", user=user)

    if existing.get("status") == "completed":
        return {
            "ok": True,
            "execution": "completed",
            "idempotent": True,
            "audit_id": existing.get("name"),
            "result_name": existing.get("result_name") or None,
        }
    if existing.get("status") == "started":
        raise ImportExecutionError("This approved document import is already in progress.")

    audit_id = store.start(
        {
            "plan_hash": plan_hash,
            "action": "import",
            "target_doctype": normalized["target_doctype"],
            "target_name": normalized["source_preview_id"],
            "user": user,
            "site": site,
            "plan_payload": json.dumps(normalized, sort_keys=True, ensure_ascii=True),
        }
    )
    try:
        preview = build_document_preview(file_name, content, mime_type=mime_type)
        if preview.get("format") != normalized["source_format"] or preview.get("preview_id") != normalized["source_preview_id"]:
            raise ImportExecutionError("The attachment changed; prepare the document import again.")
        preview.update(build_field_extraction_preview(preview))
        rebuilt = build_extracted_import_plan(
            preview,
            normalized["target_doctype"],
            _target_schema(frappe_module, normalized["target_doctype"]),
            normalized["reviewed_record"],
        )
        if rebuilt["plan_hash"] != plan_hash or not rebuilt["ready_for_approval"]:
            raise ImportExecutionError("The attachment, target fields or reviewed values changed; prepare the document import again.")
        names = _insert_rows(frappe_module, normalized["target_doctype"], rebuilt, [normalized["reviewed_record"]])
        result_name = _result_summary(names)
        store.complete(audit_id, result_name)
        return {
            "ok": True,
            "execution": "completed",
            "idempotent": False,
            "audit_id": audit_id,
            "result_name": result_name,
            "created_count": len(names),
        }
    except Exception as error:
        _rollback(frappe_module)
        store.fail(audit_id, str(error))
        if isinstance(error, ImportExecutionError):
            raise
        raise ImportExecutionError("Document import failed; no changes were committed.") from error


def _validate_import_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("version") != "v1":
        raise ImportExecutionError("A valid import plan is required.")
    if not plan.get("ready_for_approval"):
        raise ImportExecutionError("Resolve the import validation errors before approval.")
    if plan.get("execution") != "preview_only" or plan.get("model_training"):
        raise ImportExecutionError("The import plan is not a valid guarded plan.")
    if not isinstance(plan.get("mappings"), list) or not plan["mappings"]:
        raise ImportExecutionError("The import plan has no field mappings.")
    if int(plan.get("row_count") or 0) < 1 or int(plan.get("row_count") or 0) > MAX_IMPORT_ROWS:
        raise ImportExecutionError("The import row count is outside the safe limit.")
    target = str(plan.get("target_doctype") or "").strip()
    source_id = str(plan.get("source_preview_id") or "").strip()
    plan_hash = str(plan.get("plan_hash") or "").strip()
    if not target or not source_id or len(plan_hash) != 64:
        raise ImportExecutionError("The import plan is incomplete.")
    expected = stable_hash(canonical_json({key: value for key, value in plan.items() if key != "plan_hash"}))
    if expected != plan_hash:
        raise ImportExecutionError("The approved import plan changed and must be reviewed again.")
    return dict(plan)


def _validate_extracted_import_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("version") != "v1-extracted-review":
        raise ImportExecutionError("A valid reviewed document import plan is required.")
    if not plan.get("ready_for_approval") or plan.get("execution") != "confirmation_required":
        raise ImportExecutionError("Resolve the reviewed document validation errors before confirmation.")
    if plan.get("model_training") or plan.get("source_format") not in {"pdf", "docx"}:
        raise ImportExecutionError("The reviewed document import format is not guarded.")
    if not isinstance(plan.get("mappings"), list) or not plan["mappings"]:
        raise ImportExecutionError("The reviewed document import has no field mappings.")
    if int(plan.get("row_count") or 0) != 1 or not isinstance(plan.get("reviewed_record"), dict):
        raise ImportExecutionError("The reviewed document import must contain one bounded record.")
    target = str(plan.get("target_doctype") or "").strip()
    source_id = str(plan.get("source_preview_id") or "").strip()
    source_format = str(plan.get("source_format") or "").strip()
    plan_hash = str(plan.get("plan_hash") or "").strip()
    if not target or not source_id or source_format not in {"pdf", "docx"} or len(plan_hash) != 64:
        raise ImportExecutionError("The reviewed document import plan is incomplete.")
    expected = stable_hash(canonical_json({key: value for key, value in plan.items() if key != "plan_hash"}))
    if expected != plan_hash:
        raise ImportExecutionError("The reviewed document import plan changed and must be reviewed again.")
    return dict(plan)


def _target_schema(frappe_module: Any, doctype: str) -> list[dict[str, Any]]:
    try:
        meta = frappe_module.get_meta(doctype)
    except Exception as error:
        raise ImportExecutionError("The target DocType is no longer available.") from error
    fields = []
    for field in getattr(meta, "fields", []) or []:
        fields.append({
            "fieldname": getattr(field, "fieldname", ""),
            "label": getattr(field, "label", ""),
            "fieldtype": getattr(field, "fieldtype", "Data"),
            "reqd": bool(getattr(field, "reqd", False)),
            "options": getattr(field, "options", ""),
        })
    return fields


def _insert_rows(frappe_module: Any, doctype: str, plan: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    mappings = {item["source"]: item["target"] for item in plan["mappings"]}
    names = []
    for record in records[:MAX_IMPORT_ROWS]:
        values = {
            target: str(record[source])[:240]
            for source, target in mappings.items()
            if source in record and record[source] not in (None, "")
        }
        if any(str(key) in PROTECTED_FIELDS for key in values):
            raise ImportExecutionError("The import contains a protected field.")
        doc = frappe_module.new_doc(doctype)
        meta_fields = {str(getattr(field, "fieldname", "")) for field in getattr(getattr(doc, "meta", None), "fields", [])}
        unknown = [key for key in values if meta_fields and key not in meta_fields]
        if unknown:
            raise ImportExecutionError(f"The import contains unsupported fields: {', '.join(unknown[:5])}.")
        for key, value in values.items():
            setter = getattr(doc, "set", None)
            if callable(setter):
                setter(key, value)
            else:
                setattr(doc, key, value)
        doc.insert(ignore_permissions=False)
        names.append(str(getattr(doc, "name", "") or ""))
    return names


def _result_summary(names: list[str]) -> str:
    shown = [name for name in names if name][:5]
    suffix = "..." if len(names) > len(shown) else ""
    return f"Imported {len(names)} record(s)" + (f": {', '.join(shown)}{suffix}" if shown else "")


def _rollback(frappe_module: Any) -> None:
    rollback = getattr(getattr(frappe_module, "db", None), "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception:
            pass
