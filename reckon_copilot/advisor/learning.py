"""Privacy-safe feedback and administrator-approved advisor improvements.

This module deliberately does not train a model. It aggregates coarse outcomes,
turns repeated negative signals into reviewable candidates, validates candidates
against the installed schema and native permissions, and publishes only approved
read-only catalog templates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Protocol

from reckon_copilot.advisor.catalog import AdvisorCatalog, AdvisorTemplate, WRITE_ACTIONS
from reckon_copilot.permissions.boundary import PermissionAdapter


FEEDBACK_OUTCOMES = {"selected", "helpful", "not_relevant", "too_generic", "dismissed"}
NEGATIVE_OUTCOMES = {"not_relevant", "too_generic"}
MIN_NEGATIVE_FEEDBACK = 3


@dataclass
class FeedbackAggregate:
    feedback_key: str
    template_id: str
    page_type: str
    doctype: str = ""
    module: str = ""
    catalog_version: str = "1"
    selected_count: int = 0
    helpful_count: int = 0
    not_relevant_count: int = 0
    too_generic_count: int = 0
    dismissed_count: int = 0
    last_outcome: str = ""
    last_seen_at: str = ""

    @property
    def negative_count(self) -> int:
        return self.not_relevant_count + self.too_generic_count

    @property
    def total_count(self) -> int:
        return sum(
            (
                self.selected_count,
                self.helpful_count,
                self.not_relevant_count,
                self.too_generic_count,
                self.dismissed_count,
            )
        )

    def increment(self, outcome: str, now: str | None = None) -> "FeedbackAggregate":
        field_name = f"{outcome}_count"
        if field_name not in {
            "selected_count",
            "helpful_count",
            "not_relevant_count",
            "too_generic_count",
            "dismissed_count",
        }:
            raise ValueError("Unsupported feedback outcome")
        return replace(
            self,
            **{
                field_name: getattr(self, field_name) + 1,
                "last_outcome": outcome,
                "last_seen_at": now or _now(),
            },
        )

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.update({"negative_count": self.negative_count, "total_count": self.total_count})
        return result


@dataclass
class CatalogCandidate:
    candidate_key: str
    base_template_key: str
    title: str
    prompt_template: str
    category: str
    page_type: str
    action_type: str
    reason: str
    doctype: str = ""
    required_fields: tuple[str, ...] = ()
    priority: str = "normal"
    intent_type: str = "read_only_analysis"
    source_feedback_key: str = ""
    feedback_summary: str = ""
    catalog_version: str = "1"
    proposed_version: str = "1"
    source_ref: str = "aggregate_feedback"
    validation_status: str = "PENDING"
    validation_message: str = "Awaiting installed-field and permission validation."
    status: str = "PENDING"
    generated_at: str = ""
    approved_by: str = ""
    approved_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CatalogSnapshot:
    snapshot_key: str
    version: str
    template_keys: tuple[str, ...] = ()
    status: str = "Published"
    source_candidate: str = ""
    published_by: str = ""
    published_at: str = ""
    rollback_of: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_key": self.snapshot_key,
            "version": self.version,
            "status": self.status,
            "template_count": len(self.template_keys),
            "source_candidate": self.source_candidate,
            "published_by": self.published_by,
            "published_at": self.published_at,
            "rollback_of": self.rollback_of,
            "notes": self.notes,
            "manifest_json": json.dumps(
                {"template_keys": list(self.template_keys)},
                sort_keys=True,
            ),
        }


class CatalogLearningRepository(Protocol):
    def get_feedback(self, feedback_key: str) -> FeedbackAggregate | None:
        ...

    def save_feedback(self, feedback: FeedbackAggregate) -> FeedbackAggregate:
        ...

    def list_feedback(self) -> list[FeedbackAggregate]:
        ...

    def get_candidate(self, candidate_key: str) -> CatalogCandidate | None:
        ...

    def save_candidate(self, candidate: CatalogCandidate) -> CatalogCandidate:
        ...

    def list_candidates(self) -> list[CatalogCandidate]:
        ...

    def save_template(self, template: AdvisorTemplate, *, approved_by: str) -> AdvisorTemplate:
        ...

    def list_templates(self) -> list[AdvisorTemplate]:
        ...

    def publish_snapshot(
        self,
        templates: list[AdvisorTemplate],
        *,
        source_candidate: str,
        published_by: str,
        rollback_of: str = "",
    ) -> CatalogSnapshot:
        ...

    def rollback_snapshot(self, snapshot_key: str, *, published_by: str) -> CatalogSnapshot | None:
        ...

    def list_snapshots(self) -> list[CatalogSnapshot]:
        ...


class InMemoryCatalogLearningRepository:
    """Small deterministic repository used by tests and local development."""

    def __init__(self) -> None:
        self.feedback: dict[str, FeedbackAggregate] = {}
        self.candidates: dict[str, CatalogCandidate] = {}
        self.templates: dict[str, AdvisorTemplate] = {}
        self.snapshots: dict[str, CatalogSnapshot] = {}

    def get_feedback(self, feedback_key: str) -> FeedbackAggregate | None:
        return self.feedback.get(feedback_key)

    def save_feedback(self, feedback: FeedbackAggregate) -> FeedbackAggregate:
        self.feedback[feedback.feedback_key] = feedback
        return feedback

    def list_feedback(self) -> list[FeedbackAggregate]:
        return list(self.feedback.values())

    def get_candidate(self, candidate_key: str) -> CatalogCandidate | None:
        return self.candidates.get(candidate_key)

    def save_candidate(self, candidate: CatalogCandidate) -> CatalogCandidate:
        self.candidates[candidate.candidate_key] = candidate
        return candidate

    def list_candidates(self) -> list[CatalogCandidate]:
        return list(self.candidates.values())

    def save_template(self, template: AdvisorTemplate, *, approved_by: str) -> AdvisorTemplate:
        self.templates[template.key] = template
        return template

    def list_templates(self) -> list[AdvisorTemplate]:
        published = [snapshot for snapshot in self.snapshots.values() if snapshot.status == "Published"]
        if not published:
            return list(self.templates.values())
        active = max(published, key=lambda item: item.published_at or "")
        return [template for template in self.templates.values() if template.key in active.template_keys]

    def publish_snapshot(
        self,
        templates: list[AdvisorTemplate],
        *,
        source_candidate: str,
        published_by: str,
        rollback_of: str = "",
    ) -> CatalogSnapshot:
        for snapshot in self.snapshots.values():
            snapshot.status = "Retired"
        version = str(len(self.snapshots) + 1)
        digest = hashlib.sha256("|".join(sorted(item.key for item in templates)).encode("utf-8")).hexdigest()[:10]
        snapshot = CatalogSnapshot(
            snapshot_key=f"catalog-snapshot-{version}-{digest}",
            version=version,
            template_keys=tuple(sorted(item.key for item in templates)),
            source_candidate=source_candidate,
            published_by=published_by,
            published_at=_now(),
            rollback_of=rollback_of,
        )
        self.snapshots[snapshot.snapshot_key] = snapshot
        return snapshot

    def rollback_snapshot(self, snapshot_key: str, *, published_by: str) -> CatalogSnapshot | None:
        target = self.snapshots.get(snapshot_key)
        if target is None:
            return None
        templates = [self.templates[key] for key in target.template_keys if key in self.templates]
        return self.publish_snapshot(
            templates,
            source_candidate="",
            published_by=published_by,
            rollback_of=target.snapshot_key,
        )

    def list_snapshots(self) -> list[CatalogSnapshot]:
        return list(self.snapshots.values())


class FrappeCatalogLearningRepository:
    """Frappe-backed aggregate, candidate and published-template storage."""

    def __init__(self, frappe_module: Any):
        self.frappe = frappe_module

    def get_feedback(self, feedback_key: str) -> FeedbackAggregate | None:
        return self._get("Copilot Suggestion Feedback", feedback_key, _feedback_from_row)

    def save_feedback(self, feedback: FeedbackAggregate) -> FeedbackAggregate:
        self._save("Copilot Suggestion Feedback", feedback.feedback_key, _feedback_row(feedback))
        return feedback

    def list_feedback(self) -> list[FeedbackAggregate]:
        return [
            _feedback_from_row(row)
            for row in self._all("Copilot Suggestion Feedback")
        ]

    def get_candidate(self, candidate_key: str) -> CatalogCandidate | None:
        return self._get("Copilot Catalog Candidate", candidate_key, _candidate_from_row)

    def save_candidate(self, candidate: CatalogCandidate) -> CatalogCandidate:
        self._save("Copilot Catalog Candidate", candidate.candidate_key, _candidate_row(candidate))
        return candidate

    def list_candidates(self) -> list[CatalogCandidate]:
        return [
            _candidate_from_row(row)
            for row in self._all("Copilot Catalog Candidate")
        ]

    def save_template(self, template: AdvisorTemplate, *, approved_by: str) -> AdvisorTemplate:
        values = {
            "template_key": template.key,
            "title": template.title,
            "prompt_template": template.prompt_template,
            "category": template.category,
            "page_type": template.page_type,
            "action_type": template.action_type,
            "target_doctype": template.doctype,
            "required_fields": "\n".join(template.required_fields),
            "priority": template.priority,
            "intent_type": template.intent_type,
            "reason": template.reason,
            "source_ref": template.source_ref,
            "catalog_version": template.version,
            "status": "Approved",
            "enabled": 1,
            "approved_by": approved_by,
            "approved_at": _now(),
            "metadata_json": json.dumps(template.metadata, sort_keys=True),
        }
        self._save("Copilot Suggested Action Template", template.key, values)
        return template

    def list_templates(self) -> list[AdvisorTemplate]:
        active_keys = self._active_template_keys()
        rows = self._all(
            "Copilot Suggested Action Template",
            filters={"status": "Approved", "enabled": 1},
        )
        templates: list[AdvisorTemplate] = []
        for row in rows:
            try:
                action_type = str(row.get("action_type") or "question")
                intent_type = str(row.get("intent_type") or "read_only_analysis")
                template_key = str(row.get("template_key") or row.get("name") or "")
                if active_keys is not None and template_key not in active_keys:
                    continue
                if action_type in WRITE_ACTIONS or intent_type.startswith("write_"):
                    continue
                templates.append(
                    AdvisorTemplate(
                        key=template_key,
                        title=str(row.get("title") or ""),
                        prompt_template=str(row.get("prompt_template") or ""),
                        category=str(row.get("category") or "advisor"),
                        page_type=str(row.get("page_type") or "List"),
                        action_type=action_type,
                        reason=str(row.get("reason") or "Approved by an administrator."),
                        doctype=str(_target_doctype(row) or "") or None,
                        required_fields=_split_fields(row.get("required_fields")),
                        priority=str(row.get("priority") or "normal"),
                        intent_type=intent_type,
                        version=str(row.get("catalog_version") or "1"),
                        source_ref=str(row.get("source_ref") or "administrator-approved-template"),
                        metadata=_json_object(row.get("metadata_json")),
                    )
                )
            except (TypeError, ValueError):
                continue
        return templates

    def publish_snapshot(
        self,
        templates: list[AdvisorTemplate],
        *,
        source_candidate: str,
        published_by: str,
        rollback_of: str = "",
    ) -> CatalogSnapshot:
        previous = self._published_snapshot()
        if previous:
            self._set_snapshot_status(previous.snapshot_key, "Retired")
        version = str((int(previous.version) + 1) if previous and previous.version.isdigit() else 1)
        digest = hashlib.sha256("|".join(sorted(item.key for item in templates)).encode("utf-8")).hexdigest()[:10]
        snapshot = CatalogSnapshot(
            snapshot_key=f"catalog-snapshot-{version}-{digest}",
            version=version,
            template_keys=tuple(sorted(item.key for item in templates)),
            source_candidate=source_candidate,
            published_by=published_by,
            published_at=_now(),
            rollback_of=rollback_of,
        )
        self._save("Copilot Catalog Snapshot", snapshot.snapshot_key, snapshot.as_dict())
        return snapshot

    def rollback_snapshot(self, snapshot_key: str, *, published_by: str) -> CatalogSnapshot | None:
        target = self._get("Copilot Catalog Snapshot", snapshot_key, _snapshot_from_row)
        if target is None:
            return None
        templates = [template for template in self.list_templates() if template.key in target.template_keys]
        # Include retired templates from the target manifest when the active
        # snapshot no longer exposes them through list_templates().
        if len(templates) != len(target.template_keys):
            templates = self._templates_for_keys(target.template_keys)
        return self.publish_snapshot(
            templates,
            source_candidate="",
            published_by=published_by,
            rollback_of=target.snapshot_key,
        )

    def list_snapshots(self) -> list[CatalogSnapshot]:
        return [_snapshot_from_row(row) for row in self._all("Copilot Catalog Snapshot")]

    def _published_snapshot(self) -> CatalogSnapshot | None:
        rows = self._all("Copilot Catalog Snapshot", filters={"status": "Published"})
        snapshots = [_snapshot_from_row(row) for row in rows]
        return max(snapshots, key=lambda item: item.published_at or "") if snapshots else None

    def _active_template_keys(self) -> set[str] | None:
        snapshot = self._published_snapshot()
        return set(snapshot.template_keys) if snapshot else None

    def _templates_for_keys(self, keys: tuple[str, ...]) -> list[AdvisorTemplate]:
        rows = self._all("Copilot Suggested Action Template")
        allowed = set(keys)
        templates: list[AdvisorTemplate] = []
        for row in rows:
            if str(row.get("template_key") or row.get("name") or "") not in allowed:
                continue
            if str(row.get("action_type") or "question") in WRITE_ACTIONS:
                continue
            try:
                templates.append(
                    AdvisorTemplate(
                        key=str(row.get("template_key") or row.get("name") or ""),
                        title=str(row.get("title") or ""),
                        prompt_template=str(row.get("prompt_template") or ""),
                        category=str(row.get("category") or "advisor"),
                        page_type=str(row.get("page_type") or "List"),
                        action_type=str(row.get("action_type") or "question"),
                        reason=str(row.get("reason") or "Approved by an administrator."),
                        doctype=_target_doctype(row) or None,
                        required_fields=_split_fields(row.get("required_fields")),
                        priority=str(row.get("priority") or "normal"),
                        intent_type=str(row.get("intent_type") or "read_only_analysis"),
                        version=str(row.get("catalog_version") or "1"),
                        source_ref=str(row.get("source_ref") or "administrator-approved-template"),
                        metadata=_json_object(row.get("metadata_json")),
                    )
                )
            except (TypeError, ValueError):
                continue
        return templates

    def _set_snapshot_status(self, snapshot_key: str, status: str) -> None:
        try:
            doc = self.frappe.get_doc("Copilot Catalog Snapshot", snapshot_key)
            doc.status = status
            doc.save(ignore_permissions=True)
        except Exception:
            return None

    def _get(self, doctype: str, name: str, converter):
        try:
            if not self.frappe.db.exists(doctype, name):
                return None
            return converter(self.frappe.get_doc(doctype, name))
        except Exception:
            return None

    def _all(self, doctype: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            return list(
                self.frappe.get_all(
                    doctype,
                    filters=filters or {},
                    fields="*",
                    limit_page_length=0,
                )
                or []
            )
        except Exception:
            return []

    def _save(self, doctype: str, name: str, values: dict[str, Any]) -> None:
        payload = {key: value for key, value in values.items() if value is not None}
        try:
            if self.frappe.db.exists(doctype, name):
                doc = self.frappe.get_doc(doctype, name)
                doc.update(payload)
                doc.save(ignore_permissions=True)
            else:
                self.frappe.get_doc({"doctype": doctype, **payload}).insert(ignore_permissions=True)
        except Exception:
            # Feedback must never break the user workflow. Scheduled/admin calls
            # can inspect logs and retry after migration if a DocType is absent.
            return None


def record_feedback(
    repository: CatalogLearningRepository,
    template_id: str,
    outcome: str,
    context: dict[str, Any] | None = None,
    catalog_version: str = "1",
) -> FeedbackAggregate:
    outcome = str(outcome or "").strip().lower()
    if outcome not in FEEDBACK_OUTCOMES:
        raise ValueError("Unsupported feedback outcome")
    safe = _safe_context(context or {})
    template_id = str(template_id or "").strip()[:180]
    if not template_id:
        raise ValueError("A catalog template id is required")
    key = feedback_key(template_id, safe, catalog_version)
    current = repository.get_feedback(key) or FeedbackAggregate(
        feedback_key=key,
        template_id=template_id,
        page_type=safe.get("page_type", "Page"),
        doctype=safe.get("doctype", ""),
        module=safe.get("module", ""),
        catalog_version=str(catalog_version or "1")[:40],
    )
    return repository.save_feedback(current.increment(outcome))


def feedback_key(template_id: str, context: dict[str, Any], catalog_version: str = "1") -> str:
    payload = {
        "template_id": str(template_id).strip().lower(),
        "page_type": context.get("page_type", "Page"),
        "doctype": context.get("doctype", ""),
        "module": context.get("module", ""),
        "catalog_version": str(catalog_version or "1"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"feedback-{digest[:32]}"


def generate_candidates(
    repository: CatalogLearningRepository,
    catalog: AdvisorCatalog,
    *,
    minimum_negative_feedback: int = MIN_NEGATIVE_FEEDBACK,
) -> list[CatalogCandidate]:
    generated: list[CatalogCandidate] = []
    for feedback in repository.list_feedback():
        if feedback.negative_count < minimum_negative_feedback:
            continue
        template = catalog.find(feedback.template_id)
        if template is None or not template.approved or not template.enabled:
            continue
        candidate_key = _candidate_key(feedback, template)
        if repository.get_candidate(candidate_key):
            continue
        title, prompt, reason = _improvement_for(template, feedback)
        candidate = CatalogCandidate(
            candidate_key=candidate_key,
            base_template_key=template.key,
            title=title,
            prompt_template=prompt,
            category=template.category,
            page_type=template.page_type,
            action_type=template.action_type,
            reason=reason,
            doctype=template.doctype or feedback.doctype,
            required_fields=template.required_fields,
            priority=template.priority,
            intent_type=template.intent_type,
            source_feedback_key=feedback.feedback_key,
            feedback_summary=(
                f"{feedback.total_count} total signals; "
                f"{feedback.not_relevant_count} not relevant; "
                f"{feedback.too_generic_count} too generic."
            ),
            catalog_version=template.version,
            proposed_version=_next_version(template.version),
            generated_at=_now(),
        )
        generated.append(repository.save_candidate(candidate))
    return generated


def validate_candidate(
    candidate: CatalogCandidate,
    catalog: AdvisorCatalog,
    metadata: dict[str, Any],
    permission_adapter: PermissionAdapter,
    user: str,
) -> CatalogCandidate:
    base = catalog.find(candidate.base_template_key)
    if base is None:
        return replace(candidate, validation_status="REJECTED", validation_message="The source catalog template is no longer installed.")
    if candidate.action_type in WRITE_ACTIONS or candidate.intent_type.startswith("write_"):
        return replace(candidate, validation_status="REJECTED", validation_message="Only read-only advisor templates can be published.")
    if candidate.page_type not in {"Homepage", "Workspace", "Dashboard", "List", "Form", "Report"}:
        return replace(candidate, validation_status="REJECTED", validation_message="The page type is not supported by the advisor.")
    available = {str(value).strip().lower() for value in metadata.get("field_names") or []}
    missing = [field for field in candidate.required_fields if field.lower() not in available]
    if missing:
        return replace(
            candidate,
            validation_status="REJECTED",
            validation_message=f"Installed schema is missing: {', '.join(missing[:6])}.",
        )
    if candidate.doctype and candidate.page_type in {"List", "Form"}:
        if not permission_adapter.has_doctype_permission(candidate.doctype, "read", user):
            return replace(candidate, validation_status="REJECTED", validation_message="The validation user has no read access to the target DocType.")
    return replace(candidate, validation_status="VALID", validation_message="Installed fields and read permission validated.")


def publish_candidate(
    repository: CatalogLearningRepository,
    candidate: CatalogCandidate,
    *,
    approver: str,
    is_admin: bool,
) -> AdvisorTemplate:
    if not is_admin:
        raise PermissionError("Administrator approval is required before publishing")
    if candidate.status != "PENDING":
        raise ValueError("Only pending candidates can be published")
    if candidate.validation_status != "VALID":
        raise ValueError("Candidate must pass installed-field and permission validation first")
    template = AdvisorTemplate(
        key=f"approved.{candidate.candidate_key}",
        title=candidate.title,
        prompt_template=candidate.prompt_template,
        category=candidate.category,
        page_type=candidate.page_type,
        action_type=candidate.action_type,
        reason=candidate.reason,
        doctype=candidate.doctype or None,
        required_fields=candidate.required_fields,
        priority=candidate.priority,
        intent_type=candidate.intent_type,
        version=candidate.proposed_version,
        source_ref=f"candidate:{candidate.candidate_key}",
        enabled=True,
        approved=True,
        metadata={"source_feedback_key": candidate.source_feedback_key},
    )
    repository.save_template(template, approved_by=approver)
    published_templates = repository.list_templates()
    if not any(item.key == template.key for item in published_templates):
        published_templates = [*published_templates, template]
    repository.publish_snapshot(
        published_templates,
        source_candidate=candidate.candidate_key,
        published_by=approver,
    )
    repository.save_candidate(
        replace(candidate, status="APPROVED", approved_by=approver, approved_at=_now())
    )
    return template


def _improvement_for(template: AdvisorTemplate, feedback: FeedbackAggregate) -> tuple[str, str, str]:
    if feedback.too_generic_count >= feedback.not_relevant_count:
        return (
            f"{template.title} with visible evidence",
            f"{template.prompt_template.rstrip('.')} Include the active page scope, relevant fields, current date and compact evidence. If a required signal is unavailable, say so clearly.",
            "Repeated users found this guidance too broad, so the candidate makes scope, evidence and missing data explicit.",
        )
    return (
        f"{template.title} for matching page signals",
        f"Only answer when the current page has a matching signal. Explain why it is relevant, name the evidence used, and state when the signal is unavailable. {template.prompt_template}",
        "Repeated users found this guidance unrelated to some pages, so the candidate adds a relevance gate and evidence explanation.",
    )


def _safe_context(context: dict[str, Any]) -> dict[str, str]:
    allowed = {"page_type", "doctype", "module"}
    return {
        key: str(context.get(key) or "")[:120]
        for key in allowed
        if context.get(key) not in (None, "")
    }


def _candidate_key(feedback: FeedbackAggregate, template: AdvisorTemplate) -> str:
    raw = f"{feedback.feedback_key}:{template.version}"
    return f"candidate-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _next_version(version: str) -> str:
    try:
        return str(int(str(version).split(".", 1)[0]) + 1)
    except (TypeError, ValueError):
        return f"{version}.1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _feedback_from_row(row: Any) -> FeedbackAggregate:
    return FeedbackAggregate(
        feedback_key=str(_row_value(row, "feedback_key") or _row_value(row, "name") or ""),
        template_id=str(_row_value(row, "template_id") or ""),
        page_type=str(_row_value(row, "page_type") or "Page"),
        doctype=str(_target_doctype(row) or ""),
        module=str(_row_value(row, "module") or ""),
        catalog_version=str(_row_value(row, "catalog_version") or "1"),
        selected_count=_int_value(row, "selected_count"),
        helpful_count=_int_value(row, "helpful_count"),
        not_relevant_count=_int_value(row, "not_relevant_count"),
        too_generic_count=_int_value(row, "too_generic_count"),
        dismissed_count=_int_value(row, "dismissed_count"),
        last_outcome=str(_row_value(row, "last_outcome") or ""),
        last_seen_at=str(_row_value(row, "last_seen_at") or ""),
    )


def _candidate_from_row(row: Any) -> CatalogCandidate:
    values = {field_name: _row_value(row, field_name) for field_name in CatalogCandidate.__dataclass_fields__}
    values["doctype"] = _target_doctype(row)
    values["required_fields"] = _split_fields(values.get("required_fields"))
    for key in CatalogCandidate.__dataclass_fields__:
        if key == "required_fields":
            continue
        if key in {"priority", "intent_type", "source_feedback_key", "feedback_summary", "catalog_version", "proposed_version", "source_ref", "validation_status", "validation_message", "status", "generated_at", "approved_by", "approved_at"}:
            values[key] = str(values.get(key) or "")
    for key in ("candidate_key", "base_template_key", "title", "prompt_template", "category", "page_type", "action_type", "reason"):
        values[key] = str(values.get(key) or "")
    return CatalogCandidate(**values)


def _candidate_row(candidate: CatalogCandidate) -> dict[str, Any]:
    values = candidate.as_dict()
    values["target_doctype"] = values.pop("doctype", "")
    return values


def _snapshot_from_row(row: Any) -> CatalogSnapshot:
    manifest = _json_object(_row_value(row, "manifest_json"))
    keys = manifest.get("template_keys") if isinstance(manifest.get("template_keys"), list) else []
    return CatalogSnapshot(
        snapshot_key=str(_row_value(row, "snapshot_key") or _row_value(row, "name") or ""),
        version=str(_row_value(row, "version") or "1"),
        template_keys=tuple(str(value) for value in keys if value),
        status=str(_row_value(row, "status") or "Retired"),
        source_candidate=str(_row_value(row, "source_candidate") or ""),
        published_by=str(_row_value(row, "published_by") or ""),
        published_at=str(_row_value(row, "published_at") or ""),
        rollback_of=str(_row_value(row, "rollback_of") or ""),
        notes=str(_row_value(row, "notes") or ""),
    )


def _feedback_row(feedback: FeedbackAggregate) -> dict[str, Any]:
    values = asdict(feedback)
    values["target_doctype"] = values.pop("doctype", "")
    return values


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _target_doctype(row: Any) -> str:
    value = _row_value(row, "target_doctype")
    if value:
        return str(value)
    return str(row.get("doctype") or "") if isinstance(row, dict) else ""


def _int_value(row: Any, key: str) -> int:
    try:
        return int(_row_value(row, key) or 0)
    except (TypeError, ValueError):
        return 0


def _split_fields(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(item.strip() for item in str(value or "").replace(",", "\n").splitlines() if item.strip())


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
