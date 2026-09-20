from __future__ import annotations

import unittest

from reckon_copilot.api.preferences import (
    DEFAULT_PREFERENCES,
    normalize_preference_updates,
    require_authenticated_user,
)


class PreferenceContractTests(unittest.TestCase):
    def test_defaults_are_enabled_and_sound_is_optional(self):
        self.assertEqual(
            DEFAULT_PREFERENCES,
            {
                "enabled": True,
                "notifications_enabled": True,
                "response_sound_enabled": False,
            },
        )

    def test_boolean_updates_are_normalized(self):
        self.assertEqual(
            normalize_preference_updates(
                {
                    "enabled": "0",
                    "notifications_enabled": 1,
                    "response_sound_enabled": "true",
                }
            ),
            {
                "enabled": False,
                "notifications_enabled": True,
                "response_sound_enabled": True,
            },
        )

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_preference_updates({"user": "another@example.com"})

    def test_guest_is_rejected(self):
        with self.assertRaises(PermissionError):
            require_authenticated_user("Guest")

    def test_authenticated_user_is_returned(self):
        self.assertEqual(
            require_authenticated_user("user@example.com"),
            "user@example.com",
        )


if __name__ == "__main__":
    unittest.main()
