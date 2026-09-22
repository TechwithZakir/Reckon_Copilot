from __future__ import annotations

import unittest

from reckon_copilot.api.ask import answer_from_evidence, ask_with_services
from reckon_copilot.cache.manager import CacheManager, InMemoryCacheBackend
from reckon_copilot.knowledge.models import Evidence
from reckon_copilot.knowledge.rag import RagContext
from reckon_copilot.permissions.boundary import StaticPermissionAdapter
from reckon_copilot.providers.base import AIProvider, ProviderDisabled, ProviderRequest, ProviderResponse, ProviderResponseError, ProviderTimeout
from reckon_copilot.providers.manager import ProviderConfig, ProviderManager
from reckon_copilot.providers.llm import LocalLLMProvider, LLMProviderConfig
from reckon_copilot.providers.prompts import build_compact_prompt, compact_context, compact_evidence
from reckon_copilot.providers.schemas import parse_answer_payload
from reckon_copilot.providers.usage import InMemoryUsageLogger


class FakeProvider(AIProvider):
    provider_name = "local_llm"

    def __init__(self, text='{"answer":"ok","confidence":"high","evidence_ids":["c1"]}', error=None):
        self.text = text
        self.error = error
        self.calls = 0
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        self.requests.append(request)
        if self.error:
            raise self.error
        return ProviderResponse(text=self.text, provider="local_llm", model=request.model, latency_ms=25)


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate(self, base_url, payload, timeout_seconds):
        self.calls.append((base_url, payload, timeout_seconds))
        return self.payload


class FakeRag:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = 0

    def build_context(self, question, context, user, top_k=5):
        self.calls += 1
        return RagContext(question=question, evidence=self.evidence)


