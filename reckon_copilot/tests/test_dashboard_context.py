from __future__ import annotations

import unittest
from types import SimpleNamespace

from reckon_copilot.context.dashboard import build_dashboard_snapshot, enrich_dashboard_context


class FakeFrappe:
    def __init__(self):
        self.documents = {
            ("Dashboard", "Stock"): SimpleNamespace(
                name="Stock",
                charts=[SimpleNamespace(chart_name="Stock Value by Item Group")],
                cards=[SimpleNamespace(card="Total Stock Value")],
                content="",
            ),
            ("Dashboard Chart", "Stock Value by Item Group"): SimpleNamespace(
                name="Stock Value by Item Group",
                chart_name="Stock Value by Item Group",
                chart_type="Bar",
                document_type="Stock Ledger Entry",
                based_on="stock_value",
                group_by="item_group",
            ),
            ("Number Card", "Total Stock Value"): SimpleNamespace(
                name="Total Stock Value",
                label="Total Stock Value",
                type="Document Type",
                document_type="Stock Ledger Entry",
                function="Sum",
                aggregate_function_based_on="stock_value",
            ),
        }

    def has_permission(self, doctype, ptype=None, doc=None, user=None):
        return (doctype, doc) in self.documents or doctype in {"Dashboard", "Workspace"}

    def get_doc(self, doctype, name):
        return self.documents[(doctype, name)]


class WorkspaceDashboardFrappe(FakeFrappe):
    def __init__(self):
        super().__init__()
        self.documents.pop(("Dashboard", "Stock"))
        self.documents[("Workspace", "Stock")] = SimpleNamespace(
            name="Stock",
            charts=[SimpleNamespace(chart_name="Stock Value by Item Group")],
            number_cards=[SimpleNamespace(number_card_name="Total Stock Value")],
            content="",
        )


class DashboardContextTests(unittest.TestCase):
    def test_snapshot_contains_visible_chart_and_kpi_metadata(self):
        snapshot = build_dashboard_snapshot(
            {"page_type": "Dashboard", "dashboard_name": "Stock", "filters": {}},
            FakeFrappe(),
            user="Administrator",
        )

        self.assertEqual(snapshot["title"], "Stock")
        self.assertEqual(snapshot["source"], "Dashboard")
        self.assertEqual(snapshot["charts"][0]["title"], "Stock Value by Item Group")
        self.assertEqual(snapshot["number_cards"][0]["title"], "Total Stock Value")
        self.assertIn("KPI card", snapshot["summary"])

    def test_enrichment_recomputes_fingerprint(self):
        context = {
            "page_type": "Dashboard",
            "dashboard_name": "Stock",
            "filters": {},
            "fingerprint": "old",
        }

        enriched = enrich_dashboard_context(context, FakeFrappe(), user="Administrator")

        self.assertIn("dashboard_snapshot", enriched)
        self.assertNotEqual(enriched["fingerprint"], "old")
        self.assertEqual(len(enriched["fingerprint"]), 64)

    def test_restricted_linked_chart_is_omitted(self):
        frappe = FakeFrappe()
        original = frappe.has_permission
        frappe.has_permission = lambda doctype, ptype=None, doc=None, user=None: not (
            doctype == "Dashboard Chart"
        )

        snapshot = build_dashboard_snapshot(
            {"page_type": "Dashboard", "dashboard_name": "Stock", "filters": {}},
            frappe,
            user="limited@example.com",
        )

        self.assertEqual(snapshot["charts"], [])
        frappe.has_permission = original

    def test_snapshot_supports_workspace_backed_dashboard(self):
        snapshot = build_dashboard_snapshot(
            {"page_type": "Dashboard", "dashboard_name": "Stock", "filters": {}},
            WorkspaceDashboardFrappe(),
            user="Administrator",
        )

        self.assertEqual(snapshot["source"], "Workspace")
        self.assertEqual(snapshot["charts"][0]["title"], "Stock Value by Item Group")


if __name__ == "__main__":
    unittest.main()
