from __future__ import annotations

import json
import unittest
from pathlib import Path


class WorkspaceTests(unittest.TestCase):
    def test_reckon_copilot_workspace_links_knowledge_doctypes(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "reckon_copilot"
            / "workspace"
            / "reckon_copilot"
            / "reckon_copilot.json"
        )
        workspace = json.loads(path.read_text())
        links = {link.get("link_to") for link in workspace["links"] if link.get("type") == "Link"}
        shortcuts = {shortcut.get("link_to") for shortcut in workspace["shortcuts"]}
        expected = {
            "Copilot Knowledge Source",
            "Copilot Knowledge Document",
            "Copilot Knowledge Chunk",
            "Copilot Knowledge Ingestion Job",
            "Copilot Knowledge Vector Index",
            "Copilot User Preference",
            "Copilot Provider",
            "Copilot Usage Log",
        }

        self.assertTrue(expected.issubset(links))
        self.assertTrue(expected.issubset(shortcuts))

    def test_reckon_copilot_workspace_is_administrator_only(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "reckon_copilot"
            / "workspace"
            / "reckon_copilot"
            / "reckon_copilot.json"
        )
        workspace = json.loads(path.read_text())

        self.assertEqual(workspace["for_user"], "Administrator")
        self.assertEqual(workspace["public"], 0)


if __name__ == "__main__":
    unittest.main()
