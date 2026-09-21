from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reckon_copilot.cache.keys import build_cache_identity, build_cache_key
from reckon_copilot.cache.manager import CacheManager, FrappeCacheBackend
from reckon_copilot.cache.ttl import ttl_for
from reckon_copilot.context.builders import build_context
from reckon_copilot.knowledge.rag import RagOrchestrator
from reckon_copilot.knowledge.repository import FrappeKnowledgeRepository
from reckon_copilot.knowledge.retriever import KnowledgeRetriever
from reckon_copilot.permissions.boundary import (
    CAPABILITY_CALL_PROVIDER,
    CopilotPermissionBoundary,
    FrappePermissionAdapter,
    PermissionAdapter,
    PermissionDenied,
    authorize_context,
)
from reckon_copilot.providers.base import ProviderDisabled, ProviderRequest, ProviderResponseError, ProviderTimeout
from reckon_copilot.providers.intent import classify_intent
from reckon_copilot.providers.manager import ProviderConfig, ProviderManager, provider_manager_from_frappe
from reckon_copilot.providers.prompts import PROMPT_VERSION, build_compact_prompt
from reckon_copilot.providers.schemas import AnswerPayload, parse_answer_payload, validate_answer_payload
from reckon_copilot.providers.usage import FrappeUsageLogger, InMemoryUsageLogger, UsageRecord


@dataclass(frozen=True)
class AskResult:
    payload: AnswerPayload
    cache_hit: bool = False
    provider_called: bool = False
    provider: str = "none"
    model: str = "none"
    latency_ms: int = 0
    intent: str = "general"
    evidence: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "cache_hit": self.cache_hit,
            "provider_called": self.provider_called,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "intent": self.intent,
            "evidence": list(self.evidence),
            "answer": self.payload.as_dict(),
        }


def ask_with_services(
    *,
    question: str,
    context: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    user: str | None = None,
    provider_manager: ProviderManager,
    cache_manager: CacheManager | None = None,
    usage_logger: InMemoryUsageLogger | FrappeUsageLogger | None = None,
    permission_adapter: PermissionAdapter | None = None,
    rag: RagOrchestrator | None = None,
    site: str = "default",
) -> AskResult:
    question = (question or "").strip()
    if not question:
        raise ValueError("Question is required")

    authorized = authorize_context(
        context,
        capability=CAPABILITY_CALL_PROVIDER,
        user=user,
        adapter=permission_adapter,
    ).context
    evidence = evidence or []
    intent = classify_intent(question)
    if not evidence and rag:
        evidence = rag.build_context(question, authorized, user or "user@example.com").as_prompt_context()
    logger = usage_logger or InMemoryUsageLogger()
    config = provider_manager.config
    prompt = build_compact_prompt(question, authorized, evidence, intent=intent)

    deterministic = answer_from_evidence(question, evidence)
    if deterministic:
        result = AskResult(
            payload=deterministic,
            provider="knowledge",
            model="rules",
            intent=intent,
            evidence=tuple(_compact_evidence_meta(evidence, deterministic.evidence_ids)),
        )
        logger.log(
            UsageRecord(
                provider="knowledge",
                model="rules",
                capability=CAPABILITY_CALL_PROVIDER,
                status="answered_without_llm",
                cache_hit=False,
                prompt_chars=prompt.prompt_chars,
                response_chars=len(deterministic.answer),
            )
        )
        return result

    def compute() -> dict[str, Any]:
        response = provider_manager.complete(
            ProviderRequest(
                prompt=prompt.user_prompt,
                system_prompt=prompt.system_prompt,
                capability=CAPABILITY_CALL_PROVIDER,
                context=authorized,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
            )
        )
        payload = parse_answer_payload(response.text, source=response.provider)
        logger.log(
            UsageRecord(
                provider=response.provider,
                model=response.model or "unknown",
                capability=CAPABILITY_CALL_PROVIDER,
                status="ok",
                cache_hit=False,
                latency_ms=response.latency_ms,
                prompt_chars=prompt.prompt_chars,
                response_chars=len(payload.answer),
                metadata=dict(response.usage),
            )
        )
        return {
            "payload": payload.as_dict(),
            "provider": response.provider,
            "model": response.model or "unknown",
            "latency_ms": response.latency_ms,
            "intent": intent,
            "evidence": _compact_evidence_meta(evidence, payload.evidence_ids),
        }

    identity = build_cache_identity(
        context=authorized,
        capability=CAPABILITY_CALL_PROVIDER,
        question=question,
        site=site,
        provider=config.provider,
        model=config.model or "none",
        prompt_version=PROMPT_VERSION,
        data_version="knowledge-v1",
        extra={"evidence_ids": ",".join(_evidence_ids(evidence)), "intent": intent},
    )
    cache_key = build_cache_key(identity, namespace="copilot:ask")

    try:
        result = cache_manager.get_or_compute(cache_key, compute, ttl_for(CAPABILITY_CALL_PROVIDER)) if cache_manager else None
        value = result.value if result else compute()
        payload = validate_answer_payload(value["payload"], source=value.get("provider") or "llm")
        if result and result.hit:
            logger.log(
                UsageRecord(
                    provider=value.get("provider") or config.provider,
                    model=value.get("model") or config.model or "unknown",
                    capability=CAPABILITY_CALL_PROVIDER,
                    status="cache_hit",
                    cache_hit=True,
                    latency_ms=int(value.get("latency_ms") or 0),
                    prompt_chars=prompt.prompt_chars,
                    response_chars=len(payload.answer),
                )
            )
        return AskResult(
            payload=payload,
            cache_hit=bool(result and result.hit),
            provider_called=not bool(result and result.hit),
            provider=value.get("provider") or config.provider,
            model=value.get("model") or config.model or "unknown",
            latency_ms=int(value.get("latency_ms") or 0),
            intent=str(value.get("intent") or intent),
            evidence=tuple(value.get("evidence") or _compact_evidence_meta(evidence, payload.evidence_ids)),
        )
    except (ProviderDisabled, ProviderTimeout, ProviderResponseError) as error:
        logger.log(
            UsageRecord(
                provider=config.provider,
                model=config.model or "none",
                capability=CAPABILITY_CALL_PROVIDER,
                status=error.__class__.__name__,
                cache_hit=False,
                prompt_chars=prompt.prompt_chars,
                error=str(error),
            )
        )
        raise


