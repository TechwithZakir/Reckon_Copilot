import unittest

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

    def test_restricted_context_cannot_receive_advice(self):
        with self.assertRaises(PermissionDenied):
            get_advice({"page_type": "List", "doctype": "Salary Slip"}, permission_adapter=StaticPermissionAdapter())


if __name__ == "__main__":
    unittest.main()
