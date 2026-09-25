from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from reckon_copilot.context.builders import canonical_json
from reckon_copilot.imports.extraction import sanitize_extracted_record
from reckon_copilot.knowledge.models import stable_hash


MAX_PLAN_ROWS = 100
MAX_SAMPLE_ROWS = 5
MAX_ERRORS = 20
MAX_WARNINGS = 20
LAYOUT_FIELD_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}
SYSTEM_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "idx", "docstatus"}


def build_import_plan(
    preview: dict[str, Any],
    target_doctype: str,
    target_fields: list[dict[str, Any]],
    *,
    field_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, write-free mapping and validation plan."""
    if not isinstance(preview, dict):
        raise ValueError("A valid document preview is required.")
    if preview.get("structured") is False:
        raise ValueError("This document contains readable text, but structured import mapping is not available yet.")
    doctype = str(target_doctype or "").strip()
    if not doctype:
        raise ValueError("Choose a target DocType before preparing an import plan.")

    records = [item for item in preview.get("records", [])[:MAX_PLAN_ROWS] if isinstance(item, dict)]
    fields = _usable_fields(target_fields)
    if not fields:
        raise ValueError("The selected DocType has no importable fields.")
    source_fields = _source_fields(preview, records)
    mappings, duplicate_sources = _map_fields(source_fields, fields, field_map or {})
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    if duplicate_sources:
        warnings.append(f"Multiple uploaded fields map to {duplicate_sources[0]}; only the first match is used.")

    sample_rows = []
    for row_number, record in enumerate(records, start=1):
        mapped: dict[str, Any] = {}
        row_errors = []
        for source, target in mappings.items():
            if source not in record:
                continue
            value = _compact_value(record[source])
            field = next(item for item in fields if item["fieldname"] == target)
            problem = _validate_value(value, field)
            if problem:
                row_errors.append(f"{target}: {problem}")
            else:
                mapped[target] = value
        missing = [
            field["fieldname"]
            for field in fields
            if field.get("reqd") and field["fieldname"] not in mapped
        ]
        if missing:
            row_errors.append(f"Missing required fields: {', '.join(missing[:5])}")
        if row_errors and len(errors) < MAX_ERRORS:
            errors.append({"row": row_number, "messages": row_errors[:5]})
        if len(sample_rows) < MAX_SAMPLE_ROWS:
            sample_rows.append({"row": row_number, "values": mapped})

    unmapped = [field for field in source_fields if field not in mappings]
    if unmapped:
        warnings.append(f"Ignored uploaded fields: {', '.join(unmapped[:8])}.")
    if len(records) >= MAX_PLAN_ROWS:
        warnings.append(f"Plan limited to the first {MAX_PLAN_ROWS} records.")
    if not records:
        warnings.append("The preview contains no structured records to map.")
    warnings.append("Dry run only: no ERP document was created or changed.")

    plan = {
        "version": "v1",
        "source_preview_id": str(preview.get("preview_id") or ""),
        "source_file_name": str(preview.get("file_name") or "")[:180],
        "target_doctype": doctype,
        "source_fields": source_fields,
        "mappings": [{"source": source, "target": target} for source, target in mappings.items()],
        "unmapped_fields": unmapped[:40],
        "row_count": len(records),
        "sample_rows": sample_rows,
        "errors": errors,
        "error_count": sum(len(item["messages"]) for item in errors),
        "warnings": warnings[:MAX_WARNINGS],
        "write_required": True,
        "requires_approval": True,
        "ready_for_approval": not errors and bool(records) and bool(mappings),
        "execution": "preview_only",
        "model_training": False,
    }
    plan["plan_hash"] = stable_hash(canonical_json(plan))
    return plan


def build_extracted_import_plan(
    preview: dict[str, Any],
    target_doctype: str,
    target_fields: list[dict[str, Any]],
    reviewed_record: dict[str, Any],
) -> dict[str, Any]:
    """Validate reviewed PDF/DOCX candidates without enabling execution."""
    if not isinstance(preview, dict) or preview.get("structured") is not False:
        raise ValueError("A PDF or DOCX text preview is required for extracted field review.")
    allowed_fields = [
        str(field.get("fieldname") or "").strip()
        for field in target_fields
        if isinstance(field, dict)
    ]
    record = sanitize_extracted_record(reviewed_record, allowed_fields=allowed_fields)
    synthetic_preview = {
        "version": "v1-extracted",
        "preview_id": str(preview.get("preview_id") or ""),
        "file_name": str(preview.get("file_name") or "")[:180],
        "format": preview.get("format"),
        "structured": True,
        "fields": list(record),
        "records": (record,),
    }
    plan = build_import_plan(
        synthetic_preview,
        target_doctype,
        target_fields,
    )
    plan["version"] = "v1-extracted-review"
    plan["source_format"] = str(preview.get("format") or "")
    plan["extraction_method"] = str(preview.get("extraction_method") or "deterministic_label_match")
    plan["extraction_status"] = "review_only"
    plan["reviewed_record"] = record
    plan["ready_for_approval"] = False
    plan["execution"] = "review_only"
    plan["warnings"] = [
        *plan.get("warnings", []),
        "PDF/DOCX extracted values are review-only; approval and execution are not available yet.",
    ][:MAX_WARNINGS]
    plan["plan_hash"] = stable_hash(canonical_json(plan))
    return plan


def _usable_fields(target_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = []
    for raw in target_fields or []:
        if not isinstance(raw, dict):
            continue
        fieldname = str(raw.get("fieldname") or "").strip()
        fieldtype = str(raw.get("fieldtype") or "Data").strip()
        if not fieldname or fieldname in SYSTEM_FIELDS or fieldtype in LAYOUT_FIELD_TYPES:
            continue
        fields.append({
            "fieldname": fieldname,
            "label": str(raw.get("label") or fieldname)[:120],
            "fieldtype": fieldtype,
            "reqd": bool(raw.get("reqd")),
            "options": str(raw.get("options") or "")[:500],
        })
    return fields


def _source_fields(preview: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    names = []
    seen = set()
    for value in preview.get("fields", []) or []:
        name = str(value or "").strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    for record in records:
        for value in record:
            name = str(value or "").strip()
            if name and name not in seen:
                names.append(name)
                seen.add(name)
    return names[:40]


def _map_fields(source_fields: list[str], target_fields: list[dict[str, Any]], explicit: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    by_name = {field["fieldname"]: field for field in target_fields}
    by_normalized = {}
    for field in target_fields:
        for candidate in (field["fieldname"], field["label"]):
            by_normalized.setdefault(_normalize(candidate), field["fieldname"])
    mappings = {}
    used_targets = set()
    duplicates = []
    for source in source_fields:
        requested = str(explicit.get(source) or "").strip()
        target = requested if requested in by_name else by_normalized.get(_normalize(source))
        if target and target in used_targets:
            duplicates.append(target)
            continue
        if target:
            mappings[source] = target
            used_targets.add(target)
    return mappings, duplicates


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _compact_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return str(value)[:240]
    if value is None:
        return ""
    return str(value)[:240]


def _validate_value(value: Any, field: dict[str, Any]) -> str | None:
    if value in (None, ""):
        return None
    fieldtype = field.get("fieldtype")
    text = str(value).strip()
    if fieldtype == "Int":
        try:
            if int(text) != float(text):
                return "must be a whole number"
        except (TypeError, ValueError):
            return "must be a whole number"
    elif fieldtype in {"Float", "Currency", "Percent"}:
        try:
            Decimal(text.replace(",", ""))
        except (InvalidOperation, ValueError):
            return "must be a number"
    elif fieldtype == "Check" and text.lower() not in {"0", "1", "true", "false", "yes", "no"}:
        return "must be yes/no or true/false"
    elif fieldtype == "Date":
        try:
            date.fromisoformat(text[:10])
        except ValueError:
            return "must be an ISO date such as 2026-09-25"
    elif fieldtype == "Datetime":
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return "must be an ISO date and time"
    elif fieldtype == "Select":
        options = {item.strip() for item in str(field.get("options") or "").splitlines() if item.strip()}
        if options and text not in options:
            return f"must be one of: {', '.join(sorted(options)[:6])}"
    return None
