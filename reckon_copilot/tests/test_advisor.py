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
        self.assertTrue(any(item["title"] == "What happens next?" for item in result["questions"]))

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
        self.assertTrue(any(item["title"] == "What is still required?" for item in result["questions"]))
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
        self.assertFalse(any(item.get("action_type") for item in result["actions"]))

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
        self.assertFalse(any(item.get("action_type") for item in result["actions"]))

    def test_list_advice_explains_status_filter(self):
        result = get_advice(
            {"page_type": "List", "doctype": "Sales Order", "filters": {"status": "Draft"}},
            permission_adapter=StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
            ),
        )
        self.assertTrue(any(item["title"] == "Review this status slice" for item in result["questions"]))
        self.assertEqual(result["signals"]["filter_count"], 1)

    def test_restricted_context_cannot_receive_advice(self):
        with self.assertRaises(PermissionDenied):
            get_advice({"page_type": "List", "doctype": "Salary Slip"}, permission_adapter=StaticPermissionAdapter())


if __name__ == "__main__":
    unittest.main()
