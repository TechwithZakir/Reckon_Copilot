from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


PAGE_TYPES = {"Homepage", "Workspace", "Dashboard", "List", "Form", "Report"}


@dataclass(frozen=True)
class AdvisorTemplate:
    """Validated, read-only catalog entry used by the runtime advisor."""

    key: str
    title: str
    prompt_template: str
    category: str
    page_type: str
    action_type: str
    reason: str
    doctype: str | None = None
    module: str | None = None
    required_fields: tuple[str, ...] = ()
    priority: str = "normal"
    intent_type: str = "read_only_analysis"
    version: str = "1"
    source_ref: str = "Reckon_Copilot_Suggested_Actions_Catalog.md"
    enabled: bool = True
    approved: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key or not self.title or not self.prompt_template:
            raise ValueError("Advisor templates require a key, title and prompt")
        if self.page_type not in PAGE_TYPES:
            raise ValueError("Advisor template has an unsupported page type")
        if self.intent_type.startswith("write_"):
            raise ValueError("Runtime catalog templates cannot enable write intents")

    def matches(self, context: dict[str, Any], metadata: dict[str, Any]) -> bool:
        if not self.enabled or not self.approved:
            return False
        if context.get("page_type") != self.page_type:
            return False
        if self.doctype and str(context.get("doctype") or "") != self.doctype:
            return False
        if self.module and str(metadata.get("module") or "") != self.module:
            return False
        available_fields = {
            str(value).strip().lower()
            for value in metadata.get("field_names") or []
            if str(value).strip()
        }
        if self.required_fields and not {
            field.lower() for field in self.required_fields
        }.issubset(available_fields):
            return False
        status = self.metadata.get("status")
        if status and str(context.get("status") or "") != str(status):
            return False
        return True

    def recommendation(self, context: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        label = str(
            context.get("doctype")
            or context.get("report_name")
            or context.get("dashboard_name")
            or context.get("workspace_name")
            or context.get("homepage_name")
            or "this page"
        )
        prompt = self.prompt_template.format(
            current_date=str(metadata.get("current_date") or "today")[:20],
            label=label,
            doctype=str(context.get("doctype") or label),
            document_name=str(context.get("document_name") or "the current record"),
        )
        return {
            "id": self.key,
            "title": self.title,
            "prompt": prompt[:1200],
            "category": self.category,
            "reason": self.reason[:300],
            "source": "catalog",
            "source_label": "Approved action catalog",
            "source_ref": self.source_ref,
            "priority": self.priority,
            "action_type": self.action_type,
            "action_label": _action_label(self.action_type),
            "execution": "prompt",
            "requires_confirmation": False,
            "intent_type": self.intent_type,
            "catalog_version": self.version,
        }


class AdvisorCatalog:
    """Stable catalog interface; stored Frappe templates can replace it later."""

    def __init__(self, templates: Iterable[AdvisorTemplate] = ()):
        self.templates = tuple(templates)

    def questions_for(self, context: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            template.recommendation(context, metadata)
            for template in self.templates
            if template.action_type == "question" and template.matches(context, metadata)
        ]

    def actions_for(self, context: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            template.recommendation(context, metadata)
            for template in self.templates
            if template.action_type != "question" and template.matches(context, metadata)
        ]


def default_catalog() -> AdvisorCatalog:
    """Return approved, read-only entries derived from the Phase 9 catalog."""
    return AdvisorCatalog(
        (
            AdvisorTemplate(
                key="erpnext.sales_order.list.unfulfilled",
                title="Find unfulfilled Sales Orders",
                prompt_template=(
                    "As of {current_date}, find permitted {doctype} records that are not fully delivered or billed. "
                    "Show the scope used and the next fulfilment follow-up."
                ),
                category="sales-fulfilment",
                page_type="List",
                doctype="Sales Order",
                action_type="question",
                reason="The current Sales Order list can support a fulfilment review when its status fields are available.",
                required_fields=("status",),
                priority="high",
                intent_type="read_only_list_analysis",
            ),
            AdvisorTemplate(
                key="erpnext.sales_order.form.fulfilment",
                title="What remains to deliver on this order?",
                prompt_template=(
                    "As of {current_date}, review {doctype} {document_name} and explain ordered, delivered and "
                    "outstanding quantities using permitted linked records."
                ),
                category="sales-fulfilment",
                page_type="Form",
                doctype="Sales Order",
                action_type="question",
                reason="This question is available because the Sales Order form exposes its item table.",
                required_fields=("items",),
                priority="high",
                intent_type="read_only_record_analysis",
            ),
            AdvisorTemplate(
                key="erpnext.sales_invoice.list.overdue",
                title="Review overdue Sales Invoices",
                prompt_template=(
                    "As of {current_date}, review permitted {doctype} records with a past due date and outstanding "
                    "amount. Separate submitted, partially paid and fully paid records."
                ),
                category="receivables-review",
                page_type="List",
                doctype="Sales Invoice",
                action_type="question",
                reason="The Sales Invoice list can support an overdue review when due-date and outstanding fields exist.",
                required_fields=("due_date", "outstanding_amount"),
                priority="high",
                intent_type="read_only_list_analysis",
            ),
            AdvisorTemplate(
                key="erpnext.item.list.reorder",
                title="Find items below reorder level",
                prompt_template=(
                    "As of {current_date}, identify permitted {doctype} records below their configured reorder level "
                    "and explain which warehouse or stock signal needs attention."
                ),
                category="inventory-review",
                page_type="List",
                doctype="Item",
                action_type="question",
                reason="This inventory question is shown only when the current Item schema exposes stock configuration fields.",
                required_fields=("is_stock_item",),
                priority="normal",
                intent_type="read_only_list_analysis",
            ),
            AdvisorTemplate(
                key="erpnext.purchase_order.form.receipt",
                title="What remains to receive on this order?",
                prompt_template=(
                    "As of {current_date}, review Purchase Order {document_name} and explain ordered, received and "
                    "outstanding quantities using permitted linked records."
                ),
                category="procurement-review",
                page_type="Form",
                doctype="Purchase Order",
                action_type="question",
                reason="This procurement question is available when the Purchase Order item table is present.",
                required_fields=("items",),
                priority="high",
                intent_type="read_only_record_analysis",
            ),
            AdvisorTemplate(
                key="erpnext.sales_order.list.follow_up",
                title="Prepare Sales Order follow-up",
                prompt_template=(
                    "As of {current_date}, prepare a read-only follow-up review for the permitted {doctype} list. "
                    "Prioritize delivery, billing and customer issues visible in the current scope."
                ),
                category="sales-operations",
                page_type="List",
                doctype="Sales Order",
                action_type="review",
                reason="The approved catalog maps Sales Order lists to delivery, billing and customer follow-up.",
                required_fields=("status",),
                priority="high",
                intent_type="read_only_list_analysis",
            ),
            AdvisorTemplate(
                key="erpnext.sales_invoice.list.receivables",
                title="Prepare receivables review",
                prompt_template=(
                    "As of {current_date}, prepare a read-only receivables review for the permitted {doctype} list. "
                    "Separate overdue, partially paid and unallocated amounts using the active scope."
                ),
                category="receivables-review",
                page_type="List",
                doctype="Sales Invoice",
                action_type="review",
                reason="The approved catalog maps Sales Invoice lists to outstanding and payment-allocation review.",
                required_fields=("outstanding_amount",),
                priority="high",
                intent_type="read_only_list_analysis",
            ),
        )
    )


def _action_label(action_type: str) -> str:
    return {
        "question": "Analyze",
        "review": "Review",
        "analyze": "Analyze",
        "navigate": "Navigate",
        "filter": "Filter",
    }.get(action_type, "Review")
