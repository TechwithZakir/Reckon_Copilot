from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
from typing import Any


MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 100
MAX_FIELDS = 40
MAX_VALUE_LENGTH = 240
MAX_TEXT_EXCERPT = 1200
MAX_PDF_STREAM_BYTES = 2 * 1024 * 1024
MAX_PDF_DECODED_BYTES = 2 * 1024 * 1024
MAX_DOCX_ENTRIES = 100
MAX_DOCX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024
MAX_DOCX_XML_BYTES = 2 * 1024 * 1024


class ImportPreviewError(ValueError):
    """Raised when a document cannot be safely previewed."""


@dataclass(frozen=True)
class ParsedDocument:
    format: str
    records: tuple[dict[str, Any], ...]
    text_excerpt: str = ""
    structured: bool = True


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
        "structured": parsed.structured,
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
    if suffix == ".pdf" or mime_type.lower() == "application/pdf":
        return _parse_pdf(data)
    if suffix == ".docx" or "wordprocessingml.document" in mime_type.lower():
        return _parse_docx(data)
    if suffix in {".txt", ".md", ".text"} or mime_type.startswith("text/"):
        text = _decode_text(data)
        return ParsedDocument("text", ({"content": text[:MAX_TEXT_EXCERPT]},), text[:MAX_TEXT_EXCERPT])
    raise ImportPreviewError("This preview supports CSV, TSV, JSON, text, PDF and DOCX documents.")


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


def _parse_pdf(data: bytes) -> ParsedDocument:
    if not data.lstrip().startswith(b"%PDF-"):
        raise ImportPreviewError("The PDF document could not be read.")

    fragments: list[str] = []
    stream_pattern = re.compile(rb"stream(?:\r\n|\n|\r)")
    for match in stream_pattern.finditer(data):
        end = data.find(b"endstream", match.end())
        if end < 0:
            continue
        raw = data[match.end():end].rstrip(b"\r\n")
        if len(raw) > MAX_PDF_STREAM_BYTES:
            raise ImportPreviewError("The PDF contains a stream larger than the safe preview limit.")
        header = data[max(0, match.start() - 4096):match.start()]
        decoded = raw
        if b"/FlateDecode" in header:
            try:
                decoder = zlib.decompressobj()
                decoded = decoder.decompress(raw, MAX_PDF_DECODED_BYTES + 1)
                if len(decoded) > MAX_PDF_DECODED_BYTES or decoder.unconsumed_tail:
                    raise ValueError("decoded stream too large")
                decoded += decoder.flush(MAX_PDF_DECODED_BYTES + 1 - len(decoded))
            except (OSError, ValueError, zlib.error) as error:
                raise ImportPreviewError("The PDF contains compressed content that could not be read safely.") from error
        fragments.extend(_pdf_text_fragments(decoded))
        if sum(len(item) for item in fragments) >= MAX_TEXT_EXCERPT:
            break

    text = _normalise_text(" ".join(fragments))[:MAX_TEXT_EXCERPT]
    if not text:
        raise ImportPreviewError("The PDF has no readable text. Scanned PDFs require OCR and cannot be imported yet.")
    return ParsedDocument("pdf", (), text, False)


def _parse_docx(data: bytes) -> ParsedDocument:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as error:
        raise ImportPreviewError("The DOCX document could not be read.") from error

    try:
        members = archive.infolist()
        if len(members) > MAX_DOCX_ENTRIES:
            raise ImportPreviewError("The DOCX contains too many embedded parts for a safe preview.")
        total_size = 0
        for member in members:
            if member.flag_bits & 0x1:
                raise ImportPreviewError("Encrypted DOCX files cannot be previewed.")
            total_size += max(0, int(member.file_size))
            if total_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ImportPreviewError("The DOCX expands beyond the safe preview limit.")
        try:
            document = archive.getinfo("word/document.xml")
        except KeyError as error:
            raise ImportPreviewError("The DOCX does not contain a readable document body.") from error
        if document.file_size > MAX_DOCX_XML_BYTES:
            raise ImportPreviewError("The DOCX document body is larger than the safe preview limit.")
        xml = archive.read(document)
    except ImportPreviewError:
        raise
    except (OSError, zipfile.BadZipFile) as error:
        raise ImportPreviewError("The DOCX document could not be read safely.") from error
    finally:
        archive.close()

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ImportPreviewError("The DOCX document body is not valid XML.") from error

    paragraphs: list[str] = []
    for paragraph in root.iter():
        if _xml_local_name(paragraph.tag) != "p":
            continue
        parts = [str(node.text or "") for node in paragraph.iter() if _xml_local_name(node.tag) == "t"]
        value = _normalise_text("".join(parts))
        if value:
            paragraphs.append(value)
    text = _normalise_text("\n".join(paragraphs))[:MAX_TEXT_EXCERPT]
    if not text:
        raise ImportPreviewError("The DOCX has no readable text.")
    return ParsedDocument("docx", (), text, False)


def _pdf_text_fragments(data: bytes) -> list[str]:
    fragments: list[str] = []
    index = 0
    while index < len(data) and len(fragments) < MAX_FIELDS * 8:
        if data[index] == 0x28:  # PDF literal string
            value, index = _read_pdf_literal(data, index)
            if value:
                fragments.append(_decode_pdf_bytes(value))
            continue
        if data[index] == 0x3C and index + 1 < len(data) and data[index + 1] != 0x3C:  # hex string
            end = data.find(b">", index + 1)
            if end < 0:
                break
            raw = re.sub(rb"\s+", b"", data[index + 1:end])
            if re.fullmatch(rb"[0-9A-Fa-f]*", raw or b""):
                if len(raw) % 2:
                    raw += b"0"
                fragments.append(_decode_pdf_bytes(bytes.fromhex(raw.decode("ascii"))))
            index = end + 1
            continue
        index += 1
    return [item for item in fragments if item]


def _read_pdf_literal(data: bytes, start: int) -> tuple[bytes, int]:
    value = bytearray()
    depth = 1
    index = start + 1
    while index < len(data) and depth:
        byte = data[index]
        if byte == 0x5C:  # backslash escape
            if index + 1 >= len(data):
                break
            index += 1
            escaped = data[index]
            if escaped in b"nrtbf":
                value.append({ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}[escaped])
            elif 0x30 <= escaped <= 0x37:
                digits = bytes([escaped])
                while len(digits) < 3 and index + 1 < len(data) and 0x30 <= data[index + 1] <= 0x37:
                    index += 1
                    digits += bytes([data[index]])
                value.append(int(digits, 8))
            elif escaped not in b"\r\n":
                value.append(escaped)
        elif byte == 0x28:
            depth += 1
            value.append(byte)
        elif byte == 0x29:
            depth -= 1
            if depth:
                value.append(byte)
        else:
            value.append(byte)
        index += 1
    return bytes(value), index


def _decode_pdf_bytes(value: bytes) -> str:
    if value.startswith(b"\xfe\xff"):
        return value[2:].decode("utf-16-be", errors="replace")
    return value.decode("utf-8", errors="replace")


def _xml_local_name(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
    if not parsed.structured:
        warnings.append("Text extraction only: structured import mapping is not available for this file format.")
    warnings.append("Preview only: no ERP document was created or changed.")
    return warnings
