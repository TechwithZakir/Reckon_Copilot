from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


CAPABILITY_READ_CONTEXT = "context.read"
CAPABILITY_READ_KNOWLEDGE = "knowledge.read"
CAPABILITY_RUN_ANALYTICS = "analytics.run"
CAPABILITY_CALL_PROVIDER = "provider.call"
CAPABILITY_WRITE_ACTION = "action.write"

READ_ONLY_CAPABILITIES = {
    CAPABILITY_READ_CONTEXT,
    CAPABILITY_READ_KNOWLEDGE,
    CAPABILITY_RUN_ANALYTICS,
    CAPABILITY_CALL_PROVIDER,
}

SENSITIVE_KEYS = {
    "document_name",
    "filters",
    "route",
}


class PermissionDenied(PermissionError):
    """Raised when Copilot context access fails the security boundary."""


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    redacted_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorizedContext:
    context: dict[str, Any]
    decision: AccessDecision


class PermissionAdapter(Protocol):
    def session_user(self) -> str:
        ...

    def user_roles(self, user: str) -> set[str]:
        ...

    def has_doctype_permission(
        self,
        doctype: str,
        permission_type: str,
        user: str,
    ) -> bool:
        ...

    def has_document_permission(
        self,
        doctype: str,
        document_name: str,
        permission_type: str,
        user: str,
    ) -> bool:
        ...

    def has_report_permission(self, report_name: str, user: str) -> bool:
        ...

    def has_workspace_permission(self, workspace_name: str, user: str) -> bool:
        ...

    def workspace_exists(self, workspace_name: str) -> bool:
        ...

    def has_dashboard_permission(self, dashboard_name: str, user: str) -> bool:
        ...

    def user_permissions_allow(
        self,
        doctype: str,
        filters: dict[str, Any],
        user: str,
    ) -> bool:
        ...


class FrappePermissionAdapter:
    """Adapter around native Frappe v16 permission APIs.

    Frappe's native permission entrypoints used here are intentionally centralized:
    `frappe.has_permission`, `frappe.get_roles`, and `frappe.db.exists/get_value`.
    Future Copilot features must call `CopilotPermissionBoundary` instead of calling
    these APIs directly.
    """

    def __init__(self, frappe_module: Any | None = None):
        if frappe_module is None:
            import frappe as frappe_module  # type: ignore
        self.frappe = frappe_module

    def session_user(self) -> str:
        return getattr(self.frappe.session, "user", "Guest")

    def user_roles(self, user: str) -> set[str]:
        return set(self.frappe.get_roles(user) or [])

    def has_doctype_permission(
        self,
        doctype: str,
        permission_type: str,
        user: str,
    ) -> bool:
        return bool(
            self.frappe.has_permission(
                doctype,
                ptype=permission_type,
                user=user,
            )
        )

    def has_document_permission(
        self,
        doctype: str,
        document_name: str,
        permission_type: str,
        user: str,
    ) -> bool:
        try:
            doc = self.frappe.get_doc(doctype, document_name)
        except Exception:
            return False
        return bool(
            self.frappe.has_permission(
                doctype,
                ptype=permission_type,
                doc=doc,
                user=user,
            )
        )

    def has_report_permission(self, report_name: str, user: str) -> bool:
        if not self.frappe.db.exists("Report", report_name):
            return False
        try:
            report = self.frappe.get_doc("Report", report_name)
            if hasattr(report, "is_permitted"):
                return bool(report.is_permitted())
        except Exception:
            pass
        return bool(
            self.frappe.has_permission(
                "Report",
                ptype="read",
                doc=report_name,
                user=user,
            )
        )

    def has_workspace_permission(self, workspace_name: str, user: str) -> bool:
        if not self.frappe.db.exists("Workspace", workspace_name):
            return False
        return bool(
            self.frappe.has_permission(
                "Workspace",
                ptype="read",
                doc=workspace_name,
                user=user,
            )
        )

    def workspace_exists(self, workspace_name: str) -> bool:
        return bool(self.frappe.db.exists("Workspace", workspace_name))

    def has_dashboard_permission(self, dashboard_name: str, user: str) -> bool:
        if self.frappe.db.exists("Dashboard", dashboard_name):
            return bool(
                self.frappe.has_permission(
                    "Dashboard",
                    ptype="read",
                    doc=dashboard_name,
                    user=user,
                )
            )
        # Frappe v16 dashboard-view routes can resolve to a Workspace record.
        if self.frappe.db.exists("Workspace", dashboard_name):
            return bool(
                self.frappe.has_permission(
                    "Workspace",
                    ptype="read",
                    doc=dashboard_name,
                    user=user,
                )
            )
        return False

    def user_permissions_allow(
        self,
        doctype: str,
        filters: dict[str, Any],
        user: str,
    ) -> bool:
        company = filters.get("company") or filters.get("Company")
        if not company:
            return True

        user_permission = self.frappe.db.exists(
            "User Permission",
            {"user": user, "allow": "Company"},
        )
        if not user_permission:
            return True

        allowed = self.frappe.db.exists(
            "User Permission",
            {"user": user, "allow": "Company", "for_value": company},
        )
        return bool(allowed)

    def permission_scope_fragments(self, context: dict[str, Any], user: str) -> dict[str, Any]:
        fragments: dict[str, Any] = {}
        try:
            company_permissions = self.frappe.get_all(
                "User Permission",
                filters={"user": user, "allow": "Company"},
                pluck="for_value",
            )
        except Exception:
            company_permissions = []
        if company_permissions:
            fragments["allowed_companies"] = sorted(str(value) for value in company_permissions)
        return fragments


