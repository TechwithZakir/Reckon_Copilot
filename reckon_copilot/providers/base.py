"""Base provider contract for future Reckon Copilot LLM adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderRequest:
    """Minimal request object shared by provider implementations."""

    prompt: str
    capability: str = "health_check"
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    """Minimal structured response returned by provider implementations."""

    text: str
    provider: str
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class AIProvider(ABC):
    """Stable interface for provider adapters.

    Phase 0 defines the contract only. Real LLM/network calls are introduced in
    a later phase behind this boundary.
    """

    provider_name: str

    @abstractmethod
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return a response for a request."""

