<script setup>
defineProps({
  contextAlert: { type: String, default: "" },
  insights: { type: Array, default: () => [] },
});

const fallbackInsights = [
  {
    finding_id: "fallback-status",
    title: "Review pending document status",
    summary: "Copilot can highlight overdue, blocked or incomplete work once context extraction is enabled.",
    severity: "critical",
  },
  {
    finding_id: "fallback-linked",
    title: "Check linked transactions",
    summary: "Related records and permission-safe summaries are planned for the next context phase.",
    severity: "warning",
  },
  {
    finding_id: "fallback-page",
    title: "Ask about this page",
    summary: "Use suggested prompts to prepare for page-aware assistance without sending record data yet.",
    severity: "info",
  },
];

function insightClass(severity) {
  return `is-${["critical", "warning", "info"].includes(severity) ? severity : "info"}`;
}

function insightMark(severity) {
  return severity === "critical" ? "!" : severity === "warning" ? "+" : "i";
}
</script>

<template>
  <section class="rc-block" aria-labelledby="rc-notifications-title">
    <div class="rc-block-heading">
      <span class="rc-heading-icon" aria-hidden="true">!</span>
      <h3 id="rc-notifications-title">Key Insights</h3>
      <button class="rc-link-button" type="button">View all</button>
    </div>
    <div class="rc-insight-list">
      <div v-if="contextAlert" class="rc-insight-card is-warning" role="alert">
        <span class="rc-insight-mark" aria-hidden="true">!</span>
        <span>
          <strong>Copilot access is limited</strong>
          <small>{{ contextAlert }}</small>
        </span>
        <span class="rc-insight-arrow" aria-hidden="true">&gt;</span>
      </div>
      <button
        v-for="insight in insights.length ? insights : fallbackInsights"
        :key="insight.finding_id || insight.title"
        class="rc-insight-card"
        :class="insightClass(insight.severity)"
        type="button"
      >
        <span class="rc-insight-mark" aria-hidden="true">{{ insightMark(insight.severity) }}</span>
        <span>
          <strong>{{ insight.title }}</strong>
          <small>{{ insight.summary }}</small>
        </span>
        <span class="rc-insight-arrow" aria-hidden="true">&gt;</span>
      </button>
    </div>
  </section>
</template>
