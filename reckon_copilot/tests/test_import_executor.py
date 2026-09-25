from __future__ import annotations

import json
import unittest
import zlib
from types import SimpleNamespace

from reckon_copilot.actions.approval import issue_approval_token
from reckon_copilot.actions.executor import InMemoryAuditStore
from reckon_copilot.imports.executor import (
    ImportExecutionError,
    execute_extracted_import_plan,
    execute_import_plan,
    record_extracted_import_approval,
    record_import_approval,
)
from reckon_copilot.imports.extraction import build_field_extraction_preview
from reckon_copilot.imports.mapping import build_extracted_import_plan, build_import_plan
from reckon_copilot.imports.preview import build_document_preview
from reckon_copilot.permissions.boundary import StaticPermissionAdapter


class _FakeDB:
    def __init__(self):
        self.rollback_count = 0

    def rollback(self):
        self.rollback_count += 1


class _FakeDoc:
    counter = 0

    def __init__(self):
        self.values = {}
        self.name = ""
        self.meta = SimpleNamespace(fields=[
            SimpleNamespace(fieldname="customer_name"),
            SimpleNamespace(fieldname="qty"),
        ])

    def set(self, key, value):
        self.values[key] = value

    def insert(self, ignore_permissions=False):
        type(self).counter += 1
        self.name = f"SO-IMPORT-{type(self).counter:05d}"


class _FakeFrappe:
    def __init__(self):
        self.db = _FakeDB()
        self.docs = []

    def get_meta(self, doctype):
        return SimpleNamespace(fields=[
            SimpleNamespace(fieldname="customer_name", label="Customer Name", fieldtype="Data", reqd=True, options=""),
            SimpleNamespace(fieldname="qty", label="Quantity", fieldtype="Int", reqd=True, options=""),
        ])

    def new_doc(self, doctype):
        doc = _FakeDoc()
        self.docs.append(doc)
        return doc


def _plan_and_payload():
    payload = json.dumps([
        {"Customer Name": "Crystal Traders", "Quantity": "2"},
        {"Customer Name": "Northwind", "Quantity": "3"},
    ]).encode()
    preview = build_document_preview("sales-orders.json", payload)
    plan = build_import_plan(
        preview,
        "Sales Order",
        [
            {"fieldname": "customer_name", "label": "Customer Name", "fieldtype": "Data", "reqd": True},
            {"fieldname": "qty", "label": "Quantity", "fieldtype": "Int", "reqd": True},
        ],
    )
    return plan, payload


def _adapter():
    return StaticPermissionAdapter(
        user="Administrator",
        roles={"System Manager"},
        doctype_permissions={("Sales Order", "create"): True},
    )


def _employee_adapter():
    return StaticPermissionAdapter(
        user="Employee",
        roles={"Employee"},
        doctype_permissions={("Sales Order", "create"): True},
    )


def _extracted_plan_and_payload():
    stream = zlib.compress(b"BT /F1 12 Tf (Customer: Crystal Traders) Tj ET")
    payload = (
        b"%PDF-1.7\n1 0 obj\n<< /Length "
        + str(len(stream)).encode()
        + b" /Filter /FlateDecode >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF"
    )
    preview = build_document_preview("invoice.pdf", payload, mime_type="application/pdf")
    preview.update(build_field_extraction_preview(preview))
    plan = build_extracted_import_plan(
        preview,
        "Sales Order",
        [
            {"fieldname": "customer_name", "label": "Customer Name", "fieldtype": "Data", "reqd": True},
            {"fieldname": "qty", "label": "Quantity", "fieldtype": "Int", "reqd": True},
        ],
        {"customer_name": "Crystal Traders", "qty": "1"},
    )
    return plan, payload


class ImportExecutorTests(unittest.TestCase):
    def test_import_requires_native_approval_record(self):
        plan, payload = _plan_and_payload()
        token = issue_approval_token(plan, user="Administrator", site="test.local")

        with self.assertRaisesRegex(ImportExecutionError, "Approve this import"):
            execute_import_plan(
                plan,
                token,
                file_name="sales-orders.json",
                content=payload,
                mime_type="application/json",
                frappe_module=_FakeFrappe(),
                user="Administrator",
                site="test.local",
                permission_adapter=_adapter(),
                audit_store=InMemoryAuditStore(),
            )

    def test_approved_import_is_idempotent(self):
        plan, payload = _plan_and_payload()
        token = issue_approval_token(plan, user="Administrator", site="test.local")
        store = InMemoryAuditStore()
        record_import_approval(plan, token, user="Administrator", site="test.local", audit_store=store)
        frappe = _FakeFrappe()

        first = execute_import_plan(
            plan,
            token,
            file_name="sales-orders.json",
            content=payload,
            mime_type="application/json",
            frappe_module=frappe,
            user="Administrator",
            site="test.local",
            permission_adapter=_adapter(),
            audit_store=store,
        )
        second = execute_import_plan(
            plan,
            token,
            file_name="sales-orders.json",
            content=payload,
            mime_type="application/json",
            frappe_module=frappe,
            user="Administrator",
            site="test.local",
            permission_adapter=_adapter(),
            audit_store=store,
        )

        self.assertEqual(first["created_count"], 2)
        self.assertTrue(second["idempotent"])
        self.assertEqual(len(frappe.docs), 2)

    def test_changed_attachment_is_rejected_before_insert(self):
        plan, payload = _plan_and_payload()
        token = issue_approval_token(plan, user="Administrator", site="test.local")
        store = InMemoryAuditStore()
        record_import_approval(plan, token, user="Administrator", site="test.local", audit_store=store)
        frappe = _FakeFrappe()

        with self.assertRaisesRegex(ImportExecutionError, "attachment or target fields changed"):
            execute_import_plan(
                plan,
                token,
                file_name="sales-orders.json",
                content=payload.replace(b"Northwind", b"Changed Customer"),
                mime_type="application/json",
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                permission_adapter=_adapter(),
                audit_store=store,
            )

        self.assertEqual(frappe.docs, [])
        self.assertEqual(store.records[plan["plan_hash"]]["status"], "failed")

    def test_reviewed_pdf_import_can_be_confirmed_by_native_user_permission(self):
        plan, payload = _extracted_plan_and_payload()
        token = issue_approval_token(plan, user="Employee", site="test.local")
        store = InMemoryAuditStore()
        record_extracted_import_approval(
            plan,
            token,
            user="Employee",
            site="test.local",
            audit_store=store,
        )
        frappe = _FakeFrappe()

        first = execute_extracted_import_plan(
            plan,
            token,
            file_name="invoice.pdf",
            content=payload,
            mime_type="application/pdf",
            frappe_module=frappe,
            user="Employee",
            site="test.local",
            permission_adapter=_employee_adapter(),
            audit_store=store,
        )
        second = execute_extracted_import_plan(
            plan,
            token,
            file_name="invoice.pdf",
            content=payload,
            mime_type="application/pdf",
            frappe_module=frappe,
            user="Employee",
            site="test.local",
            permission_adapter=_employee_adapter(),
            audit_store=store,
        )

        self.assertEqual(first["created_count"], 1)
        self.assertTrue(second["idempotent"])
        self.assertEqual(len(frappe.docs), 1)


if __name__ == "__main__":
    unittest.main()
