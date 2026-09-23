from __future__ import annotations

import unittest
from unittest.mock import patch

from reckon_copilot.api.notifications import get_notifications
from reckon_copilot.notifications.service import generate_notifications
from reckon_copilot.permissions.boundary import PermissionDenied, StaticPermissionAdapter


class NotificationServiceTests(unittest.TestCase):
    def test_disabled_notifications_return_empty_payload(self):
        result = generate_notifications(
            {"page_type": "List", "doctype": "Sales Order", "filters": {}},
            permission_adapter=StaticPermissionAdapter(),
            enabled=False,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["enabled"])
        self.assertEqual(result["notifications"], [])

    def test_notifications_are_derived_from_warning_insights(self):
        adapter = StaticPermissionAdapter(
            doctype_permissions={("Sales Order", "read"): True},
        )
        result = generate_notifications(
            {"page_type": "List", "doctype": "Sales Order", "filters": {}},
            permission_adapter=adapter,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["warning"], 1)
        self.assertEqual(result["notifications"][0]["level"], "warning")
        self.assertEqual(result["notifications"][0]["action_prompt"], "Which filters may help?")

    def test_restricted_doctype_cannot_emit_side_channel_notification(self):
        with self.assertRaises(PermissionDenied):
            generate_notifications(
                {"page_type": "List", "doctype": "Salary Slip", "filters": {}},
                permission_adapter=StaticPermissionAdapter(),
            )

    def test_api_converts_permission_denial_to_panel_payload(self):
        with patch(
            "reckon_copilot.api.notifications.generate_notifications",
            side_effect=PermissionDenied("No access to requested report"),
        ):
            result = get_notifications(
                context={
                    "page_type": "Report",
                    "report_name": "Restricted Report",
                    "filters": {},
                },
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["access_denied"])
        self.assertEqual(result["notifications"][0]["source"], "permission")
        self.assertEqual(result["notifications"][0]["message"], "No access to requested report")

    def test_evidence_risk_becomes_notification_without_full_document(self):
        adapter = StaticPermissionAdapter(
            doctype_permissions={("Sales Invoice", "read"): True},
        )
        result = generate_notifications(
            {"page_type": "List", "doctype": "Sales Invoice", "filters": {"company": "Crystal Traders"}},
            evidence=[
                {
                    "chunk_id": "chunk-1",
                    "source_title": "Credit Manual",
                    "text": "Critical exception: overdue unpaid invoice risk. " * 20,
                }
            ],
            permission_adapter=adapter,
        )

        self.assertEqual(result["notifications"][0]["level"], "critical")
        self.assertLessEqual(len(result["notifications"][0]["message"]), 260)


if __name__ == "__main__":
    unittest.main()
