from __future__ import annotations

import json
import io
import unittest
import zipfile
import zlib

from reckon_copilot.imports.preview import ImportPreviewError, build_document_preview
from reckon_copilot.imports.mapping import build_extracted_import_plan, build_import_plan
from reckon_copilot.imports.extraction import build_field_extraction_preview


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
        with self.assertRaisesRegex(ImportPreviewError, "no readable text"):
            build_document_preview("invoice.pdf", b"%PDF-1.7")

    def test_pdf_preview_extracts_bounded_text_without_structured_rows(self):
        stream = zlib.compress(b"BT /F1 12 Tf (Invoice total: 1250) Tj ET")
        payload = (
            b"%PDF-1.7\n1 0 obj\n<< /Length "
            + str(len(stream)).encode()
            + b" /Filter /FlateDecode >>\nstream\n"
            + stream
            + b"\nendstream\nendobj\n%%EOF"
        )

        preview = build_document_preview("invoice.pdf", payload, mime_type="application/pdf")

        self.assertEqual(preview["format"], "pdf")
        self.assertEqual(preview["record_count"], 0)
        self.assertFalse(preview["structured"])
        self.assertIn("Invoice total: 1250", preview["text_excerpt"])
        self.assertTrue(any("structured import mapping" in warning for warning in preview["warnings"]))

    def test_docx_preview_extracts_document_body_without_reading_embedded_files(self):
        document_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body><w:p><w:r><w:t>Invoice total: </w:t></w:r><w:r><w:t>1250</w:t></w:r></w:p>'
            b'<w:p><w:r><w:t>Approval required.</w:t></w:r></w:p></w:body></w:document>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", document_xml)
            archive.writestr("word/media/ignored.bin", b"should not be read")

        preview = build_document_preview(
            "invoice.docx",
            buffer.getvalue(),
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        self.assertEqual(preview["format"], "docx")
        self.assertFalse(preview["structured"])
        self.assertEqual(preview["record_count"], 0)
        self.assertIn("Invoice total: 1250", preview["text_excerpt"])
        self.assertIn("Approval required.", preview["text_excerpt"])

    def test_text_extraction_cannot_be_promoted_to_an_import_plan(self):
        preview = build_document_preview("manual.pdf", b"%PDF-1.7\n1 0 obj\nstream\nBT (Read only) Tj ET\nendstream")

        with self.assertRaisesRegex(ValueError, "structured import mapping"):
            build_import_plan(preview, "Sales Order", [{"fieldname": "customer", "fieldtype": "Data"}])

    def test_labeled_invoice_values_map_only_to_installed_target_fields(self):
        extraction = build_field_extraction_preview(
            {
                "text_excerpt": (
                    "Invoice Number: INV-2026-0042 Invoice Date: 24-09-2026 "
                    "Customer: Crystal Traders Grand Total: BDT 1,250.00 "
                    "Unlabelled secret value"
                )
            },
            target_fields={"bill_no", "posting_date", "customer", "grand_total", "company"},
        )

        values = {item["fieldname"]: item["value"] for item in extraction["extracted_fields"]}
        self.assertEqual(values["bill_no"], "INV-2026-0042")
        self.assertEqual(values["posting_date"], "2026-09-24")
        self.assertEqual(values["customer"], "Crystal Traders")
        self.assertEqual(values["grand_total"], "1250.00")
        self.assertNotIn("secret", extraction["extracted_record"])
        self.assertFalse(extraction["write_required"])
        self.assertTrue(extraction["requires_approval"])
        self.assertFalse(extraction["model_training"])

    def test_extraction_reports_when_no_target_field_matches(self):
        extraction = build_field_extraction_preview(
            {"text_excerpt": "Invoice Number: INV-2026-0042"},
            target_fields={"description"},
        )

        self.assertEqual(extraction["extracted_fields"], [])
        self.assertTrue(any("selected DocType" in warning for warning in extraction["extraction_warnings"]))

    def test_extracted_review_plan_validates_values_but_cannot_be_approved(self):
        plan = build_extracted_import_plan(
            {
                "structured": False,
                "preview_id": "a" * 64,
                "file_name": "invoice.pdf",
                "format": "pdf",
                "extraction_method": "deterministic_label_match",
            },
            "Purchase Invoice",
            [
                {"fieldname": "bill_no", "label": "Bill No", "fieldtype": "Data", "reqd": True},
                {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date", "reqd": True},
                {"fieldname": "grand_total", "label": "Grand Total", "fieldtype": "Currency", "reqd": True},
            ],
            {"bill_no": "PINV-0042", "posting_date": "2026-09-24", "grand_total": "1250.00"},
        )

        self.assertEqual(plan["version"], "v1-extracted-review")
        self.assertEqual(plan["execution"], "review_only")
        self.assertFalse(plan["ready_for_approval"])
        self.assertEqual(plan["row_count"], 1)
        self.assertEqual(plan["error_count"], 0)
        self.assertEqual(len(plan["plan_hash"]), 64)

    def test_extracted_review_plan_rejects_fields_outside_target_schema(self):
        with self.assertRaisesRegex(ValueError, "not available"):
            build_extracted_import_plan(
                {"structured": False, "preview_id": "b" * 64, "file_name": "invoice.docx", "format": "docx"},
                "Purchase Invoice",
                [{"fieldname": "bill_no", "fieldtype": "Data"}],
                {"grand_total": "1250.00"},
            )

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
