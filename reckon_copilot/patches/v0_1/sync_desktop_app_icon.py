"""Keep the Reckon Copilot Desk icon and sidebar available."""

from __future__ import annotations

LABEL = "Reckon Copilot"
ICON_PATH = "/assets/reckon_copilot/images/reckon_copilot.png"


def execute():
    import frappe  # type: ignore

    if frappe.db.exists("DocType", "Workspace Sidebar"):
        _sync_workspace_sidebar(frappe)
    if frappe.db.exists("DocType", "Desktop Icon"):
        _sync_desktop_icon(frappe)

    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("workspace_sidebar")
    frappe.cache.delete_key("bootinfo")


def _sync_desktop_icon(frappe):

    fields = {field.fieldname for field in frappe.get_meta("Desktop Icon").fields}
    sidebar_exists = frappe.db.exists("Workspace Sidebar", LABEL)
    values = {
        "label": LABEL,
        "app": "reckon_copilot",
        "standard": 1,
        "icon_type": "Link",
        "link_type": "Workspace Sidebar" if sidebar_exists else "Route",
        "link_to": LABEL if sidebar_exists else None,
        "link": None if sidebar_exists else "/desk/reckon-copilot",
        "icon": ICON_PATH,
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


def _sync_roles(frappe):
    if not frappe.db.exists("Desktop Icon", LABEL):
        return
    doc = frappe.get_doc("Desktop Icon", LABEL)
    if hasattr(doc, "roles"):
        doc.set("roles", [])
        doc.append("roles", {"role": "System Manager"})
        doc.save(ignore_permissions=True)


def _sync_workspace_sidebar(frappe):
    values = {
        "title": LABEL,
        "app": "reckon_copilot",
        "module": "Reckon Copilot",
        "header_icon": "sparkles",
        "standard": 1,
    }
    if frappe.db.exists("Workspace Sidebar", LABEL):
        doc = frappe.get_doc("Workspace Sidebar", LABEL)
        doc.update(_existing_fields(doc, values))
    else:
        doc = frappe.get_doc({"doctype": "Workspace Sidebar", "name": LABEL, **values})

    if hasattr(doc, "items"):
        doc.set("items", [])
        for item in _sidebar_items():
            doc.append("items", item)
    if getattr(doc, "is_new", lambda: False)():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)


def _existing_fields(doc, values):
    meta = getattr(doc, "meta", None)
    meta_fields = {field.fieldname for field in getattr(meta, "fields", [])}
    if not meta_fields:
        return values
    return {field: value for field, value in values.items() if field in meta_fields}


def _sidebar_items():
    items = [
        ("Home", "Workspace", LABEL, "home", 0, "Link"),
        ("Knowledge", "DocType", "", "database", 0, "Section Break"),
        ("Copilot Knowledge Source", "DocType", "Copilot Knowledge Source", "", 1, "Link"),
        ("Copilot Knowledge Document", "DocType", "Copilot Knowledge Document", "", 1, "Link"),
        ("Copilot Knowledge Chunk", "DocType", "Copilot Knowledge Chunk", "", 1, "Link"),
        ("Copilot Knowledge Ingestion Job", "DocType", "Copilot Knowledge Ingestion Job", "", 1, "Link"),
        ("Copilot Knowledge Vector Index", "DocType", "Copilot Knowledge Vector Index", "", 1, "Link"),
        ("Settings", "DocType", "", "settings", 0, "Section Break"),
        ("Copilot Provider", "DocType", "Copilot Provider", "", 1, "Link"),
        ("Copilot Usage Log", "DocType", "Copilot Usage Log", "", 1, "Link"),
        ("Copilot User Preference", "DocType", "Copilot User Preference", "", 1, "Link"),
    ]
    return [
        {
            "child": child,
            "collapsible": 1,
            "icon": icon,
            "indent": 1 if item_type == "Section Break" else 0,
            "keep_closed": 0,
            "label": label,
            "link_to": link_to,
            "link_type": link_type,
            "show_arrow": 0,
            "type": item_type,
        }
        for label, link_type, link_to, icon, child, item_type in items
    ]
