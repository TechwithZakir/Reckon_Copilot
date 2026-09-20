from __future__ import annotations

import unittest

from reckon_copilot.context.builders import (
    build_context,
    fingerprint_context,
    normalize_context_input,
)


class ContextNormalizationTests(unittest.TestCase):
    def test_form_context_is_sanitized_and_fingerprinted(self):
        context = build_context(
            route=["Form", "Sales Invoice", "SINV-00045"],
            filters={"html": "<main>ignored</main>"},
        )

        self.assertEqual(context["version"], "v1")
        self.assertEqual(context["page_type"], "Form")
        self.assertEqual(context["doctype"], "Sales Invoice")
        self.assertEqual(context["document_name"], "SINV-00045")
        self.assertNotIn("full_html", context)
        self.assertEqual(len(context["fingerprint"]), 64)

    def test_list_context_adapter(self):
        context = build_context(
            route=["List", "Material Request", "List"],
            filters={"status": "Pending"},
        )

        self.assertEqual(context["page_type"], "List")
        self.assertEqual(context["doctype"], "Material Request")
        self.assertEqual(context["view"], "List")
        self.assertEqual(context["filters"], {"status": "Pending"})

    def test_report_context_adapter(self):
        context = build_context(
            route=["Report", "Item Wise Consumption"],
            filters={"from_date": "2026-09-01", "to_date": "2026-09-30"},
        )

        self.assertEqual(context["page_type"], "Report")
        self.assertEqual(context["report_name"], "Item Wise Consumption")

    def test_dashboard_context_adapter(self):
        context = build_context(route=["Dashboard", "Buying"])

        self.assertEqual(context["page_type"], "Dashboard")
        self.assertEqual(context["dashboard_name"], "Buying")

    def test_workspace_context_adapter(self):
        context = build_context(route=["Workspace", "Buying"])

        self.assertEqual(context["page_type"], "Workspace")
        self.assertEqual(context["workspace_name"], "Buying")

    def test_unknown_route_falls_back_to_page_context(self):
        context = build_context(route=["buying"])

        self.assertEqual(context["page_type"], "Page")
        self.assertEqual(context["page_name"], "buying")

    def test_fingerprint_is_deterministic_and_changes_with_route(self):
        first = build_context(route=["List", "Item"])
        second = build_context(route=["List", "Item"])
        changed = build_context(route=["List", "Supplier"])

        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotEqual(first["fingerprint"], changed["fingerprint"])
        self.assertEqual(first["fingerprint"], fingerprint_context(first))

    def test_filter_order_does_not_change_fingerprint(self):
        first = build_context(route=["Report", "General Ledger"], filters={"b": 2, "a": 1})
        second = build_context(route=["Report", "General Ledger"], filters={"a": 1, "b": 2})

        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_route_and_filter_values_are_limited(self):
        normalized = normalize_context_input(
            route=["Form", "DocType", "x" * 300],
            filters={f"k{i}": i for i in range(30)},
        )

        self.assertLessEqual(len(normalized.route[2]), 163)
        self.assertEqual(len(normalized.filters), 20)


if __name__ == "__main__":
    unittest.main()
