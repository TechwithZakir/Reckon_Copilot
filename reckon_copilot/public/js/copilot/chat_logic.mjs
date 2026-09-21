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

export function canAsk(question, context) {
  return Boolean(String(question || "").trim() && context && !context.access_denied);
}
