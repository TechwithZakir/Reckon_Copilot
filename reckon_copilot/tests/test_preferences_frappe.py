from __future__ import annotations

import unittest

try:
    import frappe
    from frappe.tests.utils import FrappeTestCase
except ImportError:
    frappe = None
    FrappeTestCase = unittest.TestCase

from reckon_copilot.api.preferences import get_preferences, update_preferences


@unittest.skipUnless(frappe, "Frappe test environment required")
class PreferenceFrappeTests(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        self.test_user = "reckon.copilot.phase1@example.com"
        if not frappe.db.exists("User", self.test_user):
            user = frappe.new_doc("User")
            user.email = self.test_user
            user.first_name = "Reckon Copilot"
            user.send_welcome_email = 0
            user.insert(ignore_permissions=True)
        frappe.set_user(self.test_user)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_preferences_persist_for_current_user(self):
        saved = update_preferences(
            enabled=False,
            notifications_enabled=True,
            response_sound_enabled=True,
        )

        self.assertFalse(saved["enabled"])
        self.assertTrue(saved["response_sound_enabled"])
        self.assertEqual(get_preferences(), saved)

        name = frappe.db.exists(
            "Copilot User Preference", {"user": self.test_user}
        )
        self.assertTrue(name)
        self.assertEqual(
            frappe.db.get_value("Copilot User Preference", name, "user"),
            self.test_user,
        )

    def test_guest_access_is_rejected(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            get_preferences()
