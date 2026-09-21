from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from reckon_copilot.providers.base import ProviderResponseError


ANSWER_SCHEMA_VERSION = "copilot.answer.v1"


@dataclass(frozen=True)
class AnswerPayload:
    answer: str
    confidence: str = "low"
    evidence_ids: tuple[str, ...] = ()
    followups: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str = ANSWER_SCHEMA_VERSION
    source: str = "llm"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "answer": self.answer,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "followups": list(self.followups),
            "warnings": list(self.warnings),
        }


def parse_answer_payload(raw: str | dict[str, Any], source: str = "llm") -> AnswerPayload:
    if isinstance(raw, str):
        payload = _parse_json_text(raw)
    else:
        payload = dict(raw)
    return validate_answer_payload(payload, source=source)


def validate_answer_payload(payload: dict[str, Any], source: str = "llm") -> AnswerPayload:
    answer = str(payload.get("answer") or "").strip()
    if not answer:
        raise ProviderResponseError("Provider response did not include an answer")

    confidence = str(payload.get("confidence") or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    return AnswerPayload(
        answer=answer[:2000],
        confidence=confidence,
        evidence_ids=tuple(_string_list(payload.get("evidence_ids"))[:8]),
        followups=tuple(_string_list(payload.get("followups"))[:4]),
        warnings=tuple(_string_list(payload.get("warnings"))[:6]),
        schema_version=ANSWER_SCHEMA_VERSION,
        source=source,
    )


def _parse_json_text(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProviderResponseError("Provider response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ProviderResponseError("Provider response must be a JSON object")
    return payload


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:160] for item in value if str(item).strip()]
