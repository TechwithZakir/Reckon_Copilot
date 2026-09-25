from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable


MAX_EXTRACTED_FIELDS = 24
MAX_VALUE_LENGTH = 240


_FIELD_CATALOG = (
    ("customer", "Customer", ("customer name", "customer", "bill to")),
    ("supplier", "Supplier", ("supplier name", "supplier", "vendor")),
    ("company", "Company", ("company", "legal entity")),
    ("invoice_number", "Invoice number", ("invoice number", "invoice no", "invoice #", "bill no", "bill number")),
    ("posting_date", "Invoice date", ("invoice date", "posting date", "bill date", "date")),
    ("due_date", "Due date", ("due date", "payment due", "due")),
    ("currency", "Currency", ("currency", "currency code")),
    ("net_total", "Net total", ("net total", "subtotal", "sub total")),
    ("total_taxes_and_charges", "Tax total", ("tax total", "tax amount", "taxes", "vat", "gst")),
    ("grand_total", "Grand total", ("grand total", "total due", "amount due", "invoice total", "total")),
)


def build_field_extraction_preview(
    preview: dict[str, Any],
    *,
    target_fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Extract only explicitly labelled values from a read-only text preview."""
    if not isinstance(preview, dict):
        return _empty_result("A readable document preview is required.")

    text = str(preview.get("text_excerpt") or "")[:1200]
    if not text:
        return _empty_result("No readable text was available for field extraction.")

    allowed = {str(field).strip() for field in (target_fields or ()) if str(field).strip()}
    extracted: list[dict[str, Any]] = []
    record: dict[str, str] = {}
    for canonical, label, aliases in _FIELD_CATALOG:
        target = _resolve_target(canonical, allowed)
        if allowed and not target:
            continue
        match = _find_label_value(text, aliases)
        if not match:
            continue
        source_label, raw_value = match
        value = _normalise_value(canonical, raw_value)
        if not value:
            continue
        fieldname = target or canonical
        extracted.append({
            "fieldname": fieldname,
            "label": label,
            "value": value[:MAX_VALUE_LENGTH],
            "confidence": "high",
            "source": f"label: {source_label}",
            "reason": "Matched an explicit label in the uploaded document text.",
        })
        record[fieldname] = value[:MAX_VALUE_LENGTH]
        if len(extracted) >= MAX_EXTRACTED_FIELDS:
            break

    warnings = []
    if allowed and not extracted:
        warnings.append("No labelled values matched fields on the selected DocType.")
    if extracted:
        warnings.append("Review extracted values before any future import step.")
    else:
        warnings.append("No fields were extracted. Add clear labels such as Invoice number, Date or Total.")
    return {
        "extraction_method": "deterministic_label_match",
        "extraction_status": "review_only",
        "extracted_fields": extracted,
        "extracted_record": record,
        "extraction_warnings": warnings,
        "write_required": False,
        "requires_approval": True,
        "model_training": False,
    }


def _resolve_target(canonical: str, allowed: set[str]) -> str | None:
    if not allowed:
        return canonical
    candidates = [canonical]
    aliases = dict((item[0], item[2]) for item in _FIELD_CATALOG).get(canonical, ())
    candidates.extend(aliases)
    normalized = {_normalize(item): item for item in allowed}
    for candidate in candidates:
        resolved = normalized.get(_normalize(candidate))
        if resolved:
            return resolved
    if canonical == "invoice_number":
        for candidate in ("bill_no", "supplier_invoice_no", "invoice_no"):
            if _normalize(candidate) in normalized:
                return normalized[_normalize(candidate)]
    return None


def _find_label_value(text: str, aliases: tuple[str, ...]) -> tuple[str, str] | None:
    labels = sorted(aliases, key=len, reverse=True)
    known_labels = sorted({alias for _, _, candidates in _FIELD_CATALOG for alias in candidates}, key=len, reverse=True)
    next_label = "|".join(re.escape(label) for label in known_labels)
    pattern = re.compile(
        rf"(?<![A-Za-z])({'|'.join(re.escape(label) for label in labels)})\s*(?:[:#-])\s*"
        rf"([^:|;]{{1,160}}?)(?=\s+(?:{next_label})\s*[:#-]|$)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    value = re.split(r"\s+(?=[A-Za-z][A-Za-z /#.-]{2,32}\s*[:#-])", match.group(2), maxsplit=1)[0]
    return match.group(1), value.strip(" \t\r\n-:")


def _normalise_value(canonical: str, value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if canonical in {"posting_date", "due_date"}:
        for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(value[:10], pattern).date().isoformat()
            except ValueError:
                continue
    if canonical in {"net_total", "total_taxes_and_charges", "grand_total"}:
        number = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value)
        if number:
            return number.group(0).replace(",", "")
    return value


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _empty_result(message: str) -> dict[str, Any]:
    return {
        "extraction_method": "deterministic_label_match",
        "extraction_status": "review_only",
        "extracted_fields": [],
        "extracted_record": {},
        "extraction_warnings": [message],
        "write_required": False,
        "requires_approval": True,
        "model_training": False,
    }
