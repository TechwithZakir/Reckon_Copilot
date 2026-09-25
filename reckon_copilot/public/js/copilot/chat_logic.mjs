export function normalizeAskResponse(response) {
  if (!response) {
    return {
      role: "assistant",
      tone: "warning",
      text: "Copilot did not return a response. Please try again.",
    };
  }
  if (response.access_denied) {
    return {
      role: "assistant",
      tone: "warning",
      text: response.message || "Copilot cannot access this page with your current permissions.",
    };
  }
  if (response.provider_error) {
    return {
      role: "assistant",
      tone: "warning",
      text: response.message || "The local provider is not ready yet.",
    };
  }
  const answer = response.answer?.answer || response.message || "";
  return {
    role: "assistant",
    tone: "normal",
    text: answer || "I could not produce an answer for that question.",
    meta: {
      source: response.answer?.source,
      confidence: response.answer?.confidence,
      cacheHit: Boolean(response.cache_hit),
      provider: response.provider,
      model: response.model,
      intent: response.intent,
      evidence: Array.isArray(response.evidence) ? response.evidence : [],
      followups: Array.isArray(response.answer?.followups) ? response.answer.followups : [],
      warnings: Array.isArray(response.answer?.warnings) ? response.answer.warnings : [],
    },
  };
}

export function normalizeAnalyticsResponse(response) {
  if (!response) {
    return {
      role: "assistant",
      tone: "warning",
      text: "Analytics did not return a result. Please try again.",
    };
  }
  if (response.access_denied) {
    return {
      role: "assistant",
      tone: "warning",
      text: response.message || "Analytics cannot access this page with your current permissions.",
    };
  }
  if (!response.ok) {
    return {
      role: "assistant",
      tone: "warning",
      text: response.message || "Analytics could not complete for this page.",
    };
  }
  return {
    role: "assistant",
    tone: "normal",
    text: response.narrative || "No analytical result was found for this page.",
    meta: {
      source: response.source || "Current page",
      provider: "Analytics Agent",
      model: "deterministic",
      intent: response.intent,
      analytics: response,
    },
  };
}

export function normalizeForecastingResponse(response) {
  if (!response) {
    return {
      role: "assistant",
      tone: "warning",
      text: "The Forecasting Agent did not return a result. Please try again.",
    };
  }
  if (typeof response !== "object") {
    return {
      role: "assistant",
      tone: "warning",
      text: "The Forecasting Agent returned an unreadable result. Please try again.",
    };
  }
  if (response.access_denied) {
    return {
      role: "assistant",
      tone: "warning",
      text: response.message || "The Forecasting Agent cannot access this page with your current permissions.",
    };
  }
  if (!response.ok) {
    return {
      role: "assistant",
      tone: "warning",
      text: response.message || "The Forecasting Agent could not complete for this page.",
    };
  }
  const isAnomaly = response.intent === "anomaly";
  return {
    role: "assistant",
    tone: "normal",
    text: response.narrative || (isAnomaly ? "No anomaly result was found." : "No forecast result was found."),
    meta: {
      source: response.source || "Current page",
      provider: "Forecasting Agent",
      model: "deterministic",
      intent: response.intent,
      forecasting: response,
    },
  };
}

export function canAsk(question, context) {
  return Boolean(String(question || "").trim() && context && !context.access_denied);
}
