from __future__ import annotations

import unittest

from reckon_copilot.context.builders import (
    build_context,
    fingerprint_context,
    humanize_slug,
    normalize_context_input,
    promote_workspace_slug_to_doctype,
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

    def test_report_context_preserves_meaningful_hyphens(self):
        context = build_context(
            route=["Report", "Sales Person-wise Transaction Summary"],
            filters={"doc_type": "Sales Order"},
        )

        self.assertEqual(context["page_type"], "Report")
        self.assertEqual(context["report_name"], "Sales Person-wise Transaction Summary")

    def test_single_part_report_hint_preserves_hyphenated_report_name(self):
        context = build_context(route=["Item-wise Sales Register"], page_type="Report")

        self.assertEqual(context["page_type"], "Report")
        self.assertEqual(context["report_name"], "Item-wise Sales Register")

    def test_dashboard_context_adapter(self):
        context = build_context(route=["Dashboard", "Buying"])

        self.assertEqual(context["page_type"], "Dashboard")
        self.assertEqual(context["dashboard_name"], "Buying")

    def test_dashboard_context_accepts_frappe_json_string_args(self):
        context = build_context(
            route='["Dashboard","Selling"]',
            filters="{}",
            page_type="Dashboard",
        )

        self.assertEqual(context["page_type"], "Dashboard")
        self.assertEqual(context["dashboard_name"], "Selling")

    def test_workspace_context_adapter(self):
        context = build_context(route=["Workspace", "Buying"])

        self.assertEqual(context["page_type"], "Workspace")
        self.assertEqual(context["workspace_name"], "Buying")

    def test_workspace_slug_promotes_to_tree_doctype_when_exact_doctype_exists(self):
        context = build_context(route=["Workspace", "Customer Group"])

        promoted = promote_workspace_slug_to_doctype(
            context,
            workspace_exists=lambda name: True,
            doctype_exists=lambda name: name == "Customer Group",
            is_tree_doctype=lambda name: True,
        )

        self.assertEqual(promoted["page_type"], "List")
        self.assertEqual(promoted["doctype"], "Customer Group")
        self.assertEqual(promoted["view"], "Tree")
        self.assertNotIn("workspace_name", promoted)

    def test_workspace_stays_workspace_when_no_exact_doctype_exists(self):
        context = build_context(route=["Workspace", "Projects"])

        promoted = promote_workspace_slug_to_doctype(
            context,
            workspace_exists=lambda name: True,
            doctype_exists=lambda name: False,
            is_tree_doctype=lambda name: True,
        )

        self.assertEqual(promoted["page_type"], "Workspace")
        self.assertEqual(promoted["workspace_name"], "Projects")

    def test_item_group_workspace_slug_promotes_to_tree_doctype(self):
        context = build_context(route=["Workspace", "Item Group"])

        promoted = promote_workspace_slug_to_doctype(
            context,
            workspace_exists=lambda name: True,
            doctype_exists=lambda name: name == "Item Group",
            is_tree_doctype=lambda name: True,
        )

        self.assertEqual(promoted["page_type"], "List")
        self.assertEqual(promoted["doctype"], "Item Group")
        self.assertEqual(promoted["view"], "Tree")

    def test_unknown_route_falls_back_to_page_context(self):
        context = build_context(route=["buying"])

        self.assertEqual(context["page_type"], "Page")
        self.assertEqual(context["page_name"], "buying")

    def test_page_type_hint_normalizes_single_slug_list_routes(self):
        context = build_context(route=["delivery-note"], page_type="List")

        self.assertEqual(context["page_type"], "List")
        self.assertEqual(context["doctype"], "Delivery Note")
        self.assertEqual(context["route"], ["delivery-note"])

    def test_invalid_page_type_hint_is_ignored(self):
        context = build_context(route=["delivery-note"], page_type="Unsafe")

        self.assertEqual(context["page_type"], "Page")

    def test_slug_humanization_handles_frappe_route_names(self):
        self.assertEqual(humanize_slug("item-wise-consumption"), "Item Wise Consumption")

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
