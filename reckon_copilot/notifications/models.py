from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CopilotNotification:
    title: str
    message: str
    level: str = "info"
    source: str = "insight"
    source_id: str = ""
    action_label: str = "Review"
    action_prompt: str = "What should I review?"
    dismissible: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "notification_id": self.notification_id,
            "title": self.title,
            "message": self.message,
            "level": self.level if self.level in {"critical", "warning", "info"} else "info",
            "source": self.source,
            "source_id": self.source_id,
            "action_label": self.action_label,
            "action_prompt": self.action_prompt,
            "dismissible": self.dismissible,
        }
        return payload

    @property
    def notification_id(self) -> str:
        identity = {
            "title": self.title,
            "message": self.message,
            "level": self.level,
            "source": self.source,
            "source_id": self.source_id,
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]
