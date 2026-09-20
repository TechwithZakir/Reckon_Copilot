app_name = "reckon_copilot"
app_title = "Reckon Copilot"
app_publisher = "Reckon Technologies Ltd."
app_description = "Reckon Copilot foundation for Frappe and ERPNext v16+"
app_email = "hello@reckon.tech"
app_license = "Proprietary"
app_version = "0.0.1"

required_apps = ["frappe", "erpnext"]


def after_install():
    """Installation hook reserved for Phase 0 validation."""
    return None


def before_uninstall():
    """Uninstall hook reserved for Phase 0 validation."""
    return None

