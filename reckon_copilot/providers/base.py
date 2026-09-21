"""Provider contracts for Reckon Copilot LLM adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


class ProviderError(RuntimeError):
    """Base class for provider failures handled by the ask pipeline."""


class ProviderDisabled(ProviderError):
    """Raised when a provider is intentionally disabled or incomplete."""


class ProviderTimeout(ProviderError):
    """Raised when a provider cannot answer within the configured timeout."""


class ProviderResponseError(ProviderError):
    """Raised when a provider response is malformed or unsafe to use."""


@dataclass(frozen=True)
class ProviderRequest:
    """Request object shared by provider implementations."""

    prompt: str
    system_prompt: str = ""
    capability: str = "health_check"
    context: Mapping[str, Any] = field(default_factory=dict)
    model: str | None = None
    timeout_seconds: float = 15.0


@dataclass(frozen=True)
class ProviderResponse:
    """Structured response returned by provider implementations."""

    text: str
    provider: str
    model: str | None = None
    latency_ms: int = 0
    usage: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


class AIProvider(ABC):
    """Stable interface for provider adapters.

    Provider implementations own transport details. Callers only pass a compact
    prompt and receive a validated, schema-shaped answer.
    """

    provider_name: str

    @abstractmethod
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return a response for a request."""
