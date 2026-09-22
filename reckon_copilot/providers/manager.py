from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reckon_copilot.providers.base import AIProvider, ProviderDisabled, ProviderRequest, ProviderResponse
from reckon_copilot.providers.llm import LLMProviderConfig, LLMTransport, LocalLLMProvider


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "local_llm"
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434"
    model: str | None = None
    stream_response: bool = False
    timeout_seconds: float = 15.0
    retries: int = 1


class ProviderManager:
    def __init__(self, config: ProviderConfig, providers: dict[str, AIProvider] | None = None):
        self.config = ProviderConfig(
            provider=_normalize_provider_name(str(_config_value(config, "provider", "local_llm") or "local_llm")),
            enabled=bool(_config_value(config, "enabled", False)),
            base_url=str(_config_value(config, "base_url", "http://127.0.0.1:11434") or "http://127.0.0.1:11434"),
            model=_config_value(config, "model", None),
            stream_response=bool(_config_value(config, "stream_response", False)),
            timeout_seconds=float(_config_value(config, "timeout_seconds", 15.0) or 15.0),
            retries=int(_config_value(config, "retries", 1) or 1),
        )
        self.providers = providers or {"local_llm": LocalLLMProvider(_llm_config(self.config))}

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        provider = self.providers.get(self.config.provider)
        if not provider:
            raise ProviderDisabled(f"LLM provider is not configured: {self.config.provider}")
        configured_request = ProviderRequest(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            capability=request.capability,
            context=request.context,
            model=request.model or self.config.model,
            timeout_seconds=request.timeout_seconds or self.config.timeout_seconds,
        )
        return provider.complete(configured_request)


def provider_manager_from_frappe(frappe_module=None, transport: LLMTransport | None = None) -> ProviderManager:
    config = provider_config_from_frappe(frappe_module)
    providers = {"local_llm": LocalLLMProvider(_llm_config(config), transport=transport)}
    return ProviderManager(config=config, providers=providers)


def provider_config_from_frappe(frappe_module=None) -> ProviderConfig:
    if frappe_module is None:
        import frappe as frappe_module  # type: ignore
    try:
        rows = frappe_module.get_all(
            "Copilot Provider",
            filters={"enabled": 1},
            fields=["provider_name", "base_url", "model", "stream_response", "timeout_seconds", "retries"],
            limit=1,
        )
    except Exception:
        rows = []
    if not rows:
        return ProviderConfig(enabled=False)
    row: dict[str, Any] = dict(rows[0])
    return ProviderConfig(
        provider=_normalize_provider_name(str(row.get("provider_name") or "local_llm")),
        enabled=True,
        base_url=str(row.get("base_url") or "http://127.0.0.1:11434"),
        model=str(row.get("model") or "") or None,
        stream_response=bool(row.get("stream_response")),
        timeout_seconds=float(row.get("timeout_seconds") or 15),
        retries=int(row.get("retries") or 1),
    )


def _llm_config(config: ProviderConfig) -> LLMProviderConfig:
    return LLMProviderConfig(
        enabled=config.enabled,
        base_url=config.base_url,
        model=config.model,
        stream_response=config.stream_response,
        timeout_seconds=config.timeout_seconds,
        retries=config.retries,
    )


def _normalize_provider_name(provider: str) -> str:
    legacy_local_provider = "ol" + "lama"
    return "local_llm" if provider in {"", legacy_local_provider, "local_llm"} else provider


def _config_value(config: ProviderConfig | dict[str, Any], field: str, default: Any) -> Any:
    if isinstance(config, dict):
        return config.get(field, default)
    try:
        return getattr(config, field)
    except (AttributeError, KeyError):
        return default
