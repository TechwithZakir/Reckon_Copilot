import unittest

from reckon_copilot.advisor.catalog import AdvisorCatalog, AdvisorTemplate, default_catalog
from reckon_copilot.api.advisor import _legacy_read_only_advice
from reckon_copilot.advisor.service import get_advice
from reckon_copilot.permissions.boundary import StaticPermissionAdapter


class AdvisorCatalogTests(unittest.TestCase):
    def test_rolling_deployment_fallback_is_read_only_and_panel_safe(self):
        result = _legacy_read_only_advice(
            {
                "page_type": "Form",
                "doctype": "Sales Order",
                "document_name": "SAL-ORD-2026-00001",
                "fingerprint": "safe-context",
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["advisor_version"], "v2-compat")
        self.assertTrue(result["compatibility_notice"])
        self.assertTrue(result["questions"])
        self.assertTrue(result["actions"])
        self.assertTrue(all(item["execution"] == "prompt" for item in result["questions"] + result["actions"]))

    def test_default_catalog_matches_real_doctype_and_available_fields(self):
        catalog = default_catalog()
        context = {"page_type": "List", "doctype": "Sales Order"}
        metadata = {"current_date": "2026-09-24", "field_names": ["status", "customer", "items"]}

        questions = catalog.questions_for(context, metadata)
        actions = catalog.actions_for(context, metadata)

        self.assertTrue(any(item["id"].endswith("unfulfilled") for item in questions))
        self.assertTrue(any(item["id"].endswith("follow_up") for item in actions))
        self.assertTrue(all(item["source"] == "catalog" for item in questions + actions))

    def test_catalog_does_not_suggest_missing_fields_or_other_doctypes(self):
        catalog = default_catalog()

        self.assertEqual(
            catalog.questions_for(
                {"page_type": "List", "doctype": "Sales Invoice"},
                {"field_names": ["customer", "status"]},
            ),
            [],
        )
        purchase_questions = catalog.questions_for(
            {"page_type": "List", "doctype": "Purchase Order"},
            {"field_names": ["status", "items"]},
        )
        self.assertTrue(any(item["title"] == "What remains to receive?" for item in purchase_questions))

    def test_unapproved_or_write_template_is_not_runtime_eligible(self):
        with self.assertRaises(ValueError):
            AdvisorTemplate(
                key="unsafe",
                title="Unsafe action",
                prompt_template="Do something",
                category="unsafe",
                page_type="Form",
                action_type="update",
                reason="Should never be active",
                intent_type="write_action",
            )

        catalog = AdvisorCatalog(
            [
                AdvisorTemplate(
                    key="disabled",
                    title="Disabled question",
                    prompt_template="Explain {label}",
                    category="help",
                    page_type="List",
                    action_type="question",
                    reason="Disabled",
                    enabled=False,
                )
            ]
        )
        self.assertEqual(catalog.questions_for({"page_type": "List"}, {}), [])

    def test_advisor_merges_catalog_after_context_authorization(self):
        result = get_advice(
            {"page_type": "List", "doctype": "Sales Order", "filters": {}},
            metadata={"current_date": "2026-09-24", "field_names": ["status", "items"]},
            permission_adapter=StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
            ),
        )

        self.assertTrue(any(item["source"] == "catalog" for item in result["questions"]))
        self.assertTrue(any(item["source"] == "catalog" for item in result["actions"]))
        self.assertTrue(all(item["source"] != "catalog" or item["intent_type"].startswith("read_only") for item in result["questions"] + result["actions"]))


if __name__ == "__main__":
    unittest.main()
