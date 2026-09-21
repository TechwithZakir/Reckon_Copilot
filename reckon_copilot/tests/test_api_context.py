from __future__ import annotations

import unittest
from unittest.mock import patch

from reckon_copilot.api.context import get_context
from reckon_copilot.permissions import PermissionDenied


class ContextApiTests(unittest.TestCase):
    def test_permission_denied_returns_panel_alert_payload(self):
        with patch(
            "reckon_copilot.api.context.authorize_context",
            side_effect=PermissionDenied("No access to requested workspace"),
        ):
            context = get_context(route=["Workspace", "Restricted"], filters={}, page_type="Workspace")

        self.assertTrue(context["access_denied"])
        self.assertEqual(context["page_type"], "Workspace")
        self.assertEqual(context["workspace_name"], "Restricted")
        self.assertEqual(context["permission"]["allowed"], False)
        self.assertEqual(context["permission"]["reason"], "No access to requested workspace")
        self.assertEqual(len(context["fingerprint"]), 64)

    def test_permission_error_returns_panel_alert_payload(self):
        with patch(
            "reckon_copilot.api.context.authorize_context",
            side_effect=PermissionError("No access to requested report"),
        ):
            context = get_context(
                route=["Report", "Item-wise Sales Register"],
                filters={"company": "Crystal Traders"},
                page_type="Report",
            )

        self.assertTrue(context["access_denied"])
        self.assertEqual(context["page_type"], "Report")
        self.assertEqual(context["report_name"], "Item-wise Sales Register")
        self.assertEqual(context["permission"]["reason"], "No access to requested report")


if __name__ == "__main__":
    unittest.main()
