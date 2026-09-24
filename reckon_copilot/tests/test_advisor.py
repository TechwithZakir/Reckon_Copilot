import unittest

from reckon_copilot.permissions.boundary import CopilotPermissionBoundary
from reckon_copilot.advisor.service import get_advice
from reckon_copilot.permissions.boundary import PermissionDenied, StaticPermissionAdapter


class AdvisorTests(unittest.TestCase):
    def test_sales_order_list_advice_is_contextual(self):
        result = get_advice(
            {"page_type": "List", "doctype": "Sales Order", "filters": {}},
            permission_adapter=StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
                document_permissions={("Sales Order", "SO-0001", "read"): True},
            ),
        )
        self.assertTrue(any("attention" in item["title"] for item in result["questions"]))
        self.assertTrue(result["actions"])

    def test_form_advice_includes_workflow_question(self):
        result = get_advice(
            {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            permission_adapter=StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
                document_permissions={("Sales Order", "SO-0001", "read"): True},
            ),
        )
        self.assertTrue(any(item["action_type"] == "workflow" for item in result["questions"]))

    def test_form_advice_uses_doctype_metadata_and_native_write_permission(self):
        result = get_advice(
            {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            user="Administrator",
            metadata={
                "required_fields": ["Customer", "Transaction Date"],
                "has_workflow_state": True,
                "is_submittable": True,
            },
            permission_adapter=StaticPermissionAdapter(
                user="Administrator",
                roles={"System Manager"},
                doctype_permissions={("Sales Order", "read"): True},
                document_permissions={
                    ("Sales Order", "SO-0001", "read"): True,
                    ("Sales Order", "SO-0001", "write"): True,
                    ("Sales Order", "SO-0001", "submit"): True,
                },
            ),
        )
        self.assertTrue(any(item["category"] == "completion-check" for item in result["questions"]))
        self.assertTrue(any(item.get("action_type") == "update" for item in result["actions"]))
        self.assertTrue(any(item.get("action_type") == "submit" for item in result["actions"]))
        self.assertEqual(result["signals"]["metadata"]["required_fields"], ["Customer", "Transaction Date"])

    def test_form_advice_hides_write_actions_without_native_permission(self):
        result = get_advice(
            {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            user="Administrator",
            metadata={"is_submittable": True},
            permission_adapter=StaticPermissionAdapter(
                user="Administrator",
                roles={"System Manager"},
                doctype_permissions={("Sales Order", "read"): True},
                document_permissions={("Sales Order", "SO-0001", "read"): True},
            ),
        )
        self.assertFalse(any(item.get("action_type") in {"create", "update", "submit", "delete", "approve"} for item in result["actions"]))

    def test_advisor_fails_closed_when_action_gate_is_temporarily_unavailable(self):
        original = CopilotPermissionBoundary.authorize_action
        try:
            delattr(CopilotPermissionBoundary, "authorize_action")
            result = get_advice(
                {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
                user="Administrator",
                permission_adapter=StaticPermissionAdapter(
                    user="Administrator",
                    roles={"System Manager"},
                    doctype_permissions={("Sales Order", "read"): True},
                    document_permissions={("Sales Order", "SO-0001", "read"): True},
                ),
            )
        finally:
            setattr(CopilotPermissionBoundary, "authorize_action", original)
        self.assertFalse(any(item.get("action_type") in {"create", "update", "submit", "delete", "approve"} for item in result["actions"]))

    def test_list_advice_explains_status_filter(self):
        result = get_advice(
            {"page_type": "List", "doctype": "Sales Order", "filters": {"status": "Draft"}},
            permission_adapter=StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
            ),
        )
        self.assertTrue(any(item["priority"] == "high" and item["source"] == "filter" for item in result["questions"]))
        self.assertEqual(result["signals"]["filter_count"], 1)

    def test_sales_order_advisor_returns_end_user_helpline_metadata(self):
        result = get_advice(
            {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            user="Administrator",
            metadata={
                "field_names": ["customer", "delivery_date", "items", "taxes"],
                "required_fields": ["Customer", "Transaction Date"],
                "has_workflow_state": True,
                "is_submittable": True,
            },
            permission_adapter=StaticPermissionAdapter(
                user="Administrator",
                roles={"System Manager"},
                doctype_permissions={("Sales Order", "read"): True},
                document_permissions={
                    ("Sales Order", "SO-0001", "read"): True,
                    ("Sales Order", "SO-0001", "write"): True,
                    ("Sales Order", "SO-0001", "submit"): True,
                },
            ),
        )
        self.assertEqual(result["advisor_version"], "v2")
        self.assertEqual(result["page_family"], "sales")
        self.assertIn("readiness", result["page_summary"])
        recommendation = next(item for item in result["questions"] if item["category"] == "sales-readiness")
        self.assertTrue(recommendation["reason"])
        self.assertEqual(recommendation["source_label"], "DocType structure")
        self.assertEqual(recommendation["action_type"], "workflow")
        self.assertIn(recommendation["priority"], {"high", "normal", "low"})

    def test_report_without_filters_recommends_scope_first(self):
        result = get_advice(
            {"page_type": "Report", "report_name": "Sales Person-wise Transaction Summary", "filters": {}},
            metadata={"ref_doctype": "Sales Order", "report_type": "Script Report"},
            permission_adapter=StaticPermissionAdapter(reports={"Sales Person-wise Transaction Summary"}),
        )
        self.assertEqual(result["page_family"], "sales")
        scope_question = next(item for item in result["questions"] if item["category"] == "report-scope")
        self.assertEqual(scope_question["action_type"], "filter")
        self.assertEqual(scope_question["priority"], "high")

    def test_dashboard_advice_names_real_visible_components(self):
        result = get_advice(
            {"page_type": "Dashboard", "dashboard_name": "Stock", "filters": {}},
            metadata={
                "chart_count": 1,
                "number_card_count": 2,
                "chart_titles": ["Stock Value by Item Group"],
                "number_card_titles": ["Total Warehouses", "Total Stock Value"],
                "dashboard_snapshot": {
                    "summary": "Stock dashboard contains 2 KPI card(s) and 1 chart(s).",
                },
            },
            permission_adapter=StaticPermissionAdapter(dashboards={"Stock"}),
        )

        self.assertIn("2 KPI card(s)", result["page_summary"])
        self.assertTrue(any("Stock Value by Item Group" in item["title"] for item in result["questions"]))
        self.assertTrue(any(item["category"] == "dashboard-summary" for item in result["questions"]))

    def test_homepage_advice_is_date_aware_and_actionable(self):
        result = get_advice(
            {"page_type": "Homepage", "homepage_name": "Home", "filters": {}},
            metadata={
                "current_date": "2026-09-24",
                "briefing_scope": "user and company home context",
            },
            permission_adapter=StaticPermissionAdapter(),
        )

        self.assertIn("2026-09-24", result["page_summary"])
        self.assertTrue(any(item["category"] == "daily-briefing" for item in result["questions"]))
        self.assertIn("2026-09-24", result["questions"][0]["prompt"])

    def test_restricted_context_cannot_receive_advice(self):
        with self.assertRaises(PermissionDenied):
            get_advice({"page_type": "List", "doctype": "Salary Slip"}, permission_adapter=StaticPermissionAdapter())


if __name__ == "__main__":
    unittest.main()
