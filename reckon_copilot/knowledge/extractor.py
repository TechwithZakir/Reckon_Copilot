from __future__ import annotations

import re
import zipfile
from pathlib import Path

from reckon_copilot.knowledge.models import KnowledgeSource, KnowledgeSourceType, normalize_text


class ExtractionError(RuntimeError):
    pass


class KnowledgeExtractor:
    def extract(self, source: KnowledgeSource, payload: str | bytes | None = None) -> str:
        if source.source_type in {KnowledgeSourceType.MANUAL_TEXT, KnowledgeSourceType.INTERNAL_DOCUMENT}:
            return normalize_text(str(payload or source.description or ""))
        if source.source_type in {KnowledgeSourceType.WEB_URL, KnowledgeSourceType.MANUAL_URL}:
            return self._extract_url_text(source, payload)
        if source.source_type == KnowledgeSourceType.DOCX:
            return self._extract_docx(payload)
        if source.source_type == KnowledgeSourceType.PDF:
            return self._extract_pdf(payload)
        if source.source_type == KnowledgeSourceType.ERP_DATABASE:
            return normalize_text(str(payload or ""))
        raise ExtractionError(f"Unsupported knowledge source type: {source.source_type}")

    def _extract_url_text(self, source: KnowledgeSource, payload: str | bytes | None) -> str:
        if not re.match(r"^https?://", source.origin or ""):
            raise ExtractionError("Only http(s) URLs are allowed")
        return normalize_text(str(payload or source.description or source.origin))

    def _extract_docx(self, payload: str | bytes | None) -> str:
        if payload is None:
            raise ExtractionError("DOCX payload is required")
        path = Path(str(payload))
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
        except Exception as error:
            raise ExtractionError("DOCX extraction failed") from error
        xml = re.sub(r"</w:p>", "\n", xml)
        return normalize_text(re.sub(r"<[^>]+>", " ", xml))

    def _extract_pdf(self, payload: str | bytes | None) -> str:
        if isinstance(payload, bytes):
            text = payload.decode("utf-8", errors="ignore")
        else:
            path = Path(str(payload or ""))
            if not path.exists():
                raise ExtractionError("PDF payload is required")
            text = path.read_bytes().decode("utf-8", errors="ignore")
        return normalize_text(text)

