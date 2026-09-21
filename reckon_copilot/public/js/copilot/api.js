export function call(method, args = {}) {
  if (!window.frappe?.call) {
    return Promise.reject(new Error("Frappe API is unavailable"));
  }

  return new Promise((resolve, reject) => {
    window.frappe.call({
      method,
      args,
      callback: (response) => resolve(response.message),
      error: (error) => reject(normalizeFrappeError(error)),
    });
  });
}

function normalizeFrappeError(error) {
  const message =
    error?._server_messages ||
    error?.responseJSON?._server_messages ||
    error?.responseJSON?.exception ||
    error?.exception ||
    error?.message ||
    "Request failed";
  return new Error(String(message));
}

export function getShellConfig(pageType) {
  return call("reckon_copilot.api.shell.get_shell_config", { page_type: pageType });
}

export function getRouteContext(route, filters = {}, pageType = "Page") {
  return call("reckon_copilot.api.context.get_context", {
    route,
    filters,
    page_type: pageType,
  });
}

export function savePreferences(preferences) {
  return call("reckon_copilot.api.preferences.update_preferences", preferences);
}

export function askCopilot(question, context, evidence = []) {
  return call("reckon_copilot.api.ask.ask", {
    question,
    context,
    evidence,
  });
}
