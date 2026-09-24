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
    """Return the approved read-only catalog for installed page contexts."""
    return AdvisorCatalog((*_legacy_catalog_templates(), *_standard_doctype_templates()))


def _legacy_catalog_templates() -> tuple[AdvisorTemplate, ...]:
    """Keep the original high-value entries stable while expanding coverage."""
    return (
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


def _standard_doctype_templates() -> tuple[AdvisorTemplate, ...]:
    """Build field-gated entries from the supplied cross-app catalog."""
    templates: list[AdvisorTemplate] = []
    for definition in _DOCTYPE_DEFINITIONS:
        doctype = definition["doctype"]
        fields = tuple(definition.get("required_fields", ()))
        family = definition["family"]
        category = definition["category"]
        priority = definition.get("priority", "normal")
        for page_type, intent_type in (("List", "read_only_list_analysis"), ("Form", "read_only_record_analysis")):
            suffix = "list" if page_type == "List" else "form"
            templates.extend(
                (
                    AdvisorTemplate(
                        key=f"catalog.{family}.{_slug(doctype)}.{suffix}.review",
                        title=definition["action_title"],
                        prompt_template=definition["action_prompt"],
                        category=category,
                        page_type=page_type,
                        doctype=doctype,
                        action_type="review",
                        reason=definition["action_reason"],
                        required_fields=fields,
                        priority=priority,
                        intent_type=intent_type,
                    ),
                    AdvisorTemplate(
                        key=f"catalog.{family}.{_slug(doctype)}.{suffix}.question",
                        title=definition["question_title"],
                        prompt_template=definition["question_prompt"],
                        category=category,
                        page_type=page_type,
                        doctype=doctype,
                        action_type="question",
                        reason=definition["question_reason"],
                        required_fields=fields,
                        priority=priority,
                        intent_type=intent_type,
                    ),
                )
            )
    return tuple(templates)


_DOCTYPE_DEFINITIONS = (
    {
        "doctype": "DocType",
        "family": "framework",
        "category": "metadata-review",
        "required_fields": ("name",),
        "action_title": "Review this DocType structure",
        "action_prompt": "As of {current_date}, explain the permitted {doctype} schema, links, workflow and effective metadata without suggesting database changes.",
        "action_reason": "Framework metadata guidance is shown only for the actual DocType context.",
        "question_title": "Which fields and links does this DocType define?",
        "question_prompt": "Explain the fields, field types and linked DocTypes available on this {doctype} using the effective site metadata.",
        "question_reason": "The current DocType metadata is the source for this explanation.",
    },
    {
        "doctype": "Workflow",
        "family": "framework",
        "category": "workflow-review",
        "required_fields": ("document_type", "workflow_state_field"),
        "action_title": "Review workflow states and transitions",
        "action_prompt": "As of {current_date}, review the permitted {doctype} states, transitions, roles and approvers; identify gaps without changing workflow configuration.",
        "action_reason": "Workflow guidance is limited to the configured states and roles visible to the current user.",
        "question_title": "Which role can perform the next transition?",
        "question_prompt": "Explain which configured role and transition apply to the current {doctype} workflow state.",
        "question_reason": "The answer must come from the effective workflow definition, not a generic assumption.",
    },
    {
        "doctype": "Customer",
        "family": "sales",
        "category": "customer-review",
        "required_fields": ("customer_name",),
        "action_title": "Review customer activity and balance",
        "action_prompt": "As of {current_date}, prepare a read-only review of this {doctype}'s permitted orders, invoices, payments, overdue balance and recent activity.",
        "action_reason": "Customer guidance is shown when the current record exposes its effective customer identity.",
        "question_title": "What is outstanding for this customer?",
        "question_prompt": "As of {current_date}, explain this customer's permitted outstanding balance and the orders or invoices contributing to it.",
        "question_reason": "The answer must separate ordered, invoiced, paid and outstanding amounts.",
        "priority": "high",
    },
    {
        "doctype": "Supplier",
        "family": "purchasing",
        "category": "supplier-review",
        "required_fields": ("supplier_name",),
        "action_title": "Review supplier activity and balance",
        "action_prompt": "As of {current_date}, prepare a read-only review of this {doctype}'s permitted purchase orders, receipts, bills, payments and outstanding balance.",
        "action_reason": "Supplier guidance is limited to records the current user can access.",
        "question_title": "Which supplier bills are overdue?",
        "question_prompt": "As of {current_date}, find permitted overdue supplier bills and explain what remains ordered, received and unpaid.",
        "question_reason": "The answer must distinguish receipt, invoice and payment status.",
        "priority": "high",
    },
    {
        "doctype": "Item",
        "family": "inventory",
        "category": "inventory-review",
        "required_fields": ("item_code",),
        "action_title": "Review item availability and setup",
        "action_prompt": "As of {current_date}, review this {doctype}'s permitted warehouse availability, UOM, price, serial or batch and reorder configuration.",
        "action_reason": "Item guidance uses the effective inventory fields available on this site.",
        "question_title": "Where is this item available?",
        "question_prompt": "As of {current_date}, show the permitted availability of this item by warehouse and explain relevant reserved or projected quantities.",
        "question_reason": "Availability must be sourced from permitted stock records, not inferred from the item master alone.",
    },
    {
        "doctype": "Account",
        "family": "accounts",
        "category": "account-review",
        "required_fields": ("account_name",),
        "action_title": "Review account activity",
        "action_prompt": "As of {current_date}, prepare a read-only review of this {doctype}'s type, parent-child structure and permitted ledger activity for the active company and period.",
        "action_reason": "Account guidance must preserve company, period and posted-ledger scope.",
        "question_title": "What makes up this account balance?",
        "question_prompt": "Explain the permitted posted entries and dimensions contributing to this account balance for the active company and date scope.",
        "question_reason": "The answer must distinguish posted ledger activity from draft or planned values.",
    },
    {
        "doctype": "Quotation",
        "family": "sales",
        "category": "quotation-review",
        "required_fields": ("items",),
        "action_title": "Review quotation expiry and follow-up",
        "action_prompt": "As of {current_date}, review this {doctype}'s validity, items, taxes, pricing, status and next conversion step.",
        "action_reason": "Quotation guidance is tied to the actual item table and effective status fields.",
        "question_title": "Is this quotation still valid?",
        "question_prompt": "Explain this quotation's validity, current status, pricing and the next permitted follow-up step.",
        "question_reason": "The answer should use the document's actual expiry and status fields.",
    },
    {
        "doctype": "Sales Order",
        "family": "sales",
        "category": "sales-fulfilment",
        "required_fields": ("items",),
        "action_title": "Review Sales Order fulfilment",
        "action_prompt": "As of {current_date}, review this {doctype} for ordered, delivered, billed and outstanding quantities, linked documents and the next customer follow-up.",
        "action_reason": "Sales Order guidance separates delivery, billing, payment and return states.",
        "question_title": "Has this order been delivered, invoiced and paid?",
        "question_prompt": "As of {current_date}, trace permitted delivery notes, invoices, returns and payments for this {doctype} and state what remains.",
        "question_reason": "The question is grounded in the current order and permitted linked records.",
        "priority": "high",
    },
    {
        "doctype": "Delivery Note",
        "family": "sales",
        "category": "delivery-review",
        "required_fields": ("items",),
        "action_title": "Review delivery fulfilment",
        "action_prompt": "As of {current_date}, review this {doctype}'s delivered quantities, returns, warehouse movement and billing follow-up.",
        "action_reason": "Delivery guidance uses the actual item and warehouse context.",
        "question_title": "What stock changed on this delivery?",
        "question_prompt": "Explain the permitted stock and accounting effects of this submitted {doctype}, including any partial or returned quantities.",
        "question_reason": "Submitted downstream effects must be verified from linked records.",
    },
    {
        "doctype": "Sales Invoice",
        "family": "accounts",
        "category": "receivables-review",
        "required_fields": ("customer", "outstanding_amount"),
        "action_title": "Review invoice payment status",
        "action_prompt": "As of {current_date}, review this {doctype}'s due date, taxes, outstanding amount, allocations, returns and submitted accounting status.",
        "action_reason": "Invoice guidance distinguishes invoice value, paid value, allocations and credits.",
        "question_title": "Is this invoice fully paid?",
        "question_prompt": "As of {current_date}, explain this invoice's submitted, paid, allocated and outstanding amounts and linked payments.",
        "question_reason": "Payment state is calculated from the permitted invoice and allocation records.",
        "priority": "high",
    },
    {
        "doctype": "Material Request",
        "family": "purchasing",
        "category": "procurement-review",
        "required_fields": ("items",),
        "action_title": "Review material request fulfilment",
        "action_prompt": "As of {current_date}, review this {doctype}'s requested items, fulfilment status and linked purchase documents.",
        "action_reason": "Material request guidance is limited to the configured item and status fields.",
        "question_title": "Which requested items are still open?",
        "question_prompt": "Identify permitted requested quantities that remain open and whether a Purchase Order or receipt is linked.",
        "question_reason": "The answer traces only verified linked purchasing records.",
    },
    {
        "doctype": "Request for Quotation",
        "family": "purchasing",
        "category": "procurement-review",
        "required_fields": ("items",),
        "action_title": "Review sourcing progress",
        "action_prompt": "As of {current_date}, review this {doctype}'s suppliers, requested items, responses, validity and sourcing next step.",
        "action_reason": "Sourcing guidance depends on the configured supplier and item tables.",
        "question_title": "Which suppliers have not responded?",
        "question_prompt": "Find permitted suppliers or requested items without a quotation response and explain the next sourcing follow-up.",
        "question_reason": "Only actual RFQ response records should be counted.",
    },
    {
        "doctype": "Supplier Quotation",
        "family": "purchasing",
        "category": "procurement-review",
        "required_fields": ("items",),
        "action_title": "Compare supplier quotation details",
        "action_prompt": "As of {current_date}, review this {doctype}'s supplier, items, currency, taxes, validity and comparable landed-cost inputs.",
        "action_reason": "Supplier quotation comparisons must preserve currency, tax and validity context.",
        "question_title": "How does this quotation compare?",
        "question_prompt": "Compare permitted supplier quotation values for the same items, currency, taxes and validity period where records support it.",
        "question_reason": "Comparisons are shown only when the required sourcing data is available.",
    },
    {
        "doctype": "Purchase Order",
        "family": "purchasing",
        "category": "procurement-review",
        "required_fields": ("items",),
        "action_title": "Review purchase order fulfilment",
        "action_prompt": "As of {current_date}, review this {doctype} for ordered, received, billed and unpaid quantities or amounts and delayed items.",
        "action_reason": "Purchase Order guidance keeps receipt, billing and payment states separate.",
        "question_title": "What remains to receive?",
        "question_prompt": "As of {current_date}, trace permitted receipts, invoices, returns and payments for this {doctype} and explain what remains.",
        "question_reason": "The answer is based on linked purchasing records and current scope.",
        "priority": "high",
    },
    {
        "doctype": "Purchase Receipt",
        "family": "purchasing",
        "category": "procurement-review",
        "required_fields": ("items",),
        "action_title": "Check purchase receipt matching",
        "action_prompt": "As of {current_date}, compare this {doctype}'s received quantities with linked purchase orders and billing status.",
        "action_reason": "Receipt review must distinguish received, returned and invoiced quantities.",
        "question_title": "Are there quantity differences?",
        "question_prompt": "Identify permitted differences between this receipt and its linked purchase order, including items not yet billed.",
        "question_reason": "Quantity comparisons use actual linked documents.",
    },
    {
        "doctype": "Purchase Invoice",
        "family": "accounts",
        "category": "payables-review",
        "required_fields": ("supplier", "outstanding_amount"),
        "action_title": "Review supplier invoice status",
        "action_prompt": "As of {current_date}, review this {doctype}'s due date, taxes, outstanding amount, receipt matching and payment allocations.",
        "action_reason": "Payables guidance preserves supplier, receipt, invoice and payment distinctions.",
        "question_title": "What is still outstanding on this bill?",
        "question_prompt": "Explain this supplier invoice's permitted due, paid, allocated and outstanding amounts and linked receipts or payments.",
        "question_reason": "The answer comes from the invoice and permitted linked records.",
        "priority": "high",
    },
    {
        "doctype": "Payment Entry",
        "family": "accounts",
        "category": "payment-review",
        "required_fields": ("payment_type",),
        "action_title": "Review payment allocation",
        "action_prompt": "As of {current_date}, review this {doctype}'s payment mode, party, allocated references, unallocated amount and affected accounts.",
        "action_reason": "Payment guidance distinguishes advances from allocated settlements.",
        "question_title": "Is this payment fully allocated?",
        "question_prompt": "Explain which permitted invoices or bills this payment settles and whether any amount remains unallocated.",
        "question_reason": "Allocation is verified from the payment references, not guessed from the amount.",
    },
    {
        "doctype": "Journal Entry",
        "family": "accounts",
        "category": "journal-review",
        "required_fields": ("accounts",),
        "action_title": "Review journal entry balance",
        "action_prompt": "As of {current_date}, review this {doctype}'s debit and credit lines, dimensions, company, status and linked source documents.",
        "action_reason": "Journal review preserves account and dimension context.",
        "question_title": "Is this journal entry balanced?",
        "question_prompt": "Check whether this permitted {doctype} balances and explain the accounts and dimensions affected.",
        "question_reason": "Balance and ledger effects must be calculated from the actual account lines.",
    },
    {
        "doctype": "Stock Entry",
        "family": "inventory",
        "category": "stock-review",
        "required_fields": ("items",),
        "action_title": "Review stock movement",
        "action_prompt": "As of {current_date}, review this {doctype}'s purpose, source and target warehouses, quantities, UOM and serial or batch details.",
        "action_reason": "Stock movement guidance is tied to the actual warehouse and item tables.",
        "question_title": "Which warehouses changed?",
        "question_prompt": "Explain the permitted source and target warehouse movements and what stock ledger effect this submitted {doctype} created.",
        "question_reason": "Submitted stock effects must be traced from the actual document.",
    },
    {
        "doctype": "Stock Reconciliation",
        "family": "inventory",
        "category": "stock-review",
        "required_fields": ("items",),
        "action_title": "Review stock reconciliation differences",
        "action_prompt": "As of {current_date}, compare this {doctype}'s counted and system quantities, warehouses, valuation and approval status.",
        "action_reason": "Reconciliation guidance highlights adjustments before submission without changing data.",
        "question_title": "Which items differ from book stock?",
        "question_prompt": "Identify permitted item quantity or valuation differences in this {doctype} and explain the expected stock impact.",
        "question_reason": "The result should show the counted-versus-system evidence behind each difference.",
    },
    {
        "doctype": "Warehouse",
        "family": "inventory",
        "category": "warehouse-review",
        "required_fields": ("warehouse_name",),
        "action_title": "Review warehouse stock position",
        "action_prompt": "As of {current_date}, summarize permitted stock quantity and value for this {doctype}, including child warehouses and movement gaps.",
        "action_reason": "Warehouse guidance follows the configured tree and permitted stock scope.",
        "question_title": "Which items need attention in this warehouse?",
        "question_prompt": "Find permitted items below minimum levels or with no recent movement in this warehouse.",
        "question_reason": "Only configured reorder and movement signals should be used.",
    },
    {
        "doctype": "Serial No",
        "family": "inventory",
        "category": "serial-review",
        "required_fields": ("item_code",),
        "action_title": "Trace serial number history",
        "action_prompt": "As of {current_date}, review this {doctype}'s item, warehouse, warranty, expiry and permitted movement history.",
        "action_reason": "Serial guidance is restricted to the current serial record and linked transactions.",
        "question_title": "Where did this serial number move?",
        "question_prompt": "Trace the permitted receipt, issue, transfer and current-location history for this serial number.",
        "question_reason": "Movement history must be linked to actual stock transactions.",
    },
    {
        "doctype": "Batch",
        "family": "inventory",
        "category": "batch-review",
        "required_fields": ("item",),
        "action_title": "Review batch expiry and movement",
        "action_prompt": "As of {current_date}, review this {doctype}'s item, expiry, warranty and permitted warehouse movement information.",
        "action_reason": "Batch guidance uses configured expiry and movement data only.",
        "question_title": "What is this batch movement history?",
        "question_prompt": "Summarize the permitted receipts, issues, transfers, expiry and current locations for this batch.",
        "question_reason": "The answer must use actual batch-linked stock records.",
    },
    {
        "doctype": "Work Order",
        "family": "manufacturing",
        "category": "production-review",
        "required_fields": ("production_item", "qty"),
        "action_title": "Review production progress",
        "action_prompt": "As of {current_date}, review this {doctype}'s planned, in-process and completed quantities, material availability and delayed operations.",
        "action_reason": "Manufacturing guidance is limited to permitted production and material signals.",
        "question_title": "What is blocking this Work Order?",
        "question_prompt": "Identify permitted missing materials, delayed operations or remaining quantities blocking this Work Order.",
        "question_reason": "Blocking conditions must be supported by current Work Order and stock data.",
        "priority": "high",
    },
    {
        "doctype": "BOM",
        "family": "manufacturing",
        "category": "production-review",
        "required_fields": ("items",),
        "action_title": "Review BOM requirements",
        "action_prompt": "As of {current_date}, review this {doctype}'s component requirements, operations, versions and permitted warehouse availability.",
        "action_reason": "BOM guidance uses the effective component and operation structure.",
        "question_title": "What changed in this BOM?",
        "question_prompt": "Explain the active BOM components and compare them with permitted production or stock requirements where available.",
        "question_reason": "The answer distinguishes configured BOM data from live warehouse availability.",
    },
    {
        "doctype": "Asset",
        "family": "assets",
        "category": "asset-review",
        "required_fields": ("asset_name",),
        "action_title": "Review asset status and value",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s status, category, location, custodian, book value, depreciation and maintenance signals.",
        "action_reason": "Asset guidance keeps acquisition, depreciation, transfer and disposal states distinct.",
        "question_title": "What is the current book value of this asset?",
        "question_prompt": "Explain this asset's permitted acquisition, depreciation, current book value and linked accounting records.",
        "question_reason": "Book value must be derived from configured asset accounting data.",
    },
    {
        "doctype": "Project",
        "family": "projects",
        "category": "project-review",
        "required_fields": ("status",),
        "action_title": "Review project progress",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s progress, open tasks, logged hours, milestones and budget signals.",
        "action_reason": "Project guidance is limited to permitted tasks, timesheets and budget fields.",
        "question_title": "Which project milestones are at risk?",
        "question_prompt": "Identify overdue tasks, missing updates or planned-versus-logged time signals that may put this project at risk.",
        "question_reason": "Risk is presented as an indicator with the supporting task or time evidence.",
    },
    {
        "doctype": "Task",
        "family": "projects",
        "category": "task-review",
        "required_fields": ("status",),
        "action_title": "Review task progress",
        "action_prompt": "As of {current_date}, review this {doctype}'s status, dates, owner, dependencies and recent updates.",
        "action_reason": "Task suggestions use the current status and schedule fields.",
        "question_title": "Which task is due next?",
        "question_prompt": "Explain the next due date, owner, dependency and permitted follow-up for this task or its project.",
        "question_reason": "The answer should use actual task dates and links.",
    },
    {
        "doctype": "Lead",
        "family": "crm",
        "category": "crm-follow-up",
        "required_fields": ("status",),
        "action_title": "Review lead follow-up",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s source, owner, status, activity, next task and configured qualification path.",
        "action_reason": "CRM guidance keeps Lead workflow separate from ERPNext selling documents.",
        "question_title": "What should I do next with this lead?",
        "question_prompt": "Identify the next permitted follow-up for this lead, including owner, last activity and missing next task.",
        "question_reason": "The recommendation is based on the actual CRM activity timeline.",
        "priority": "high",
    },
    {
        "doctype": "Deal",
        "family": "crm",
        "category": "crm-pipeline",
        "required_fields": ("stage",),
        "action_title": "Review deal health",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s value, stage, owner, close date, activity and verified linked records.",
        "action_reason": "Deal guidance does not assume an ERPNext conversion or integration unless links exist.",
        "question_title": "Is this deal stalled?",
        "question_prompt": "Check permitted activity, next task, stage age and close date signals for this deal and explain the next follow-up.",
        "question_reason": "Stalled is treated as an indicator requiring review, not a causal conclusion.",
    },
    {
        "doctype": "Contact",
        "family": "crm",
        "category": "crm-relationship",
        "required_fields": (),
        "action_title": "Review contact relationships",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s permitted linked leads, deals, organization and recent activity.",
        "action_reason": "Contact guidance is limited to linked CRM records visible to the current user.",
        "question_title": "Which open deals are linked to this contact?",
        "question_prompt": "List permitted open deals, tasks and recent interactions linked to this contact.",
        "question_reason": "Only actual CRM links should be presented.",
    },
    {
        "doctype": "Organization",
        "family": "crm",
        "category": "crm-relationship",
        "required_fields": (),
        "action_title": "Review organization pipeline",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s permitted contacts, leads, deals, activities and configured ERPNext links.",
        "action_reason": "CRM organization guidance keeps integrations explicit and verified.",
        "question_title": "What deals are open for this organization?",
        "question_prompt": "Summarize permitted open deals, contacts and follow-up activity associated with this organization.",
        "question_reason": "The answer is based on actual CRM relationships.",
    },
    {
        "doctype": "POS Profile",
        "family": "pos",
        "category": "pos-setup",
        "required_fields": ("company",),
        "action_title": "Review POS Profile setup",
        "action_prompt": "As of {current_date}, explain this {doctype}'s company, warehouse, price list, customer, taxes, payment modes and print behavior without changing it.",
        "action_reason": "POS suggestions are shown only for the actual configured profile.",
        "question_title": "Which warehouse and payment modes apply?",
        "question_prompt": "Explain the configured warehouse, price list, taxes and payment modes for this POS Profile and who can use it.",
        "question_reason": "Configuration is read from the effective POS Profile fields.",
    },
    {
        "doctype": "POS Invoice",
        "family": "pos",
        "category": "pos-review",
        "required_fields": ("items",),
        "action_title": "Review POS transaction status",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s items, taxes, discounts, payments, returns and transaction status.",
        "action_reason": "POS guidance uses the actual transaction DocType configured on this site.",
        "question_title": "Was this POS transaction paid?",
        "question_prompt": "Explain whether this POS transaction is paid, partially paid, returned, refunded or cancelled using permitted records.",
        "question_reason": "Payment and return state must be verified from the transaction.",
    },
    {
        "doctype": "POS Closing Entry",
        "family": "pos",
        "category": "pos-reconciliation",
        "required_fields": ("pos_profile",),
        "action_title": "Review POS closing reconciliation",
        "action_prompt": "As of {current_date}, review this {doctype}'s cashier, profile, period, payment modes, counted totals and system totals.",
        "action_reason": "Closing guidance is limited to the actual POS closing process supported by this site.",
        "question_title": "Why do the cash and system totals differ?",
        "question_prompt": "Compare permitted included transactions, payment modes and counted-versus-system totals for this POS closing.",
        "question_reason": "Differences are shown with included or excluded transaction evidence where available.",
    },
    {
        "doctype": "Employee",
        "family": "people",
        "category": "hr-review",
        "required_fields": ("employee_name",),
        "action_title": "Review employee record",
        "action_prompt": "As of {current_date}, summarize only the permitted employment, department, reporting line, lifecycle and linked record details for this {doctype}.",
        "action_reason": "HR suggestions follow employee self-service, reporting and role permissions.",
        "question_title": "What is this employee's current status?",
        "question_prompt": "Explain the permitted employment status, department, reporting line and lifecycle records for this employee.",
        "question_reason": "Sensitive HR details are only included when authorized and relevant.",
    },
    {
        "doctype": "Leave Application",
        "family": "people",
        "category": "hr-approval",
        "required_fields": ("from_date", "to_date", "status"),
        "action_title": "Review leave approval status",
        "action_prompt": "As of {current_date}, review this {doctype}'s dates, balance, overlap, workflow state, approver and payroll-cutoff relevance.",
        "action_reason": "Leave guidance respects employee scope and configured approval workflow.",
        "question_title": "Who must approve this leave?",
        "question_prompt": "Explain this leave request's permitted dates, workflow state, approver and any configured holiday overlap.",
        "question_reason": "The answer uses the configured HR workflow and date rules.",
        "priority": "high",
    },
    {
        "doctype": "Attendance",
        "family": "people",
        "category": "hr-attendance",
        "required_fields": ("attendance_date", "status"),
        "action_title": "Review attendance exception",
        "action_prompt": "As of {current_date}, review this {doctype}'s date, employee scope, status and available check-in evidence.",
        "action_reason": "Attendance guidance is limited to authorized employee and department scope.",
        "question_title": "Why is this marked absent or late?",
        "question_prompt": "Explain the permitted attendance status and available check-in or shift evidence for this record.",
        "question_reason": "The answer should show the evidence used without exposing unrelated employee data.",
    },
    {
        "doctype": "Salary Slip",
        "family": "people",
        "category": "hr-payroll",
        "required_fields": ("start_date", "end_date"),
        "action_title": "Review salary slip status",
        "action_prompt": "As of {current_date}, review only the authorized period, employee scope, configured components and submitted status for this {doctype}.",
        "action_reason": "Compensation details are restricted to authorized HR or employee self-service scope.",
        "question_title": "Which components make up this amount?",
        "question_prompt": "Explain the configured salary components and period totals for this slip only when the current user is authorized.",
        "question_reason": "The response must not expose salary details outside native permissions.",
    },
    {
        "doctype": "Payroll Entry",
        "family": "people",
        "category": "hr-payroll",
        "required_fields": ("start_date", "end_date", "status"),
        "action_title": "Review payroll readiness",
        "action_prompt": "As of {current_date}, review this {doctype}'s period, company, validation state and authorized payroll readiness signals without exposing unnecessary salary data.",
        "action_reason": "Payroll guidance follows HR role and company scope.",
        "question_title": "What is blocking payroll?",
        "question_prompt": "Identify permitted payroll validation, employee inclusion or period issues that must be resolved before submission.",
        "question_reason": "The answer is a read-only readiness check.",
        "priority": "high",
    },
    {
        "doctype": "Expense Claim",
        "family": "people",
        "category": "hr-expense",
        "required_fields": ("total_claimed_amount", "status"),
        "action_title": "Review expense claim status",
        "action_prompt": "As of {current_date}, review this {doctype}'s approval, reimbursement, accounting state and authorized amounts separately.",
        "action_reason": "Expense guidance distinguishes claimed, approved, paid and outstanding amounts.",
        "question_title": "Is this claim approved and paid?",
        "question_prompt": "Explain this claim's permitted approval, reimbursement and accounting status, including any outstanding amount.",
        "question_reason": "The answer follows the actual workflow and payment fields.",
    },
    {
        "doctype": "Job Applicant",
        "family": "people",
        "category": "hr-recruitment",
        "required_fields": ("status",),
        "action_title": "Review recruitment follow-up",
        "action_prompt": "As of {current_date}, summarize this {doctype}'s stage, owner and next permitted recruitment action without exposing unnecessary personal data.",
        "action_reason": "Recruitment suggestions use authorized candidate scope only.",
        "question_title": "What is the next hiring step?",
        "question_prompt": "Explain the configured next recruitment step, owner and follow-up status for this applicant.",
        "question_reason": "The answer is based on the actual recruitment workflow.",
    },
)


def _slug(value: str) -> str:
    return "-".join(part.lower() for part in str(value).replace("/", " ").split() if part)


def _action_label(action_type: str) -> str:
    return {
        "question": "Analyze",
        "review": "Review",
        "analyze": "Analyze",
        "navigate": "Navigate",
        "filter": "Filter",
    }.get(action_type, "Review")
