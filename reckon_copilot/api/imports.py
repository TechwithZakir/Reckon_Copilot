from __future__ import annotations

import base64
import json
from typing import Any

from reckon_copilot.imports.preview import ImportPreviewError, build_document_preview
from reckon_copilot.permissions.boundary import FrappePermissionAdapter, PermissionDenied, authorize_context


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
