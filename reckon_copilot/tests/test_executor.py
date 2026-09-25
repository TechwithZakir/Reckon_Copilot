from __future__ import annotations

import unittest
from types import SimpleNamespace

from reckon_copilot.actions.executor import (
    ActionExecutionError,
    InMemoryAuditStore,
    execute_confirmed_plan,
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


def _plan(action="update", values=None):
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
    return plan


class ActionExecutorTests(unittest.TestCase):
    def test_execution_requires_user_confirmation(self):
        plan = _plan()
        frappe = _FakeFrappe()
        store = InMemoryAuditStore()

        result = execute_confirmed_plan(
            plan,
            frappe_module=frappe,
            user="Administrator",
            site="test.local",
            audit_store=store,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(frappe.document.saved)
        self.assertEqual(store.records[plan["plan_hash"]]["approved_by"], "Administrator")

    def test_confirmed_update_is_idempotent(self):
        plan = _plan()
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

        first = execute_confirmed_plan(
            plan,
            frappe_module=frappe,
            user="Administrator",
            site="test.local",
            permission_adapter=adapter,
            audit_store=store,
        )
        second = execute_confirmed_plan(
            plan,
            frappe_module=frappe,
            user="Administrator",
            site="test.local",
            permission_adapter=adapter,
            audit_store=store,
        )

        self.assertTrue(first["ok"])
        self.assertTrue(frappe.document.saved)
        self.assertTrue(second["idempotent"])

    def test_changed_plan_is_rejected_before_mutation(self):
        plan = _plan()
        plan["values"]["customer"] = "Changed after approval"
        frappe = _FakeFrappe()

        with self.assertRaises(ActionExecutionError):
            execute_confirmed_plan(
                plan,
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                audit_store=InMemoryAuditStore(),
            )

        self.assertFalse(frappe.document.saved)

    def test_approved_update_cannot_write_protected_field(self):
        plan = _plan(values={"modified": "forbidden"})
        frappe = _FakeFrappe()

        with self.assertRaises(ActionExecutionError):
            execute_confirmed_plan(
                plan,
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                audit_store=InMemoryAuditStore(),
            )

        self.assertEqual(frappe.db.rollback_count, 1)
        self.assertFalse(frappe.document.saved)

    def test_permission_is_rechecked_immediately_before_mutation(self):
        plan = _plan()
        frappe = _FakeFrappe()
        read_only_adapter = StaticPermissionAdapter(
            user="Administrator",
            roles={"System Manager"},
            document_permissions={("Sales Order", "SO-0001", "read"): True},
        )

        with self.assertRaises(PermissionDenied):
            execute_confirmed_plan(
                plan,
                frappe_module=frappe,
                user="Administrator",
                site="test.local",
                permission_adapter=read_only_adapter,
                audit_store=InMemoryAuditStore(),
            )

        self.assertFalse(frappe.document.saved)


if __name__ == "__main__":
    unittest.main()
