from __future__ import annotations

import threading
import time
import unittest

from reckon_copilot.cache.keys import build_cache_identity, build_cache_key
from reckon_copilot.cache.manager import CacheManager, InMemoryCacheBackend
from reckon_copilot.knowledge.models import Evidence
from reckon_copilot.knowledge.rag import RagOrchestrator


class BrokenBackend:
    def get(self, key):
        raise RuntimeError("cache down")

    def set(self, key, value, ttl=None):
        raise RuntimeError("cache down")

    def delete(self, key):
        raise RuntimeError("cache down")


class FakeRetriever:
    def __init__(self):
        self.calls = 0

    def retrieve(self, request):
        self.calls += 1
        return [
            Evidence(
                chunk_id="chunk-1",
                document_id="doc-1",
                source_id="source-1",
                source_title="Manual",
                source_type="MANUAL_TEXT",
                locator="manual",
                version="v1",
                score=1.0,
                text=f"answer for {request.query}",
                metadata={"untrusted": True},
            )
        ]


class CacheTests(unittest.TestCase):
    def test_cache_key_changes_with_permission_scope(self):
        first = build_cache_key(
            build_cache_identity(
                context=_context("scope-a"),
                capability="knowledge.read",
                question="same question",
                site="site-a",
            )
        )
        second = build_cache_key(
            build_cache_identity(
                context=_context("scope-b"),
                capability="knowledge.read",
                question="same question",
                site="site-a",
            )
        )

        self.assertNotEqual(first, second)

    def test_cache_key_changes_with_versions(self):
        base = build_cache_identity(
            context=_context("scope-a"),
            capability="provider.call",
            question="forecast",
            provider="local_llm",
            model="llama",
            prompt_version="p1",
            data_version="d1",
        )
        changed = build_cache_identity(
            context=_context("scope-a"),
            capability="provider.call",
            question="forecast",
            provider="local_llm",
            model="llama",
            prompt_version="p2",
            data_version="d1",
        )

        self.assertNotEqual(build_cache_key(base), build_cache_key(changed))

    def test_get_or_compute_uses_cached_value(self):
        manager = CacheManager(InMemoryCacheBackend())
        calls = {"count": 0}

        def compute():
            calls["count"] += 1
            return {"ok": True}

        first = manager.get_or_compute("k", compute)
        second = manager.get_or_compute("k", compute)

        self.assertFalse(first.hit)
        self.assertTrue(second.hit)
        self.assertEqual(calls["count"], 1)

    def test_ttl_expiry_recomputes(self):
        manager = CacheManager(InMemoryCacheBackend())
        calls = {"count": 0}

        def compute():
            calls["count"] += 1
            return calls["count"]

        self.assertEqual(manager.get_or_compute("k", compute, ttl=1).value, 1)
        time.sleep(1.05)
        self.assertEqual(manager.get_or_compute("k", compute, ttl=1).value, 2)

    def test_single_flight_computes_once_for_concurrent_miss(self):
        manager = CacheManager(InMemoryCacheBackend(), lock_timeout=2)
        calls = {"count": 0}
        barrier = threading.Barrier(5)
        results = []

        def compute():
            calls["count"] += 1
            time.sleep(0.05)
            return {"value": 42}

        def worker():
            barrier.wait()
            results.append(manager.get_or_compute("shared", compute).value)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(calls["count"], 1)
        self.assertEqual(results, [{"value": 42}] * 5)

    def test_lock_timeout_does_not_permanently_block(self):
        manager = CacheManager(InMemoryCacheBackend(), lock_timeout=0.01)
        calls = {"count": 0}

        def compute():
            calls["count"] += 1
            time.sleep(0.05)
            return calls["count"]

        first = threading.Thread(target=lambda: manager.get_or_compute("slow", compute))
        first.start()
        time.sleep(0.005)
        result = manager.get_or_compute("slow", compute)
        first.join()

        self.assertGreaterEqual(calls["count"], 1)
        self.assertIn(result.value, {1, 2})

    def test_cache_failure_degrades_to_compute(self):
        manager = CacheManager(BrokenBackend())

        result = manager.get_or_compute("k", lambda: {"fallback": True})

        self.assertFalse(result.hit)
        self.assertEqual(result.value, {"fallback": True})

    def test_invalidate_removes_cached_value(self):
        manager = CacheManager(InMemoryCacheBackend())
        calls = {"count": 0}

        def compute():
            calls["count"] += 1
            return calls["count"]

        manager.get_or_compute("k", compute)
        manager.invalidate("k")
        self.assertEqual(manager.get_or_compute("k", compute).value, 2)

    def test_rag_cache_reuses_evidence_without_retrieval(self):
        retriever = FakeRetriever()
        rag = RagOrchestrator(retriever, cache_manager=CacheManager(InMemoryCacheBackend()))

        first = rag.build_context("hello", _context("scope-a"), "user@example.com")
        second = rag.build_context("hello", _context("scope-a"), "user@example.com")

        self.assertEqual(first.evidence[0].text, second.evidence[0].text)
        self.assertEqual(retriever.calls, 1)


def _context(scope_hash: str):
    return {
        "page_type": "Page",
        "fingerprint": "context-fingerprint",
        "permission": {"scope_hash": scope_hash},
        "filters": {},
    }


if __name__ == "__main__":
    unittest.main()