class ProviderPhaseTests(unittest.TestCase):
    def test_llm_uses_configured_model_and_transport(self):
        transport = FakeTransport({"response": '{"answer":"hello"}', "model": "llama3.1"})
        provider = LocalLLMProvider(
            LLMProviderConfig(enabled=True, model="llama3.1", base_url="http://local_llm.test"),
            transport=transport,
        )

        response = provider.complete(ProviderRequest(prompt="Hi", system_prompt="System"))

        self.assertEqual(response.model, "llama3.1")
        self.assertEqual(transport.calls[0][1]["model"], "llama3.1")
        self.assertEqual(transport.calls[0][1]["format"], "json")

    def test_llm_uses_configured_stream_flag(self):
        transport = FakeTransport({"response": '{"answer":"hello"}', "model": "llama3.1"})
        provider = LocalLLMProvider(
            LLMProviderConfig(enabled=True, model="llama3.1", stream_response=True),
            transport=transport,
        )

        provider.complete(ProviderRequest(prompt="Hi"))

        self.assertTrue(transport.calls[0][1]["stream"])

    def test_llm_can_be_disabled(self):
        provider = LocalLLMProvider(LLMProviderConfig(enabled=False, model="llama3.1"), transport=FakeTransport({}))

        with self.assertRaises(ProviderDisabled):
            provider.complete(ProviderRequest(prompt="Hi"))

    def test_unknown_provider_key_raises_provider_disabled_not_key_error(self):
        manager = ProviderManager(
            ProviderConfig(provider="missing_provider", enabled=True, model="local"),
            providers={"local_llm": FakeProvider()},
        )

        with self.assertRaises(ProviderDisabled):
            manager.complete(ProviderRequest(prompt="Hi"))

    def test_frappe_style_config_without_model_does_not_raise_key_error(self):
        class FrappeDict(dict):
            def __getattr__(self, key):
                if key in self:
                    return self[key]
                raise KeyError(key)

        manager = ProviderManager(
            FrappeDict(provider="local_llm", enabled=True),
            providers={"local_llm": FakeProvider()},
        )

        response = manager.complete(ProviderRequest(prompt="Hi", model="local"))

        self.assertEqual(response.text, '{"answer":"ok","confidence":"high","evidence_ids":["c1"]}')

    def test_provider_manager_preserves_stream_response_config(self):
        manager = ProviderManager(ProviderConfig(enabled=True, model="local", stream_response=True))

        self.assertTrue(manager.config.stream_response)

    def test_invalid_model_output_is_rejected(self):
        with self.assertRaises(ProviderResponseError):
            parse_answer_payload("not json")

    def test_prompt_contains_only_compact_sanitized_context_and_evidence(self):
        context = {
            "page_type": "Form",
            "doctype": "Sales Invoice",
            "document_name": "SINV-0001",
            "html": "<div>full document</div>",
            "permission": {"scope_hash": "abc"},
            "filters": {"api_secret": "hidden"},
        }
        evidence = [{"chunk_id": "c1", "source_id": "s1", "text": "<script>bad</script>" + ("x" * 1000)}]

        bundle = build_compact_prompt("Explain this", context, evidence)

        self.assertNotIn("full document", bundle.user_prompt)
        self.assertNotIn("<script>", bundle.user_prompt)
        self.assertIn("Sales Invoice", bundle.user_prompt)
        self.assertLess(len(compact_evidence(evidence)[0]["text"]), 520)
        self.assertNotIn("html", compact_context(context))

    def test_cache_prevents_second_provider_call(self):
        provider = FakeProvider()
        manager = ProviderManager(
            ProviderConfig(enabled=True, model="local-model"),
            providers={"local_llm": provider},
        )
        cache = CacheManager(InMemoryCacheBackend())
        adapter = StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True})

        kwargs = {
            "question": "Why is this pending?",
            "context": {"page_type": "List", "doctype": "Sales Order", "filters": {}},
            "provider_manager": manager,
            "cache_manager": cache,
            "permission_adapter": adapter,
            "user": "user@example.com",
        }
        first = ask_with_services(**kwargs)
        second = ask_with_services(**kwargs)

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(provider.calls, 1)

    def test_timeout_is_reported_without_retry_blocking(self):
        provider = FakeProvider(error=ProviderTimeout("slow"))
        manager = ProviderManager(ProviderConfig(enabled=True, model="local"), providers={"local_llm": provider})
        adapter = StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True})

        with self.assertRaises(ProviderTimeout):
            ask_with_services(
                question="Why is this pending?",
                context={"page_type": "List", "doctype": "Sales Order", "filters": {}},
                provider_manager=manager,
                permission_adapter=adapter,
                user="user@example.com",
            )

    def test_timeout_log_includes_provider_diagnostics(self):
        provider = FakeProvider(error=ProviderTimeout("slow"))
        manager = ProviderManager(
            ProviderConfig(enabled=True, model="local", stream_response=True, timeout_seconds=2, retries=0),
            providers={"local_llm": provider},
        )
        adapter = StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True})
        logger = InMemoryUsageLogger()

        with self.assertRaises(ProviderTimeout):
            ask_with_services(
                question="Why is this pending?",
                context={"page_type": "List", "doctype": "Sales Order", "filters": {}},
                provider_manager=manager,
                permission_adapter=adapter,
                usage_logger=logger,
                user="user@example.com",
            )

        self.assertEqual(logger.records[0].status, "ProviderTimeout")
        self.assertTrue(logger.records[0].metadata["stream_response"])
        self.assertEqual(logger.records[0].metadata["timeout_seconds"], 2)

    def test_simple_knowledge_question_avoids_llm(self):
        payload = answer_from_evidence("What is stock reorder?", [{"chunk_id": "c1", "text": "Stock reorder uses reorder levels."}])

        self.assertIsNotNone(payload)
        self.assertEqual(payload.source, "knowledge")

    def test_ask_auto_retrieves_rag_evidence_before_llm(self):
        provider = FakeProvider()
        manager = ProviderManager(ProviderConfig(enabled=True, model="local"), providers={"local_llm": provider})
        adapter = StaticPermissionAdapter(doctype_permissions={("Item", "read"): True})
        rag = FakeRag(
            [
                Evidence(
                    chunk_id="c1",
                    document_id="d1",
                    source_id="s1",
                    source_title="Stock SOP",
                    source_type="MANUAL_TEXT",
                    locator="manual",
                    version="1",
                    score=1,
                    text="Stock reorder uses reorder levels.",
                    metadata={"untrusted": True},
                )
            ]
        )

        result = ask_with_services(
            question="What is stock reorder?",
            context={"page_type": "List", "doctype": "Item", "filters": {}},
            evidence=[],
            provider_manager=manager,
            permission_adapter=adapter,
            rag=rag,
            user="user@example.com",
        )

        self.assertEqual(result.payload.source, "knowledge")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(rag.calls, 1)

    def test_context_question_reaches_provider_after_cache_rules_and_knowledge(self):
        provider = FakeProvider()
        manager = ProviderManager(ProviderConfig(enabled=True, model="local"), providers={"local_llm": provider})
        adapter = StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True})

        result = ask_with_services(
            question="Why is this pending?",
            context={"page_type": "List", "doctype": "Sales Order", "filters": {}},
            evidence=[],
            provider_manager=manager,
            permission_adapter=adapter,
            user="user@example.com",
        )

        self.assertTrue(result.provider_called)
        self.assertEqual(provider.calls, 1)

    def test_usage_metrics_recorded(self):
        provider = FakeProvider()
        manager = ProviderManager(ProviderConfig(enabled=True, model="local"), providers={"local_llm": provider})
        adapter = StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True})
        logger = InMemoryUsageLogger()

        ask_with_services(
            question="Why is this pending?",
            context={"page_type": "List", "doctype": "Sales Order", "filters": {}},
            provider_manager=manager,
            permission_adapter=adapter,
            usage_logger=logger,
            user="user@example.com",
        )

        self.assertEqual(logger.records[0].status, "ok")
        self.assertGreater(logger.records[0].prompt_chars, 0)


if __name__ == "__main__":
    unittest.main()
