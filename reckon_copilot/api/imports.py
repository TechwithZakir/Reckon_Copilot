from __future__ import annotations

import base64
import json
from typing import Any

from reckon_copilot.actions.approval import issue_approval_token
from reckon_copilot.actions.executor import FrappeActionAuditStore
from reckon_copilot.imports.mapping import build_extracted_import_plan, build_import_plan
from reckon_copilot.imports.executor import (
    ImportExecutionError,
    execute_extracted_import_plan,
    execute_import_plan,
    record_extracted_import_approval,
    record_import_approval,
)
from reckon_copilot.imports.extraction import build_field_extraction_preview, sanitize_extracted_record
from reckon_copilot.imports.preview import ImportPreviewError, build_document_preview
from reckon_copilot.permissions.boundary import CopilotPermissionBoundary, FrappePermissionAdapter, PermissionDenied, authorize_context


def _whitelist(**kwargs: Any):
    try:
        import frappe  # type: ignore
    except Exception:
        return lambda fn: fn
    return frappe.whitelist(**kwargs)


@_whitelist(allow_guest=False)
def preview_document(
    file_name: str = "",
    content: str = "",
    mime_type: str = "",
    context: Any = None,
    target_doctype: str = "",
) -> dict[str, Any]:
    """Preview an upload without inserting or changing an ERP document."""
    try:
        import frappe  # type: ignore

        page_context = json.loads(context) if isinstance(context, str) else context
        if not isinstance(page_context, dict):
            return _safe_error("Open the target ERP page before previewing a document.")
        authorize_context(
            page_context,
            user=frappe.session.user,
            adapter=FrappePermissionAdapter(frappe),
        )
        raw = base64.b64decode(str(content or ""), validate=True)
        fields = _target_fields(frappe, target_doctype)
        preview = build_document_preview(
            file_name,
            raw,
            mime_type=mime_type,
            target_fields=fields,
        )
        if preview.get("structured") is False:
            preview.update(build_field_extraction_preview(preview, target_fields=fields))
        preview["target_doctype"] = str(target_doctype or "").strip() or None
        preview["suggested_doctypes"] = _suggested_doctypes(frappe, file_name)
        return {"ok": True, "preview": preview}
    except ImportPreviewError as error:
        return _safe_error(str(error))
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (ValueError, TypeError) as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("The document preview could not be prepared. No ERP data was changed.")


@_whitelist(allow_guest=False)
def prepare_document_import_plan(
    file_name: str = "",
    content: str = "",
    mime_type: str = "",
    context: Any = None,
    target_doctype: str = "",
    field_map: Any = None,
) -> dict[str, Any]:
    """Prepare a validated dry-run plan without inserting ERP documents."""
    try:
        import frappe  # type: ignore

        page_context = json.loads(context) if isinstance(context, str) else context
        if not isinstance(page_context, dict):
            return _safe_error("Open the target ERP page before preparing an import plan.")
        target = str(target_doctype or "").strip()
        adapter = FrappePermissionAdapter(frappe)
        CopilotPermissionBoundary(adapter).authorize_import_preview(
            page_context,
            target,
            user=frappe.session.user,
        )
        raw = base64.b64decode(str(content or ""), validate=True)
        preview = build_document_preview(file_name, raw, mime_type=mime_type)
        if preview.get("structured") is False:
            return _safe_error("This file can be previewed as text, but structured import mapping is not available yet.")
        plan = build_import_plan(
            preview,
            target,
            _target_schema(frappe, target),
            field_map=_field_map(field_map),
        )
        return {"ok": True, "plan": plan}
    except ImportPreviewError as error:
        return _safe_error(str(error))
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (ValueError, TypeError) as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("The import plan could not be prepared. No ERP data was changed.")


@_whitelist(allow_guest=False)
def prepare_extracted_document_import_plan(
    file_name: str = "",
    content: str = "",
    mime_type: str = "",
    context: Any = None,
    target_doctype: str = "",
    reviewed_record: Any = None,
) -> dict[str, Any]:
    """Prepare a review-only plan from corrected PDF/DOCX field candidates."""
    try:
        import frappe  # type: ignore

        page_context = json.loads(context) if isinstance(context, str) else context
        if not isinstance(page_context, dict):
            return _safe_error("Open the target ERP page before preparing an extracted-field plan.")
        target = str(target_doctype or "").strip()
        adapter = FrappePermissionAdapter(frappe)
        CopilotPermissionBoundary(adapter).authorize_import_preview(
            page_context,
            target,
            user=frappe.session.user,
        )
        raw = base64.b64decode(str(content or ""), validate=True)
        preview = build_document_preview(file_name, raw, mime_type=mime_type)
        if preview.get("structured") is not False or preview.get("format") not in {"pdf", "docx"}:
            return _safe_error("Extracted-field review is available only for PDF and DOCX previews.")
        fields = _target_schema(frappe, target)
        reviewed = sanitize_extracted_record(
            reviewed_record,
            allowed_fields={str(field.get("fieldname") or "") for field in fields},
        )
        plan = build_extracted_import_plan(preview, target, fields, reviewed)
        return {"ok": True, "plan": plan}
    except ImportPreviewError as error:
        return _safe_error(str(error))
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (ValueError, TypeError) as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("The extracted-field plan could not be prepared. No ERP data was changed.")


