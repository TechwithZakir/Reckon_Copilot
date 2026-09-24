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

async function callSilent(method, args = {}) {
  const body = new URLSearchParams();
  for (const [key, value] of Object.entries(args)) {
    body.append(key, typeof value === "string" ? value : JSON.stringify(value));
  }
  const response = await fetch(`/api/method/${method}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Frappe-CSRF-Token": window.frappe?.csrf_token || "",
      Accept: "application/json",
    },
    body,
    credentials: "same-origin",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.exc || payload.exception) {
    throw normalizeFrappeError({
      responseJSON: payload,
      message: payload.message,
    });
  }
  return payload.message;
}

function isMissingMethodError(error) {
  return /has no attribute 'ask_stream'|Failed to get method.*ask_stream|ask_stream/i.test(String(error?.message || error));
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

export function getInsights(context, evidence = []) {
  return call("reckon_copilot.api.insights.get_insights", {
    context,
    evidence,
  });
}

export function getNotifications(context, evidence = [], enabled = true) {
  return call("reckon_copilot.api.notifications.get_notifications", {
    context,
    evidence,
    enabled,
  });
}

export function getAgentAdvice(context) {
  return call("reckon_copilot.api.advisor.get_agent_advice", { context });
}

export function recordSuggestionFeedback(templateId, outcome, context, catalogVersion = "1") {
  return call("reckon_copilot.api.catalog_learning.record_suggestion_feedback", {
    template_id: templateId,
    outcome,
    context,
    catalog_version: catalogVersion,
  });
}

export function runAnalytics(question, context) {
  return call("reckon_copilot.api.analytics.run", { question, context });
}

export function runForecasting(question, context, mode = "forecast") {
  return call("reckon_copilot.api.forecasting.run", { question, context, mode });
}

export function previewAction(context, action, values = {}) {
  return call("reckon_copilot.api.actions.preview_action", {
    context,
    action,
    values,
  });
}

export function approvePreview(plan, context) {
  return call("reckon_copilot.api.actions.approve_preview", { plan, context });
}

export function executeAction(plan, approvalToken, context) {
  return call("reckon_copilot.api.actions.execute_action", {
    plan,
    approval_token: approvalToken,
    context,
  });
}

export function savePreferences(preferences) {
  return call("reckon_copilot.api.preferences.update_preferences", preferences);
}

export function askCopilot(question, context, evidence = [], selectedModel = "") {
  return call("reckon_copilot.api.ask.ask", {
    question,
    context,
    evidence,
    selected_model: selectedModel,
  });
}

export function askCopilotStream({ requestId, question, context, evidence = [], selectedModel = "", onEvent }) {
  const realtime = window.frappe?.realtime;
  const canStream = realtime && typeof realtime.on === "function" && typeof realtime.off === "function";
  if (!canStream) {
    return askCopilot(question, context, evidence);
  }

  const eventName = "reckon_copilot_stream";
  const handler = (event) => {
    if (event?.request_id === requestId) {
      onEvent?.(event);
    }
  };
  realtime.on(eventName, handler);
  return callSilent("reckon_copilot.api.ask.ask_stream", {
    request_id: requestId,
    question,
    context,
    evidence,
    selected_model: selectedModel,
  })
    .catch((error) => {
      if (isMissingMethodError(error)) {
        onEvent?.({
          request_id: requestId,
          event: "stage",
          stage: "Composing response",
          percent: 65,
          provider: "LLM provider",
        });
        return askCopilot(question, context, evidence);
      }
      throw error;
    })
    .finally(() => {
      realtime.off(eventName, handler);
    });
}
