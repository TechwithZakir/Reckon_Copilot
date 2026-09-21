from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reckon_copilot.providers.base import AIProvider, ProviderRequest, ProviderResponse
from reckon_copilot.providers.ollama import OllamaProvider, OllamaProviderConfig, OllamaTransport


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "ollama"
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434"
    model: str | None = None
    timeout_seconds: float = 15.0
    retries: int = 1


class ProviderManager:
    def __init__(self, config: ProviderConfig, providers: dict[str, AIProvider] | None = None):
        self.config = config
        self.providers = providers or {"ollama": OllamaProvider(_ollama_config(config))}

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        provider = self.providers[self.config.provider]
        configured_request = ProviderRequest(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            capability=request.capability,
            context=request.context,
            model=request.model or self.config.model,
            timeout_seconds=request.timeout_seconds or self.config.timeout_seconds,
        )
        return provider.complete(configured_request)


def provider_manager_from_frappe(frappe_module=None, transport: OllamaTransport | None = None) -> ProviderManager:
    config = provider_config_from_frappe(frappe_module)
    providers = {"ollama": OllamaProvider(_ollama_config(config), transport=transport)}
    return ProviderManager(config=config, providers=providers)


def provider_config_from_frappe(frappe_module=None) -> ProviderConfig:
    if frappe_module is None:
        import frappe as frappe_module  # type: ignore
    try:
        rows = frappe_module.get_all(
            "Copilot Provider",
            filters={"enabled": 1},
            fields=["provider_name", "base_url", "model", "timeout_seconds", "retries"],
            limit=1,
        )
    except Exception:
        rows = []
    if not rows:
        return ProviderConfig(enabled=False)
    row: dict[str, Any] = dict(rows[0])
    return ProviderConfig(
        provider=str(row.get("provider_name") or "ollama"),
        enabled=True,
        base_url=str(row.get("base_url") or "http://127.0.0.1:11434"),
        model=str(row.get("model") or "") or None,
        timeout_seconds=float(row.get("timeout_seconds") or 15),
        retries=int(row.get("retries") or 1),
    )


def _ollama_config(config: ProviderConfig) -> OllamaProviderConfig:
    return OllamaProviderConfig(
        enabled=config.enabled,
        base_url=config.base_url,
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        retries=config.retries,
    )
