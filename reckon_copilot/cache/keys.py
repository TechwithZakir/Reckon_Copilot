from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reckon_copilot.context.builders import canonical_json
from reckon_copilot.knowledge.models import stable_hash


CACHE_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class CacheIdentity:
    site: str
    capability: str
    context_fingerprint: str
    permission_scope_hash: str
    question_hash: str = ""
    provider: str = "none"
    model: str = "none"
    prompt_version: str = "none"
    data_version: str = "none"
    extra: tuple[tuple[str, str], ...] = ()


def question_hash(question: str | None) -> str:
    return stable_hash((question or "").strip())


def permission_scope_hash(context: dict[str, Any]) -> str:
    permission = context.get("permission") or {}
    return str(permission.get("scope_hash") or "anonymous")


def context_fingerprint(context: dict[str, Any]) -> str:
    return str(context.get("fingerprint") or stable_hash(context))


def build_cache_identity(
    *,
    context: dict[str, Any],
    capability: str,
    question: str | None = None,
    site: str = "default",
    provider: str = "none",
    model: str = "none",
    prompt_version: str = "none",
    data_version: str = "none",
    extra: dict[str, Any] | None = None,
) -> CacheIdentity:
    return CacheIdentity(
        site=site,
        capability=capability,
        context_fingerprint=context_fingerprint(context),
        permission_scope_hash=permission_scope_hash(context),
        question_hash=question_hash(question),
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        data_version=data_version,
        extra=tuple(sorted((str(key), str(value)) for key, value in (extra or {}).items())),
    )


def build_cache_key(identity: CacheIdentity, namespace: str = "copilot") -> str:
    payload = canonical_json(
        {
            "schema": CACHE_SCHEMA_VERSION,
            "site": identity.site,
            "capability": identity.capability,
            "context": identity.context_fingerprint,
            "scope": identity.permission_scope_hash,
            "question": identity.question_hash,
            "provider": identity.provider,
            "model": identity.model,
            "prompt": identity.prompt_version,
            "data": identity.data_version,
            "extra": list(identity.extra),
        }
    )
    return f"{namespace}:{CACHE_SCHEMA_VERSION}:{stable_hash(payload)}"

