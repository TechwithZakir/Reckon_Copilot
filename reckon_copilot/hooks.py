app_name = "reckon_copilot"
app_title = "Reckon Copilot"
app_publisher = "Reckon Technologies Ltd."
app_description = "Reckon Copilot for Frappe and ERPNext v16+"
app_email = "hello@reckon.tech"
app_license = "Proprietary"
app_version = "0.0.1"
app_icon_title = "Reckon Copilot"
app_icon_route = "/desk/reckon-copilot"

required_apps = ["frappe", "erpnext"]

app_include_js = ["reckon_copilot_v2.bundle.js"]
app_include_css = ["/assets/reckon_copilot/css/copilot_v2.css"]

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "route": app_icon_route,
        "desk_route": app_icon_route,
        "has_permission": "reckon_copilot.api.shell.can_access_copilot_app",
        "sequence_id": 30,
    }
]

after_migrate = ["reckon_copilot.patches.v0_1.sync_desktop_app_icon.execute"]


def after_install():
    """Ensure Desk app icon exists after fresh install."""
    try:
        from reckon_copilot.patches.v0_1.sync_desktop_app_icon import execute

        execute()
    except Exception:
        return None
    return None


def before_uninstall():
    """Uninstall hook reserved for Phase 0 validation."""
    return None
