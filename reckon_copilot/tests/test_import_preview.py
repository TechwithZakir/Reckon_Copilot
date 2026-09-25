from __future__ import annotations

import json
import unittest

from reckon_copilot.imports.preview import ImportPreviewError, build_document_preview
from reckon_copilot.imports.mapping import build_import_plan


class ImportPreviewTests(unittest.TestCase):
    def test_json_preview_is_compact_and_write_free(self):
        preview = build_document_preview(
            "sales-invoice.json",
            json.dumps({"customer": "Crystal Traders", "grand_total": 1250, "secret": "do not expose"}).encode(),
            target_fields={"customer", "grand_total"},
        )

        self.assertEqual(preview["format"], "json")
        self.assertEqual(preview["record_count"], 1)
        self.assertFalse(preview["write_required"])
        self.assertFalse(preview["model_training"])
        self.assertIn("secret", preview["unknown_fields"])
        self.assertEqual(preview["records"][0]["customer"], "Crystal Traders")

    def test_csv_preview_is_bounded_and_reports_unknown_fields(self):
        preview = build_document_preview(
            "orders.csv",
            b"customer,amount,unexpected\nCrystal Traders,1250,x\n",
            target_fields={"customer", "amount"},
        )

        self.assertEqual(preview["format"], "csv")
        self.assertEqual(preview["fields"], ["customer", "amount", "unexpected"])
        self.assertEqual(preview["unknown_fields"], ["unexpected"])
        self.assertTrue(any("not available" in warning for warning in preview["warnings"]))

    def test_unsupported_document_is_rejected_without_fallback_write(self):
        with self.assertRaisesRegex(ImportPreviewError, "supports CSV"):
            build_document_preview("invoice.pdf", b"%PDF-1.7")

    def test_empty_or_oversized_document_is_rejected(self):
        with self.assertRaises(ImportPreviewError):
            build_document_preview("empty.txt", b"")
        with self.assertRaisesRegex(ImportPreviewError, "4 MB"):
            build_document_preview("large.txt", b"x" * (4 * 1024 * 1024 + 1))

    def test_import_plan_maps_labels_and_stays_preview_only(self):
        preview = build_document_preview(
            "orders.json",
            json.dumps([
                {"Customer Name": "Crystal Traders", "qty": "2", "status": "Draft"},
                {"Customer Name": "Northwind", "qty": "3", "status": "Draft"},
            ]).encode(),
        )
        plan = build_import_plan(
            preview,
            "Sales Order",
            [
                {"fieldname": "customer_name", "label": "Customer Name", "fieldtype": "Data", "reqd": True},
                {"fieldname": "qty", "label": "Quantity", "fieldtype": "Int", "reqd": True},
                {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Draft\nSubmitted"},
            ],
        )

        self.assertTrue(plan["ready_for_approval"])
        self.assertTrue(plan["write_required"])
        self.assertTrue(plan["requires_approval"])
        self.assertFalse(plan["model_training"])
        self.assertEqual(plan["row_count"], 2)
        self.assertEqual(plan["error_count"], 0)
        self.assertEqual(len(plan["plan_hash"]), 64)

    def test_import_plan_reports_type_and_required_field_errors(self):
        preview = build_document_preview(
            "orders.csv",
            b"customer_name,qty\nCrystal Traders,not-a-number\n",
        )
        plan = build_import_plan(
            preview,
            "Sales Order",
            [
                {"fieldname": "customer_name", "label": "Customer", "fieldtype": "Data", "reqd": True},
                {"fieldname": "qty", "label": "Quantity", "fieldtype": "Int", "reqd": True},
                {"fieldname": "company", "label": "Company", "fieldtype": "Data", "reqd": True},
            ],
        )

        self.assertFalse(plan["ready_for_approval"])
        self.assertGreater(plan["error_count"], 0)
        self.assertTrue(any("whole number" in message for item in plan["errors"] for message in item["messages"]))
        self.assertTrue(any("Missing required fields" in message for item in plan["errors"] for message in item["messages"]))


if __name__ == "__main__":
    unittest.main()
