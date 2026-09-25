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
        self.assertEqual(len(authorized.context["permission"]["scope_hash"]), 64)

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

    def test_missing_workspace_route_is_allowed_as_module_context(self):
        boundary = CopilotPermissionBoundary(StaticPermissionAdapter())

        authorized = boundary.authorize(
            {
                "page_type": "Workspace",
                "workspace_name": "Copilot Knowledge Ingestion Job",
                "filters": {},
            }
        )

        self.assertEqual(authorized.context["workspace_name"], "Copilot Knowledge Ingestion Job")

    def test_existing_workspace_without_permission_is_denied(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                workspaces={"Restricted Workspace"},
            )
        )
        boundary.adapter.workspaces = {"Restricted Workspace"}
        boundary.adapter.has_workspace_permission = lambda workspace_name, user: False

        with self.assertRaises(PermissionDenied):
            boundary.authorize(
                {
                    "page_type": "Workspace",
                    "workspace_name": "Restricted Workspace",
                    "filters": {},
                }
            )

    def test_provider_capability_cannot_side_channel_restricted_document(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                roles={"Sales User"},
                doctype_permissions={("Sales Invoice", "read"): True},
                document_permissions={
                    ("Sales Invoice", "SINV-SECRET", "read"): False,
                },
            )
        )

        with self.assertRaises(PermissionDenied):
            boundary.authorize(
                {
                    "page_type": "Form",
                    "doctype": "Sales Invoice",
                    "document_name": "SINV-SECRET",
                },
                capability=CAPABILITY_CALL_PROVIDER,
            )

    def test_write_capability_does_not_require_admin_role(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                roles={"Employee"},
                doctype_permissions={("Item", "read"): True},
            )
        )

        authorized = boundary.authorize(
            {"page_type": "List", "doctype": "Item"},
            capability=CAPABILITY_WRITE_ACTION,
        )
        self.assertTrue(authorized.decision.allowed)

    def test_import_preview_requires_native_create_permission(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={
                    ("Sales Order", "read"): True,
                    ("Sales Order", "create"): True,
                },
            )
        )

        authorized = boundary.authorize_import_preview(
            {"page_type": "List", "doctype": "Sales Order"},
            "Sales Order",
        )

        self.assertTrue(authorized.decision.allowed)

    def test_import_preview_blocks_without_native_create_permission(self):
        boundary = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Sales Order", "read"): True},
            )
        )

        with self.assertRaises(PermissionDenied):
            boundary.authorize_import_preview(
                {"page_type": "List", "doctype": "Sales Order"},
                "Sales Order",
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

    def test_permission_scope_hash_changes_when_roles_change(self):
        context = {"page_type": "List", "doctype": "Item", "filters": {}}
        first = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                roles={"Stock User"},
                doctype_permissions={("Item", "read"): True},
            )
        ).authorize(context)
        second = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                roles={"Stock Manager"},
                doctype_permissions={("Item", "read"): True},
            )
        ).authorize(context)

        self.assertNotEqual(
            first.context["permission"]["scope_hash"],
            second.context["permission"]["scope_hash"],
        )

    def test_permission_scope_hash_changes_when_user_permission_scope_changes(self):
        context = {
            "page_type": "List",
            "doctype": "Sales Invoice",
            "filters": {"company": "Crystal Traders"},
        }
        first = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Sales Invoice", "read"): True},
                allowed_companies={"Crystal Traders"},
            )
        ).authorize(context)
        second = CopilotPermissionBoundary(
            StaticPermissionAdapter(
                doctype_permissions={("Sales Invoice", "read"): True},
                allowed_companies={"Crystal Traders", "Blocked Company"},
            )
        ).authorize(context)

        self.assertNotEqual(
            first.context["permission"]["scope_hash"],
            second.context["permission"]["scope_hash"],
        )


if __name__ == "__main__":
    unittest.main()
