export function call(method, args = {}) {
  if (!window.frappe?.call) {
    return Promise.reject(new Error("Frappe API is unavailable"));
  }

  return window.frappe.call({ method, args }).then((response) => response.message);
}

export function getShellConfig(pageType) {
  return call("reckon_copilot.api.shell.get_shell_config", { page_type: pageType });
}

export function savePreferences(preferences) {
  return call("reckon_copilot.api.preferences.update_preferences", preferences);
}