@dataclass
class StaticPermissionAdapter:
    """Test adapter for proving boundary behavior without a Frappe bench."""

    user: str = "user@example.com"
    roles: set[str] = field(default_factory=lambda: {"Employee"})
    doctype_permissions: dict[tuple[str, str], bool] = field(default_factory=dict)
    document_permissions: dict[tuple[str, str, str], bool] = field(default_factory=dict)
    reports: set[str] = field(default_factory=set)
    workspaces: set[str] = field(default_factory=set)
    dashboards: set[str] = field(default_factory=set)
    allowed_companies: set[str] | None = None

    def session_user(self) -> str:
        return self.user

    def user_roles(self, user: str) -> set[str]:
        return self.roles

    def has_doctype_permission(
        self,
        doctype: str,
        permission_type: str,
        user: str,
    ) -> bool:
        return self.doctype_permissions.get((doctype, permission_type), False)

    def has_document_permission(
        self,
        doctype: str,
        document_name: str,
        permission_type: str,
        user: str,
    ) -> bool:
        return self.document_permissions.get((doctype, document_name, permission_type), False)

    def has_report_permission(self, report_name: str, user: str) -> bool:
        return report_name in self.reports

    def has_workspace_permission(self, workspace_name: str, user: str) -> bool:
        return workspace_name in self.workspaces

    def workspace_exists(self, workspace_name: str) -> bool:
        return workspace_name in self.workspaces

    def has_dashboard_permission(self, dashboard_name: str, user: str) -> bool:
        return dashboard_name in self.dashboards

    def user_permissions_allow(
        self,
        doctype: str,
        filters: dict[str, Any],
        user: str,
    ) -> bool:
        if self.allowed_companies is None:
            return True
        company = filters.get("company") or filters.get("Company")
        return not company or company in self.allowed_companies

    def permission_scope_fragments(self, context: dict[str, Any], user: str) -> dict[str, Any]:
        fragments: dict[str, Any] = {}
        if self.allowed_companies is not None:
            fragments["allowed_companies"] = sorted(self.allowed_companies)
        return fragments


