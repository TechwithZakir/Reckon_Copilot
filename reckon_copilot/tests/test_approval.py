import unittest
from unittest.mock import patch

from reckon_copilot.actions.approval import issue_approval_token, validate_approval_token


class ApprovalTokenTests(unittest.TestCase):
    def test_token_is_scoped_and_validates(self):
        plan = {"plan_hash": "a" * 64}
        token = issue_approval_token(plan, user="Administrator", site="test.local")
        result = validate_approval_token(token, plan_hash=plan["plan_hash"], user="Administrator", site="test.local")
        self.assertEqual(result["plan_hash"], plan["plan_hash"])

    def test_token_rejects_different_plan_or_user(self):
        plan = {"plan_hash": "b" * 64}
        token = issue_approval_token(plan, user="Administrator", site="test.local")
        with self.assertRaises(ValueError):
            validate_approval_token(token, plan_hash="c" * 64, user="Administrator", site="test.local")

    def test_token_expiry_is_enforced(self):
        plan = {"plan_hash": "d" * 64}
        token = issue_approval_token(plan, user="Administrator", site="test.local", ttl_seconds=1)
        with patch("reckon_copilot.actions.approval.time.time", return_value=9999999999):
            with self.assertRaises(ValueError):
                validate_approval_token(token, plan_hash=plan["plan_hash"], user="Administrator", site="test.local")


if __name__ == "__main__":
    unittest.main()
