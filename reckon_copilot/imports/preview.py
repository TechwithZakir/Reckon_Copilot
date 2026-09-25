from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
from typing import Any


MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 100
MAX_FIELDS = 40
MAX_VALUE_LENGTH = 240
MAX_TEXT_EXCERPT = 1200


class ImportPreviewError(ValueError):
    """Raised when a document cannot be safely previewed."""


@dataclass(frozen=True)
class ParsedDocument:
    format: str
    records: tuple[dict[str, Any], ...]
    text_excerpt: str = ""


def build_document_preview(
    file_name: str,
    data: bytes,
    *,
    mime_type: str = "",
    target_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Build a compact, write-free preview from a bounded upload."""
    name = str(file_name or "").strip()
    if not name:
        raise ImportPreviewError("Choose a document before starting the preview.")
    if not isinstance(data, bytes) or not data:
        raise ImportPreviewError("The selected document is empty.")
    if len(data) > MAX_BYTES:
        raise ImportPreviewError("The document is larger than the 4 MB preview limit.")

    parsed = _parse_document(name, data, mime_type)
    fields = _field_names(parsed.records)
    allowed = {str(field).strip() for field in (target_fields or set()) if str(field).strip()}
    unknown_fields = sorted(field for field in fields if allowed and field not in allowed)
    return {
        "version": "v1",
        "preview_id": sha256(data).hexdigest(),
        "file_name": name[:180],
        "format": parsed.format,
        "size_bytes": len(data),
        "record_count": len(parsed.records),
        "fields": fields,
        "records": [_compact_record(record) for record in parsed.records[:MAX_RECORDS]],
        "text_excerpt": parsed.text_excerpt,
        "unknown_fields": unknown_fields[:MAX_FIELDS],
        "write_required": False,
        "requires_approval": True,
        "model_training": False,
        "warnings": _warnings(parsed, unknown_fields),
    }


def _parse_document(file_name: str, data: bytes, mime_type: str) -> ParsedDocument:
    suffix = PurePath(file_name).suffix.lower()
    if suffix in {".json"} or "json" in mime_type.lower():
        return _parse_json(data)
    if suffix in {".csv", ".tsv"} or "csv" in mime_type.lower() or "tab-separated" in mime_type.lower():
        return _parse_csv(data, delimiter="\t" if suffix == ".tsv" else ",")
    if suffix in {".txt", ".md", ".text"} or mime_type.startswith("text/"):
        text = _decode_text(data)
        return ParsedDocument("text", ({"content": text[:MAX_TEXT_EXCERPT]},), text[:MAX_TEXT_EXCERPT])
    raise ImportPreviewError("This preview supports CSV, TSV, JSON and text documents. PDF/DOCX extraction will be added with the document parser phase.")


def _parse_json(data: bytes) -> ParsedDocument:
    try:
        value = json.loads(_decode_text(data))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImportPreviewError("The JSON document could not be read.") from error
    if isinstance(value, dict):
        records = (value,)
    elif isinstance(value, list) and all(isinstance(item, dict) for item in value[:MAX_RECORDS]):
        records = tuple(value[:MAX_RECORDS])
    else:
        raise ImportPreviewError("JSON must contain an object or a list of objects.")
    return ParsedDocument("json", records)


def _parse_csv(data: bytes, *, delimiter: str) -> ParsedDocument:
    text = _decode_text(data)
    try:
        rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
    except csv.Error as error:
        raise ImportPreviewError("The tabular document could not be read.") from error
    if not rows or not any(str(key or "").strip() for key in rows[0]):
        raise ImportPreviewError("The tabular document needs a header row and at least one record.")
    return ParsedDocument("tsv" if delimiter == "\t" else "csv", tuple(rows[:MAX_RECORDS]))


def _decode_text(data: bytes) -> str:
    return data.decode("utf-8-sig", errors="replace").replace("\x00", "")


def _field_names(records: tuple[dict[str, Any], ...]) -> list[str]:
    names = []
    seen = set()
    for record in records:
        for key in record:
            clean = re.sub(r"\s+", " ", str(key or "").strip())[:120]
            if clean and clean not in seen:
                seen.add(clean)
                names.append(clean)
                if len(names) >= MAX_FIELDS:
                    return names
    return names


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in list(record.items())[:MAX_FIELDS]:
        clean_key = str(key or "").strip()[:120]
        if not clean_key:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        result[clean_key] = str(value or "")[:MAX_VALUE_LENGTH]
    return result


def _warnings(parsed: ParsedDocument, unknown_fields: list[str]) -> list[str]:
    warnings = []
    if parsed.format in {"csv", "tsv"} and len(parsed.records) >= MAX_RECORDS:
        warnings.append(f"Preview limited to the first {MAX_RECORDS} records.")
    if unknown_fields:
        warnings.append("Some uploaded fields are not available on the selected DocType.")
    warnings.append("Preview only: no ERP document was created or changed.")
    return warnings
