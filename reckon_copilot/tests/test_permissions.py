from __future__ import annotations

import unittest

from reckon_copilot.permissions.boundary import (
    CAPABILITY_CALL_PROVIDER,
    CAPABILITY_READ_CONTEXT,
    CAPABILITY_WRITE_ACTION,
    CopilotPermissionBoundary,
    PermissionDenied,
    StaticPermissionAdapter,
)


class PermissionBoundaryTests(unittest.TestCase):
    def test_role_permission_allows_doctype_list_context(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
            )
        )

        authorized = boundary.authorize(
            {
                "page_type": "List",
                "doctype": "Sales Order",
                "filters": {},
            }
        )

        self.assertTrue(authorized.decision.allowed)
        self.assertEqual(authorized.context["permission"]["mode"], "frappe_boundary")

    def test_role_permission_blocks_restricted_doctype(self):
        boundary = CopilotPermissionBoundary(StaticPermissionAdapter())

        with self.assertRaises(PermissionDenied):
            boundary.authorize({"page_type": "List", "doctype": "Salary Slip"})

    def test_document_permission_blocks_restricted_form_record(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
                document_permissions={
                    ("Sales Order", "SO-PRIVATE", "read"): False,
                },
            )
        )

        with self.assertRaises(PermissionDenied):
            boundary.authorize(
                {
                    "page_type": "Form",
                    "doctype": "Sales Order",
                    "document_name": "SO-PRIVATE",
                }
            )

    def test_new_unsaved_form_uses_doctype_create_permission(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Customer", "create"): True},
                document_permissions={
                    ("Customer", "new-customer-uqqpmbuqwa", "read"): False,
                },
            )
        )

        authorized = boundary.authorize(
            {
                "page_type": "Form",
                "doctype": "Customer",
                "document_name": "new-customer-uqqpmbuqwa",
            }
        )

        self.assertEqual(authorized.context["doctype"], "Customer")

    def test_user_permission_blocks_company_scope(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Sales Invoice", "read"): True},
                allowed_companies={"Crystal Traders"},
            )
        )

        with self.assertRaises(PermissionDenied):
            boundary.authorize(
                {
                    "page_type": "List",
                    "doctype": "Sales Invoice",
                    "filters": {"company": "Blocked Company"},
                }
            )

    def test_user_permission_allows_company_scope(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Sales Invoice", "read"): True},
                allowed_companies={"Crystal Traders"},
            )
        )

        authorized = boundary.authorize(
            {
                "page_type": "List",
                "doctype": "Sales Invoice",
                "filters": {"company": "Crystal Traders"},
            }
        )

        self.assertEqual(authorized.context["filters"]["company"], "Crystal Traders")

    def test_redacts_sensitive_filter_values(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Item", "read"): True},
            )
        )

        authorized = boundary.authorize(
            {
                "page_type": "List",
                "doctype": "Item",
                "filters": {"api_key": "secret-key", "item_group": "Products"},
            }
        )

        self.assertEqual(authorized.context["filters"]["api_key"], "[redacted]")
        self.assertEqual(authorized.context["filters"]["item_group"], "Products")
        self.assertIn("filters.api_key", authorized.decision.redacted_fields)

    def test_provider_capability_still_requires_context_permission(self):
        boundary = CopilotPermissionBoundary(StaticPermissionAdapter())

        with self.assertRaises(PermissionDenied):
            boundary.authorize(
                {"page_type": "List", "doctype": "Salary Slip"},
                capability=CAPABILITY_CALL_PROVIDER,
            )

    def test_write_capability_requires_system_manager(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                roles={"Employee"},
                doctype_permissions={("Item", "read"): True},
            )
        )

        with self.assertRaises(PermissionDenied):
            boundary.authorize(
                {"page_type": "List", "doctype": "Item"},
                capability=CAPABILITY_WRITE_ACTION,
            )

    def test_guest_cannot_access_context(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                user="Guest",
                doctype_permissions={("Item", "read"): True},
            )
        )

        with self.assertRaises(PermissionDenied):
            boundary.authorize(
                {"page_type": "List", "doctype": "Item"},
                capability=CAPABILITY_READ_CONTEXT,
            )


if __name__ == "__main__":
    unittest.main()
