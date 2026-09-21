from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class DesktopIconTests(unittest.TestCase):
    def test_desktop_icon_points_to_workspace_sidebar(self):
        path = Path(__file__).resolve().parents[1] / "desktop_icon" / "reckon_copilot.json"
        icon = json.loads(path.read_text())

        self.assertEqual(icon["doctype"], "Desktop Icon")
        self.assertEqual(icon["label"], "Reckon Copilot")
        self.assertEqual(icon["link_type"], "Workspace Sidebar")
        self.assertEqual(icon["link_to"], "Reckon Copilot")
        self.assertEqual(icon["hidden"], 0)
        self.assertEqual(icon["roles"], [{"role": "System Manager"}])

    def test_hooks_register_desktop_icon_sync(self):
        hooks = importlib.import_module("reckon_copilot.hooks")

        self.assertIn("reckon_copilot.patches.v0_1.sync_desktop_app_icon.execute", hooks.after_migrate)
        self.assertEqual(hooks.add_to_apps_screen[0]["title"], "Reckon Copilot")
        self.assertEqual(
            hooks.add_to_apps_screen[0]["has_permission"],
            "reckon_copilot.api.shell.can_access_copilot_app",
        )

    def test_app_permission_allows_system_manager(self):
        fake_frappe = SimpleNamespace(
            session=SimpleNamespace(user="manager@example.com"),
            get_roles=lambda user: ["System Manager"],
        )
        with patch.dict(sys.modules, {"frappe": fake_frappe}):
            shell = importlib.reload(importlib.import_module("reckon_copilot.api.shell"))
            self.assertTrue(shell.can_access_copilot_app())

    def test_app_permission_blocks_non_manager(self):
        fake_frappe = SimpleNamespace(
            session=SimpleNamespace(user="employee@example.com"),
            get_roles=lambda user: ["Employee"],
        )
        with patch.dict(sys.modules, {"frappe": fake_frappe}):
            shell = importlib.reload(importlib.import_module("reckon_copilot.api.shell"))
            self.assertFalse(shell.can_access_copilot_app())


if __name__ == "__main__":
    unittest.main()
