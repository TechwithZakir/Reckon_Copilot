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


class LLMTransport(Protocol):
    def generate(self, base_url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LLMProviderConfig:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434"
    model: str | None = None
    stream_response: bool = False
    timeout_seconds: float = 15.0
    retries: int = 1


class UrlLibLLMTransport:
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
                body = response.read().decode("utf-8")
                if payload.get("stream"):
                    return _combine_streamed_response(body)
                return json.loads(body)
        except (TimeoutError, socket.timeout) as error:
            raise ProviderTimeout("LLM request timed out") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, socket.timeout):
                raise ProviderTimeout("LLM request timed out") from error
            raise ProviderResponseError(f"LLM request failed: {error.reason}") from error
        except json.JSONDecodeError as error:
            raise ProviderResponseError("LLM provider returned invalid JSON") from error


class LocalLLMProvider(AIProvider):
    provider_name = "local_llm"

    def __init__(self, config: LLMProviderConfig, transport: LLMTransport | None = None):
        self.config = config
        self.transport = transport or UrlLibLLMTransport()

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        if not self.config.enabled:
            raise ProviderDisabled("LLM provider is disabled")
        model = request.model or self.config.model
        if not model:
            raise ProviderDisabled("LLM model is not configured")

        payload = {
            "model": model,
            "prompt": request.prompt,
            "system": request.system_prompt,
            "stream": self.config.stream_response,
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
                    raise ProviderResponseError("LLM response was empty")
                return ProviderResponse(
                    text=text,
                    provider=self.provider_name,
                    model=str(raw.get("model") or model),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    usage={
                        "prompt_eval_count": raw.get("prompt_eval_count"),
                        "eval_count": raw.get("eval_count"),
                        "total_duration": raw.get("total_duration"),
                        "load_duration": raw.get("load_duration"),
                        "prompt_eval_duration": raw.get("prompt_eval_duration"),
                        "eval_duration": raw.get("eval_duration"),
                        "stream": self.config.stream_response,
                        "base_url": self.config.base_url,
                    },
                    metadata={"done": raw.get("done", True)},
                )
            except ProviderTimeout:
                raise
            except ProviderResponseError as error:
                last_error = error
        raise ProviderResponseError(str(last_error or "LLM response failed validation"))


def _combine_streamed_response(body: str) -> dict[str, Any]:
    chunks = []
    last: dict[str, Any] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProviderResponseError("LLM provider returned invalid streamed JSON") from error
        chunks.append(str(item.get("response") or ""))
        last.update(item)
    if not last:
        raise ProviderResponseError("LLM provider returned empty streamed response")
    last["response"] = "".join(chunks)
    return last
