from __future__ import annotations

import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

from reckon_copilot.api.context import _canonicalize_with_frappe, get_context
from reckon_copilot.context.builders import build_context
from reckon_copilot.permissions import PermissionDenied


class ContextApiTests(unittest.TestCase):
    def test_frappe_canonicalizes_module_route_before_permission_checks(self):
        fake_frappe = _FakeFrappe(workspaces={"Selling", "Reckon Copilot"})
        context = build_context(route=["List", "Selling", "List"], page_type="List")

        with patch.dict(sys.modules, {"frappe": fake_frappe}):
            canonical = _canonicalize_with_frappe(context)

        self.assertEqual(canonical["page_type"], "Workspace")
        self.assertEqual(canonical["workspace_name"], "Selling")
        self.assertNotIn("doctype", canonical)

    def test_frappe_canonicalizes_private_workspace_slug(self):
        fake_frappe = _FakeFrappe(workspaces={"Reckon Copilot"})
        context = build_context(
            route=["private", "reckon-copilot"],
            page_type="Workspace",
        )

        with patch.dict(sys.modules, {"frappe": fake_frappe}):
            canonical = _canonicalize_with_frappe(context)

        self.assertEqual(canonical["page_type"], "Workspace")
        self.assertEqual(canonical["workspace_name"], "Reckon Copilot")

    def test_permission_denied_returns_panel_alert_payload(self):
        with patch(
            "reckon_copilot.api.context.authorize_context",
            side_effect=PermissionDenied("No access to requested workspace"),
        ):
            context = get_context(route=["Workspace", "Restricted"], filters={}, page_type="Workspace")

        self.assertTrue(context["access_denied"])
        self.assertEqual(context["page_type"], "Workspace")
        self.assertEqual(context["workspace_name"], "Restricted")
        self.assertEqual(context["permission"]["allowed"], False)
        self.assertEqual(context["permission"]["reason"], "No access to requested workspace")
        self.assertEqual(len(context["fingerprint"]), 64)

    def test_permission_error_returns_panel_alert_payload(self):
        with patch(
            "reckon_copilot.api.context.authorize_context",
            side_effect=PermissionError("No access to requested report"),
        ):
            context = get_context(
                route=["Report", "Item-wise Sales Register"],
                filters={"company": "Crystal Traders"},
                page_type="Report",
            )

        self.assertTrue(context["access_denied"])
        self.assertEqual(context["page_type"], "Report")
        self.assertEqual(context["report_name"], "Item-wise Sales Register")
        self.assertEqual(context["permission"]["reason"], "No access to requested report")

class _FakeDB:
    def __init__(self, workspaces):
        self.workspaces = set(workspaces)

    def exists(self, doctype, name):
        if doctype == "Workspace":
            return name if name in self.workspaces else None
        return None


class _FakeFrappe:
    def __init__(self, workspaces):
        self.db = _FakeDB(workspaces)

    def get_all(self, doctype, fields=None, limit_page_length=None):
        if doctype != "Workspace":
            return []
        return [{"name": name} for name in sorted(self.db.workspaces)]

    def get_meta(self, name):
        return SimpleNamespace(is_tree=False)


if __name__ == "__main__":
    unittest.main()