@_whitelist(allow_guest=False)
def approve_document_import_plan(plan: Any = None) -> dict[str, Any]:
    """Approve one unchanged import plan without executing it."""
    try:
        import frappe  # type: ignore

        payload = json.loads(plan) if isinstance(plan, str) else plan
        if not isinstance(payload, dict) or not payload.get("plan_hash"):
            return _safe_error("A valid import plan is required.")
        is_standard = payload.get("version") == "v1" and payload.get("execution") == "preview_only"
        is_extracted = payload.get("version") == "v1-extracted-review" and payload.get("execution") == "confirmation_required"
        if (not is_standard and not is_extracted) or not payload.get("ready_for_approval"):
            return _safe_error("This plan is review-only and cannot be approved or executed yet.")
        target = str(payload.get("target_doctype") or "").strip()
        source_id = str(payload.get("source_preview_id") or "").strip()
        permission_context = {
            "page_type": "Form",
            "doctype": target,
            "document_name": f"new-import-{source_id[:16]}",
        }
        CopilotPermissionBoundary(FrappePermissionAdapter(frappe)).authorize_action(
            permission_context,
            "create",
            user=frappe.session.user,
        )
        token = issue_approval_token(
            payload,
            user=frappe.session.user,
            site=getattr(frappe.local, "site", "default"),
        )
        approval_recorder = record_extracted_import_approval if is_extracted else record_import_approval
        approval_recorder(
            payload,
            token,
            user=frappe.session.user,
            site=getattr(frappe.local, "site", "default"),
            audit_store=FrappeActionAuditStore(frappe),
        )
        return {"ok": True, "approved": True, "execution": "ready_to_execute", "approval_token": token}
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (ImportExecutionError, TypeError, ValueError) as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("Approval could not be recorded. No ERP data was changed.")


@_whitelist(allow_guest=False)
def execute_document_import(
    plan: Any = None,
    approval_token: str = "",
    file_name: str = "",
    content: str = "",
    mime_type: str = "",
) -> dict[str, Any]:
    """Execute an approved import after re-reading and revalidating the file."""
    try:
        import frappe  # type: ignore

        payload = json.loads(plan) if isinstance(plan, str) else plan
        raw = base64.b64decode(str(content or ""), validate=True)
        if isinstance(payload, dict) and payload.get("version") == "v1-extracted-review":
            return execute_extracted_import_plan(
                payload,
                str(approval_token or ""),
                file_name=file_name,
                content=raw,
                mime_type=mime_type,
                frappe_module=frappe,
                user=frappe.session.user,
                site=getattr(frappe.local, "site", "default"),
            )
        return execute_import_plan(
            payload,
            str(approval_token or ""),
            file_name=file_name,
            content=raw,
            mime_type=mime_type,
            frappe_module=frappe,
            user=frappe.session.user,
            site=getattr(frappe.local, "site", "default"),
        )
    except PermissionDenied as error:
        return _safe_error(str(error), access_denied=True)
    except (ImportExecutionError, ImportPreviewError, TypeError, ValueError) as error:
        return _safe_error(str(error))
    except Exception:
        return _safe_error("Import could not be completed. No changes were committed.")


def _target_fields(frappe: Any, doctype: str) -> set[str]:
    name = str(doctype or "").strip()
    if not name:
        return set()
    try:
        meta = frappe.get_meta(name)
    except Exception:
        return set()
    return {
        str(field.fieldname)
        for field in getattr(meta, "fields", []) or []
        if getattr(field, "fieldname", None)
        and str(getattr(field, "fieldtype", "")) not in {"Section Break", "Column Break", "Tab Break", "HTML"}
    }


def _target_schema(frappe: Any, doctype: str) -> list[dict[str, Any]]:
    try:
        meta = frappe.get_meta(str(doctype or "").strip())
    except Exception:
        return []
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


def _field_map(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}
    return {str(key)[:120]: str(item)[:120] for key, item in list(value.items())[:40]}


def _suggested_doctypes(frappe: Any, file_name: str) -> list[str]:
    value = str(file_name or "").lower()
    candidates = []
    if "purchase" in value and "invoice" in value:
        candidates.append("Purchase Invoice")
    elif "sales" in value and "invoice" in value:
        candidates.append("Sales Invoice")
    elif "invoice" in value:
        candidates.extend(["Purchase Invoice", "Sales Invoice"])
    elif "purchase" in value or "supplier" in value:
        candidates.append("Purchase Order")
    elif "sales" in value or "customer" in value:
        candidates.append("Sales Order")
    return [candidate for candidate in candidates if _doctype_exists(frappe, candidate)][:3]


def _doctype_exists(frappe: Any, doctype: str) -> bool:
    try:
        return bool(frappe.db.exists("DocType", doctype))
    except Exception:
        return False


def _safe_error(message: str, *, access_denied: bool = False) -> dict[str, Any]:
    result = {"ok": False, "message": str(message)[:500], "write_required": False}
    if access_denied:
        result["access_denied"] = True
    return result
