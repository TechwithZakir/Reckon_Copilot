from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from reckon_copilot.providers.base import (
    AIProvider,
    ProviderDisabled,
    ProviderRequest,
    ProviderResponse,
    ProviderResponseError,
    ProviderTimeout,
)


class OllamaTransport(Protocol):
    def generate(self, base_url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class OllamaProviderConfig:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434"
    model: str | None = None
    timeout_seconds: float = 15.0
    retries: int = 1


class UrlLibOllamaTransport:
    def generate(self, base_url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            base_url.rstrip("/") + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as error:
            raise ProviderTimeout("Ollama request timed out") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, socket.timeout):
                raise ProviderTimeout("Ollama request timed out") from error
            raise ProviderResponseError(f"Ollama request failed: {error.reason}") from error
        except json.JSONDecodeError as error:
            raise ProviderResponseError("Ollama returned invalid JSON") from error


class OllamaProvider(AIProvider):
    provider_name = "ollama"

    def __init__(self, config: OllamaProviderConfig, transport: OllamaTransport | None = None):
        self.config = config
        self.transport = transport or UrlLibOllamaTransport()

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        if not self.config.enabled:
            raise ProviderDisabled("Ollama provider is disabled")
        model = request.model or self.config.model
        if not model:
            raise ProviderDisabled("Ollama model is not configured")

        payload = {
            "model": model,
            "prompt": request.prompt,
            "system": request.system_prompt,
            "stream": False,
            "format": "json",
        }
        timeout = request.timeout_seconds or self.config.timeout_seconds
        attempts = max(1, self.config.retries + 1)
        last_error: Exception | None = None
        started = time.monotonic()
        for _attempt in range(attempts):
            try:
                raw = self.transport.generate(self.config.base_url, payload, timeout)
                text = str(raw.get("response") or "").strip()
                if not text:
                    raise ProviderResponseError("Ollama response was empty")
                return ProviderResponse(
                    text=text,
                    provider=self.provider_name,
                    model=str(raw.get("model") or model),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    usage={
                        "prompt_eval_count": raw.get("prompt_eval_count"),
                        "eval_count": raw.get("eval_count"),
                        "total_duration": raw.get("total_duration"),
                    },
                    metadata={"done": raw.get("done", True)},
                )
            except ProviderTimeout:
                raise
            except ProviderResponseError as error:
                last_error = error
        raise ProviderResponseError(str(last_error or "Ollama response failed validation"))
