from __future__ import annotations

import unittest

from reckon_copilot.insights.service import generate_insights
from reckon_copilot.permissions.boundary import CAPABILITY_RUN_ANALYTICS, PermissionDenied, StaticPermissionAdapter


class InsightServiceTests(unittest.TestCase):
    def test_list_context_returns_deterministic_findings(self):
        adapter = StaticPermissionAdapter(
            doctype_permissions={("Sales Order", "read"): True},
        )
        context = {
            "page_type": "List",
            "doctype": "Sales Order",
            "filters": {},
            "fingerprint": "abc123",
        }

        first = generate_insights(context, permission_adapter=adapter)
        second = generate_insights(context, permission_adapter=adapter)

        self.assertTrue(first["ok"])
        self.assertEqual(first["capability"], CAPABILITY_RUN_ANALYTICS)
        self.assertEqual(first["findings"], second["findings"])
        self.assertGreaterEqual(first["counts"]["warning"], 1)
        self.assertEqual(first["findings"][0]["source"], "context")

    def test_restricted_doctype_cannot_use_insights_as_side_channel(self):
        adapter = StaticPermissionAdapter()

        with self.assertRaises(PermissionDenied):
            generate_insights(
                {"page_type": "List", "doctype": "Salary Slip", "filters": {}},
                permission_adapter=adapter,
            )

    def test_report_context_uses_report_permission(self):
        adapter = StaticPermissionAdapter(reports={"Project Summary"})

        result = generate_insights(
            {
                "page_type": "Report",
                "report_name": "Project Summary",
                "filters": {"status": "Open"},
            },
            permission_adapter=adapter,
        )

        titles = [finding["title"] for finding in result["findings"]]
        self.assertIn("Report filters define the scope", titles)

    def test_evidence_findings_are_compact_and_source_filtered(self):
        adapter = StaticPermissionAdapter(
            doctype_permissions={("Sales Invoice", "read"): True},
        )
        result = generate_insights(
            {"page_type": "List", "doctype": "Sales Invoice", "filters": {"company": "Crystal Traders"}},
            evidence=[
                {
                    "chunk_id": "chunk-1",
                    "source_title": "Credit Manual",
                    "text": "Customer invoices are overdue and unpaid. " * 20,
                }
            ],
            permission_adapter=adapter,
        )

        knowledge = [finding for finding in result["findings"] if finding["source"] == "knowledge"]
        self.assertEqual(len(knowledge), 1)
        self.assertEqual(knowledge[0]["severity"], "warning")
        self.assertLessEqual(len(knowledge[0]["summary"]), 360)
        self.assertEqual(knowledge[0]["evidence_refs"], ["chunk-1"])

    def test_new_form_generates_draft_warning_with_create_permission(self):
        adapter = StaticPermissionAdapter(
            doctype_permissions={("Customer", "create"): True},
        )
        result = generate_insights(
            {
                "page_type": "Form",
                "doctype": "Customer",
                "document_name": "new-customer-uqqpmbuqwa",
            },
            permission_adapter=adapter,
        )

        self.assertTrue(any(finding["title"] == "Draft record is not saved" for finding in result["findings"]))


if __name__ == "__main__":
    unittest.main()
