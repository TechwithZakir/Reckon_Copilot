<script setup>
defineProps({
  plan: { type: Object, default: null },
  approved: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "approve", "execute"]);
</script>

<template>
  <div v-if="plan" class="rc-action-dialog" role="dialog" aria-modal="true" aria-labelledby="rc-action-title">
    <div class="rc-action-dialog-card">
      <div class="rc-block-heading">
        <h3 id="rc-action-title">Review Copilot plan</h3>
        <button class="rc-icon-button" type="button" aria-label="Close plan" @click="emit('close')">×</button>
      </div>
      <p class="rc-action-dialog-summary">
        {{ plan.action }} {{ plan.target?.doctype || "record" }}
        <span v-if="plan.target?.document_name">/{{ plan.target.document_name }}</span>
      </p>
      <p v-if="plan.error" class="rc-action-risk" role="alert">{{ plan.error }}</p>
      <p v-else-if="approved" class="rc-action-approved" role="status">Approval recorded. Select Execute only when you are ready to apply this action.</p>
      <p v-else-if="plan.needs_input" class="rc-action-risk" role="status">
        Add the exact field values in the DocType form, then ask Copilot to prepare this action again. No data was changed.
      </p>
      <p v-if="plan.high_risk" class="rc-action-risk" role="alert">High-risk operation. Review carefully before approval.</p>
      <dl class="rc-action-details">
        <dt>Execution</dt><dd>{{ plan.execution }}</dd>
        <dt>Approval</dt><dd>Required</dd>
        <dt>Plan hash</dt><dd>{{ plan.plan_hash }}</dd>
      </dl>
      <div class="rc-action-dialog-actions">
        <button class="rc-secondary-button" type="button" @click="emit('close')">Cancel</button>
        <button v-if="!plan.error && !plan.needs_input && !approved" class="rc-primary-button" type="button" @click="emit('approve')">Approve action</button>
        <button v-else-if="!plan.error" class="rc-primary-button" type="button" @click="emit('execute')">Execute approved action</button>
      </div>
    </div>
  </div>
</template>
