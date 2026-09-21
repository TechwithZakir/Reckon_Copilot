"""Keep the Reckon Copilot Desktop Icon available on Frappe Desk."""

from __future__ import annotations

LABEL = "Reckon Copilot"


def execute():
    import frappe  # type: ignore

    if not frappe.db.exists("DocType", "Desktop Icon"):
        return

    fields = {field.fieldname for field in frappe.get_meta("Desktop Icon").fields}
    values = {
        "label": LABEL,
        "app": "reckon_copilot",
        "standard": 1,
        "icon_type": "Link",
        "link_type": "Workspace Sidebar",
        "link_to": LABEL,
        "link": None,
        "icon": "sparkles",
        "hidden": 0,
        "restrict_removal": 1,
        "parent_icon": None,
        "sidebar": None,
    }
    values = {field: value for field, value in values.items() if field in fields or field == "label"}

    if frappe.db.exists("Desktop Icon", LABEL):
        frappe.db.set_value("Desktop Icon", LABEL, values, update_modified=False)
    else:
        frappe.get_doc({"doctype": "Desktop Icon", **values}).insert(ignore_permissions=True)

    _sync_roles(frappe)
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")


def _sync_roles(frappe):
    if not frappe.db.exists("Desktop Icon", LABEL):
        return
    doc = frappe.get_doc("Desktop Icon", LABEL)
    if hasattr(doc, "roles"):
        doc.set("roles", [])
        doc.append("roles", {"role": "System Manager"})
        doc.save(ignore_permissions=True)
