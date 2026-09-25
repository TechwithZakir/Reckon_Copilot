from __future__ import annotations

import json
import unittest

from reckon_copilot.imports.preview import ImportPreviewError, build_document_preview


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


if __name__ == "__main__":
    unittest.main()