class CopilotPermissionBoundary:
    def __init__(self, adapter: PermissionAdapter):
        self.adapter = adapter

    def authorize(
        self,
        context: dict[str, Any],
        capability: str = CAPABILITY_READ_CONTEXT,
        user: str | None = None,
    ) -> AuthorizedContext:
        user = user or self.adapter.session_user()
        if user == "Guest":
            raise PermissionDenied("Guest users cannot access Copilot context")

        self._assert_capability(capability, user)
        self._assert_context_access(context, user)
        redacted, fields = self.redact_context(context)
        redacted["permission"] = {
            "mode": "frappe_boundary",
            "enforcement": "phase_3",
            "capability": capability,
            "user": user,
            "scope_hash": self.permission_scope_hash(redacted, capability, user),
            "redacted_fields": list(fields),
        }
        return AuthorizedContext(
            context=redacted,
            decision=AccessDecision(True, "allowed", fields),
        )

    def authorize_action(
        self,
        context: dict[str, Any],
        action: str,
        user: str | None = None,
    ) -> AuthorizedContext:
        """Authorize a proposed DocType action through native permission checks.

        This is deliberately separate from context authorization: reading a form
        does not imply that Copilot may suggest or prepare a write operation.
        The eventual executor must call this same boundary immediately before
        mutating ERPNext data.
        """
        action_name = str(action or "").strip().lower()
        if action_name not in {"create", "update", "delete", "submit", "approve"}:
            raise PermissionDenied("Unsupported Copilot action")

        authorized = self.authorize(
            context,
            capability=CAPABILITY_WRITE_ACTION,
            user=user,
        )
        user = user or self.adapter.session_user()
        doctype = _required(authorized.context, "doctype")
        document_name = authorized.context.get("document_name")

        if action_name == "create":
            # Create previews are only valid for an unsaved form. This avoids
            # turning a crafted existing-record request into an insert plan.
            allowed = (
                not document_name or _is_new_document_name(document_name)
            ) and self.adapter.has_doctype_permission(doctype, "create", user)
        elif not document_name or _is_new_document_name(document_name):
            allowed = False
        else:
            permission_type = {
                "update": "write",
                "delete": "delete",
                # Frappe has no generic "approve" ptype. A submit-level
                # permission is the minimum native gate before workflow checks.
                "submit": "submit",
                "approve": "submit",
            }[action_name]
            allowed = self.adapter.has_document_permission(
                doctype,
                str(document_name),
                permission_type,
                user,
            )

        if not allowed:
            raise PermissionDenied(f"No permission to {action_name} requested document")
        return authorized

    def _assert_capability(self, capability: str, user: str) -> None:
        if capability == CAPABILITY_WRITE_ACTION:
            roles = self.adapter.user_roles(user)
            if "System Manager" not in roles:
                raise PermissionDenied("Write actions require System Manager")
            return
        if capability not in READ_ONLY_CAPABILITIES:
            raise PermissionDenied(f"Unsupported Copilot capability: {capability}")

    def _assert_context_access(self, context: dict[str, Any], user: str) -> None:
        page_type = context.get("page_type")
        if page_type == "Form":
            doctype = _required(context, "doctype")
            document_name = context.get("document_name")
            if document_name and not _is_new_document_name(document_name):
                allowed = self.adapter.has_document_permission(doctype, document_name, "read", user)
            else:
                allowed = (
                    self.adapter.has_doctype_permission(doctype, "read", user)
                    or self.adapter.has_doctype_permission(doctype, "create", user)
                )
            if not allowed:
                raise PermissionDenied("No read permission for requested document")
            return

        if page_type == "List":
            doctype = _required(context, "doctype")
            if not self.adapter.has_doctype_permission(doctype, "read", user):
                raise PermissionDenied("No read permission for requested DocType")
            if not self.adapter.user_permissions_allow(doctype, context.get("filters") or {}, user):
                raise PermissionDenied("User Permission blocks requested scope")
            return

        if page_type == "Report":
            report_name = _required(context, "report_name")
            if not self.adapter.has_report_permission(report_name, user):
                raise PermissionDenied("No access to requested report")
            return

        if page_type == "Workspace":
            workspace_name = context.get("workspace_name")
            if workspace_name and not self.adapter.workspace_exists(workspace_name):
                return
            if workspace_name and not self.adapter.has_workspace_permission(workspace_name, user):
                raise PermissionDenied("No access to requested workspace")
            return

        if page_type == "Dashboard":
            dashboard_name = _required(context, "dashboard_name")
            if not self.adapter.has_dashboard_permission(dashboard_name, user):
                raise PermissionDenied("No access to requested dashboard")
            return

        if page_type == "Page":
            return

        if page_type == "Homepage":
            return

        raise PermissionDenied("Unsupported context page type")

    def redact_context(self, context: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
        redacted = dict(context)
        page_type = redacted.get("page_type")
        redacted_fields: list[str] = []

        if page_type != "Form" and redacted.get("document_name"):
            redacted["document_name"] = None
            redacted_fields.append("document_name")

        filters = redacted.get("filters")
        if isinstance(filters, dict):
            clean_filters = {}
            for key, value in filters.items():
                if _is_sensitive_filter(key):
                    clean_filters[key] = "[redacted]"
                    redacted_fields.append(f"filters.{key}")
                else:
                    clean_filters[key] = value
            redacted["filters"] = clean_filters

        route = redacted.get("route")
        if isinstance(route, list) and len(route) > 3:
            redacted["route"] = route[:3]
            redacted_fields.append("route")

        return redacted, tuple(sorted(set(redacted_fields)))

    def permission_scope_hash(
        self,
        context: dict[str, Any],
        capability: str = CAPABILITY_READ_CONTEXT,
        user: str | None = None,
    ) -> str:
        user = user or self.adapter.session_user()
        page_type = context.get("page_type")
        scope = {
            "version": 1,
            "user": user,
            "roles": sorted(self.adapter.user_roles(user)),
            "capability": capability,
            "page_type": page_type,
            "doctype": context.get("doctype"),
            "report_name": context.get("report_name"),
            "workspace_name": context.get("workspace_name"),
            "dashboard_name": context.get("dashboard_name"),
            "company": _filter_value(context.get("filters") or {}, "company"),
            "document_scoped": bool(page_type == "Form" and context.get("document_name")),
        }
        extra_scope = getattr(self.adapter, "permission_scope_fragments", None)
        if callable(extra_scope):
            scope["adapter_scope"] = extra_scope(context, user)
        return _stable_hash(scope)


def _required(context: dict[str, Any], field: str) -> str:
    value = context.get(field)
    if not value:
        raise PermissionDenied(f"Missing required context field: {field}")
    return str(value)


def _is_sensitive_filter(key: Any) -> bool:
    return str(key).lower() in {"password", "api_key", "api_secret", "secret", "token"}


def _is_new_document_name(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("new-")


def _filter_value(filters: dict[str, Any], key: str) -> Any:
    for candidate in (key, key.title(), key.upper()):
        if candidate in filters:
            return filters[candidate]
    return None


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def authorize_context(
    context: dict[str, Any],
    capability: str = CAPABILITY_READ_CONTEXT,
    user: str | None = None,
    adapter: PermissionAdapter | None = None,
) -> AuthorizedContext:
    boundary = CopilotPermissionBoundary(adapter or FrappePermissionAdapter())
    return boundary.authorize(context, capability=capability, user=user)
