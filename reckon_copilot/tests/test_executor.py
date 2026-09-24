from __future__ import annotations

import unittest
from types import SimpleNamespace

from reckon_copilot.actions.approval import issue_approval_token
from reckon_copilot.actions.executor import (
    ActionExecutionError,
    InMemoryAuditStore,
    execute_approved_plan,
)
from reckon_copilot.actions.planner import plan_action
from reckon_copilot.permissions.boundary import PermissionDenied, StaticPermissionAdapter


class _FakeDB:
    def __init__(self):
        self.rollback_count = 0

    def rollback(self):
        self.rollback_count += 1


class _FakeDoc:
    def __init__(self, name="SO-0001"):
        self.name = name
        self.values = {}
        self.meta = SimpleNamespace(
            fields=[SimpleNamespace(fieldname="customer"), SimpleNamespace(fieldname="status")]
        )
        self.saved = False
        self.deleted = False
        self.submitted = False

    def set(self, key, value):
        self.values[key] = value

    def save(self, ignore_permissions=False):
        self.saved = True

    def insert(self, ignore_permissions=False):
        self.name = self.name or "SO-NEW-0001"

    def delete(self, ignore_permissions=False):
        self.deleted = True

    def submit(self):
        self.submitted = True


class _FakeFrappe:
    def __init__(self):
        self.db = _FakeDB()
        self.document = _FakeDoc()
        self.session = SimpleNamespace(user="Administrator")

    def get_roles(self, user):
        return ["System Manager"]

    def has_permission(self, doctype, ptype="read", user=None, doc=None):
        return True

    def get_doc(self, doctype, name):
        return self.document

    def new_doc(self, doctype):
        self.document = _FakeDoc(name="NEW-SO")
        return self.document


def _approved_plan(action="update", values=None):
    plan = plan_action(
        {"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
        action,
        values=values or {"customer": "Crystal Traders"},
        user="Administrator",
        permission_adapter=StaticPermissionAdapter(
            user="Administrator",
            roles={"System Manager"},
            document_permissions={
                ("Sales Order", "SO-0001", "read"): True,
                ("Sales Order", "SO-0001", "write"): True,
                ("Sales Order", "SO-0001", "delete"): True,
                ("Sales Order", "SO-0001", "submit"): True,
            },
        ),
    )["plan"]
    token = issue_approval_token(plan, user="Administrator", site="test.local", secret="secret")
    return plan, token


class ActionExecutorTests(unittest.TestCase):
    def test_executes_approved_update_and_is_idempotent(self):
        plan, token = _approved_plan()
        frappe = _FakeFrappe()
        store = InMemoryAuditStore()
        adapter = StaticPermissionAdapter(
            user="Administrator",
            roles={"System Manager"},
            document_permissions={
                ("Sales Order", "SO-0001", "read"): True,
                ("Sales Order", "SO-0001", "write"): True,
            },
        )

        first = execute_approved_plan(
            plan,
            token,
            frappe_module=frappe,
            user="Administrator",
            site="test.local",
            secret="secret",
            current_context={"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            permission_adapter=adapter,
            audit_store=store,
        )
        second = execute_approved_plan(
            plan,
            token,
            frappe_module=frappe,
            user="Administrator",
            site="test.local",
            secret="secret",
            current_context={"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
            permission_adapter=adapter,
            audit_store=store,
        )

        self.assertTrue(first["ok"])
        self.assertTrue(frappe.document.saved)
        self.assertTrue(second["idempotent"])

    def test_changed_plan_is_rejected_before_mutation(self):
        plan, token = _approved_plan()
        plan["values"]["customer"] = "Changed after approval"
        frappe = _FakeFrappe()

        with self.assertRaises(ActionExecutionError):
            execute_approved_plan(
                plan,
                token,
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                secret="secret",
                current_context={"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
                audit_store=InMemoryAuditStore(),
            )

        self.assertFalse(frappe.document.saved)

    def test_approved_update_cannot_write_protected_field(self):
        plan, token = _approved_plan(values={"modified": "forbidden"})
        frappe = _FakeFrappe()

        with self.assertRaises(ActionExecutionError):
            execute_approved_plan(
                plan,
                token,
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                secret="secret",
                current_context={"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
                audit_store=InMemoryAuditStore(),
            )

        self.assertEqual(frappe.db.rollback_count, 1)
        self.assertFalse(frappe.document.saved)

    def test_navigation_to_another_document_is_rejected_before_mutation(self):
        plan, token = _approved_plan()
        frappe = _FakeFrappe()

        with self.assertRaisesRegex(ActionExecutionError, "Open that DocType and document"):
            execute_approved_plan(
                plan,
                token,
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                secret="secret",
                current_context={"page_type": "Form", "doctype": "Sales Invoice", "document_name": "SI-0001"},
                audit_store=InMemoryAuditStore(),
            )

        self.assertFalse(frappe.document.saved)
        self.assertEqual(frappe.db.rollback_count, 0)

    def test_permission_is_rechecked_immediately_before_mutation(self):
        plan, token = _approved_plan()
        frappe = _FakeFrappe()
        read_only_adapter = StaticPermissionAdapter(
            user="Administrator",
            roles={"System Manager"},
            document_permissions={("Sales Order", "SO-0001", "read"): True},
        )

        with self.assertRaises(PermissionDenied):
            execute_approved_plan(
                plan,
                token,
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                secret="secret",
                current_context={"page_type": "Form", "doctype": "Sales Order", "document_name": "SO-0001"},
                permission_adapter=read_only_adapter,
                audit_store=InMemoryAuditStore(),
            )

        self.assertFalse(frappe.document.saved)


if __name__ == "__main__":
    unittest.main()
