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

        self.assertIn("Copilot Knowledge Source", links)
        self.assertIn("Copilot Knowledge Document", links)
        self.assertIn("Copilot Knowledge Chunk", links)
        self.assertIn("Copilot Knowledge Ingestion Job", links)
        self.assertIn("Copilot Knowledge Vector Index", links)
        self.assertIn("Copilot User Preference", links)


if __name__ == "__main__":
    unittest.main()