def answer_from_evidence(question: str, evidence: list[dict[str, Any]]) -> AnswerPayload | None:
    if not evidence:
        return None
    normalized_question = question.strip().lower()
    simple_prefixes = ("what is", "what are", "how to", "how do", "explain", "show")
    if not normalized_question.startswith(simple_prefixes):
        return None
    top = evidence[0]
    text = str(top.get("text") or "").strip()
    if not text:
        return None
    return AnswerPayload(
        answer=text[:700],
        confidence="medium",
        evidence_ids=tuple(_evidence_ids(evidence[:1])),
        warnings=("Answered from approved knowledge evidence without calling the LLM.",),
        source="knowledge",
    )


def _evidence_ids(evidence: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("chunk_id") or item.get("source_id") or "") for item in evidence if item.get("chunk_id") or item.get("source_id")]


def _compact_evidence_meta(evidence: list[dict[str, Any]], selected_ids=()) -> list[dict[str, Any]]:
    selected = set(selected_ids or [])
    items = []
    for item in evidence[:5]:
        evidence_id = str(item.get("chunk_id") or item.get("source_id") or "")
        if selected and evidence_id not in selected:
            continue
        items.append(
            {
                "chunk_id": evidence_id,
                "source_title": str(item.get("source_title") or "")[:160],
                "locator": str(item.get("locator") or "")[:200],
                "score": item.get("score"),
            }
        )
    return items


def _frappe_site(frappe_module) -> str:
    return str(getattr(getattr(frappe_module, "local", None), "site", "default") or "default")


try:
    import frappe  # type: ignore
except Exception:  # pragma: no cover
    frappe = None


if frappe:

    @frappe.whitelist()
    def ask(question: str, route=None, filters=None, page_type: str | None = None, context=None, evidence=None):
        import json

        try:
            context_payload = context
            if isinstance(context_payload, str):
                context_payload = json.loads(context_payload)
            if not isinstance(context_payload, dict):
                context_payload = build_context(route=route, filters=filters, page_type=page_type)
            evidence_payload = evidence
            if isinstance(evidence_payload, str):
                evidence_payload = json.loads(evidence_payload)
            if not isinstance(evidence_payload, list):
                evidence_payload = []
            result = ask_with_services(
                question=question,
                context=context_payload,
                evidence=evidence_payload,
                user=getattr(frappe.session, "user", None),
                provider_manager=provider_manager_from_frappe(frappe),
                cache_manager=CacheManager(FrappeCacheBackend(frappe)),
                usage_logger=FrappeUsageLogger(frappe),
                rag=RagOrchestrator(
                    KnowledgeRetriever(
                        FrappeKnowledgeRepository(frappe),
                        permission_boundary=CopilotPermissionBoundary(FrappePermissionAdapter(frappe)),
                    ),
                    cache_manager=CacheManager(FrappeCacheBackend(frappe)),
                    site=_frappe_site(frappe),
                ),
                site=_frappe_site(frappe),
            )
            return result.as_dict()
        except PermissionDenied as error:
            return {"ok": False, "access_denied": True, "message": str(error)}
        except (ProviderDisabled, ProviderTimeout, ProviderResponseError) as error:
            return {"ok": False, "provider_error": True, "message": str(error)}
