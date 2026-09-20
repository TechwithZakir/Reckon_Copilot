from __future__ import annotations

import importlib
import unittest


class FoundationTests(unittest.TestCase):
    def test_app_package_imports(self):
        app = importlib.import_module("reckon_copilot")

        self.assertEqual(app.__version__, "0.0.1")

    def test_hooks_are_frappe_app_compatible(self):
        hooks = importlib.import_module("reckon_copilot.hooks")

        self.assertEqual(hooks.app_name, "reckon_copilot")
        self.assertEqual(hooks.app_title, "Reckon Copilot")
        self.assertIn("frappe", hooks.required_apps)
        self.assertIn("erpnext", hooks.required_apps)
        self.assertIsNone(hooks.after_install())
        self.assertIsNone(hooks.before_uninstall())

    def test_health_status_contract(self):
        health = importlib.import_module("reckon_copilot.api.health")

        payload = health.status()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["app"], "reckon_copilot")
        self.assertEqual(payload["version"], "0.0.1")
        self.assertEqual(payload["target"]["frappe"], "v16+")
        self.assertEqual(payload["target"]["erpnext"], "v16+")


class FakeProviderContractTests(unittest.TestCase):
    def test_fake_provider_satisfies_base_contract(self):
        from reckon_copilot.providers.base import (
            AIProvider,
            ProviderRequest,
            ProviderResponse,
        )

        class FakeProvider(AIProvider):
            provider_name = "fake"

            def complete(self, request: ProviderRequest) -> ProviderResponse:
                return ProviderResponse(
                    text=f"fake:{request.prompt}",
                    provider=self.provider_name,
                    model="fake-model",
                    metadata={"capability": request.capability},
                )

        provider = FakeProvider()
        request = ProviderRequest(prompt="ping")
        response = provider.complete(request)

        self.assertEqual(response.text, "fake:ping")
        self.assertEqual(response.provider, "fake")
        self.assertEqual(response.model, "fake-model")
        self.assertEqual(response.metadata["capability"], "health_check")


if __name__ == "__main__":
    unittest.main()

