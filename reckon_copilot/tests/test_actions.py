import unittest

from reckon_copilot.actions.planner import plan_action
from reckon_copilot.permissions.boundary import PermissionDenied, StaticPermissionAdapter


class ActionPlannerTests(unittest.TestCase):
    def test_write_action_returns_preview_with_approval(self):
        result = plan_action(
            {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            "update",
            values={"customer": "Crystal Traders", "token": "hidden"},
            user="Administrator",
            permission_adapter=StaticPermissionAdapter(
                user="Administrator",
                roles={"System Manager"},
                document_permissions={("Sales Order", "SO-0001", "read"): True},
            ),
        )
        self.assertTrue(result["plan"]["requires_confirmation"])
        self.assertEqual(result["plan"]["execution"], "preview_only")
        self.assertNotIn("token", result["plan"]["values"])
        self.assertEqual(len(result["plan"]["plan_hash"]), 64)

    def test_high_risk_actions_are_marked(self):
        result = plan_action(
            {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            "submit",
            user="Administrator",
            permission_adapter=StaticPermissionAdapter(
                user="Administrator",
                roles={"System Manager"},
                document_permissions={("Sales Order", "SO-0001", "read"): True},
            ),
        )
        self.assertTrue(result["plan"]["high_risk"])

    def test_non_manager_cannot_plan_write_action(self):
        with self.assertRaises(PermissionDenied):
            plan_action(
                {"page_type": "List", "doctype": "Sales Order"},
                "delete",
                permission_adapter=StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True}),
            )


if __name__ == "__main__":
    unittest.main()
