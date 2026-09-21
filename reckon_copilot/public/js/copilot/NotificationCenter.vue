<script setup>
defineProps({
  contextAlert: { type: String, default: "" },
});
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
      <button class="rc-insight-card is-critical" type="button">
        <span class="rc-insight-mark" aria-hidden="true">!</span>
        <span>
          <strong>Review pending document status</strong>
          <small>Copilot can highlight overdue, blocked or incomplete work once context extraction is enabled.</small>
        </span>
        <span class="rc-insight-arrow" aria-hidden="true">&gt;</span>
      </button>
      <button class="rc-insight-card is-warning" type="button">
        <span class="rc-insight-mark" aria-hidden="true">+</span>
        <span>
          <strong>Check linked transactions</strong>
          <small>Related records and permission-safe summaries are planned for the next context phase.</small>
        </span>
        <span class="rc-insight-arrow" aria-hidden="true">&gt;</span>
      </button>
      <button class="rc-insight-card is-info" type="button">
        <span class="rc-insight-mark" aria-hidden="true">i</span>
        <span>
          <strong>Ask about this page</strong>
          <small>Use suggested prompts to prepare for page-aware assistance without sending record data yet.</small>
        </span>
        <span class="rc-insight-arrow" aria-hidden="true">&gt;</span>
      </button>
    </div>
  </section>
</template>
