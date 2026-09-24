import unittest

from reckon_copilot.advisor.catalog import AdvisorCatalog, AdvisorTemplate
from reckon_copilot.advisor.learning import (
    InMemoryCatalogLearningRepository,
    generate_candidates,
    publish_candidate,
    record_feedback,
    validate_candidate,
)
from reckon_copilot.permissions.boundary import StaticPermissionAdapter


class CatalogLearningTests(unittest.TestCase):
    def setUp(self):
        self.template = AdvisorTemplate(
            key="catalog.sales.sales_order.list.review",
            title="Review Sales Orders",
            prompt_template="As of {current_date}, review permitted {doctype} records.",
            category="sales-review",
            page_type="List",
            action_type="review",
            reason="Review the visible Sales Order scope.",
            doctype="Sales Order",
            required_fields=("status",),
            intent_type="read_only_list_analysis",
        )
        self.catalog = AdvisorCatalog([self.template])
        self.repository = InMemoryCatalogLearningRepository()
        self.context = {"page_type": "List", "doctype": "Sales Order", "document_name": "SO-0001"}

    def test_feedback_is_aggregated_without_user_or_record_identity(self):
        for _ in range(2):
            record_feedback(self.repository, self.template.key, "selected", self.context)
        aggregate = record_feedback(self.repository, self.template.key, "not_relevant", self.context)

        self.assertEqual(aggregate.selected_count, 2)
        self.assertEqual(aggregate.not_relevant_count, 1)
        self.assertNotIn("SO-0001", aggregate.feedback_key)
        self.assertNotIn("document_name", aggregate.as_dict())

    def test_candidates_require_repeated_negative_feedback_and_are_idempotent(self):
        for _ in range(3):
            record_feedback(self.repository, self.template.key, "too_generic", self.context)

        candidates = generate_candidates(self.repository, self.catalog)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].status, "PENDING")
        self.assertIn("compact evidence", candidates[0].prompt_template)
        self.assertEqual(generate_candidates(self.repository, self.catalog), [])

    def test_candidate_validation_checks_installed_fields_and_permissions(self):
        for _ in range(3):
            record_feedback(self.repository, self.template.key, "not_relevant", self.context)
        candidate = generate_candidates(self.repository, self.catalog)[0]

        denied = validate_candidate(
            candidate,
            self.catalog,
            {"field_names": ["status"]},
            StaticPermissionAdapter(),
            "user@example.com",
        )
        self.assertEqual(denied.validation_status, "REJECTED")
        self.assertIn("no read access", denied.validation_message)

        allowed = validate_candidate(
            candidate,
            self.catalog,
            {"field_names": ["status"]},
            StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True}),
            "user@example.com",
        )
        self.assertEqual(allowed.validation_status, "VALID")

    def test_publication_requires_admin_and_creates_read_only_runtime_template(self):
        for _ in range(3):
            record_feedback(self.repository, self.template.key, "too_generic", self.context)
        candidate = generate_candidates(self.repository, self.catalog)[0]
        candidate = validate_candidate(
            candidate,
            self.catalog,
            {"field_names": ["status"]},
            StaticPermissionAdapter(doctype_permissions={("Sales Order", "read"): True}),
            "Administrator",
        )
        with self.assertRaises(PermissionError):
            publish_candidate(self.repository, candidate, approver="user@example.com", is_admin=False)

        published = publish_candidate(self.repository, candidate, approver="Administrator", is_admin=True)
        self.assertTrue(published.approved)
        self.assertTrue(published.intent_type.startswith("read_only"))
        self.assertEqual(self.repository.list_candidates()[0].status, "APPROVED")
        self.assertEqual(self.repository.list_templates()[0].key, published.key)
        snapshots = self.repository.list_snapshots()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].status, "Published")
        self.assertIn(published.key, snapshots[0].template_keys)

    def test_snapshot_rollback_publishes_a_new_active_version(self):
        first = AdvisorTemplate(
            key="approved.first",
            title="First",
            prompt_template="Review {doctype}.",
            category="review",
            page_type="List",
            action_type="review",
            reason="First",
            doctype="Sales Order",
        )
        second = AdvisorTemplate(
            key="approved.second",
            title="Second",
            prompt_template="Explain {doctype}.",
            category="review",
            page_type="List",
            action_type="question",
            reason="Second",
            doctype="Sales Order",
        )
        self.repository.save_template(first, approved_by="Administrator")
        original = self.repository.publish_snapshot([first], source_candidate="first", published_by="Administrator")
        self.repository.save_template(second, approved_by="Administrator")
        self.repository.publish_snapshot([first, second], source_candidate="second", published_by="Administrator")

        rollback = self.repository.rollback_snapshot(original.snapshot_key, published_by="Administrator")
        self.assertIsNotNone(rollback)
        self.assertEqual(rollback.rollback_of, original.snapshot_key)
        self.assertEqual(rollback.template_keys, (first.key,))
        self.assertEqual(len([item for item in self.repository.list_snapshots() if item.status == "Published"]), 1)


if __name__ == "__main__":
    unittest.main()
