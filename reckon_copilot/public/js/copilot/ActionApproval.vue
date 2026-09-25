<script setup>
defineProps({
  plan: { type: Object, default: null },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "approve"]);
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
      <p v-else-if="plan.needs_input" class="rc-action-risk" role="status">
        Add the exact field values in the DocType form, then ask Copilot to prepare this action again. No data was changed.
      </p>
      <p v-if="plan.high_risk" class="rc-action-risk" role="alert">High-risk operation. Review carefully before you approve.</p>
      <dl class="rc-action-details">
        <dt>Change</dt><dd>Applied immediately after you approve</dd>
        <dt>Confirmation</dt><dd>Required from you</dd>
        <dt>Plan hash</dt><dd>{{ plan.plan_hash }}</dd>
      </dl>
      <dl v-if="Object.keys(plan.values || {}).length" class="rc-action-values">
        <template v-for="(value, key) in plan.values" :key="key">
          <dt>{{ key }}</dt><dd>{{ value }}</dd>
        </template>
      </dl>
      <p v-else class="rc-action-approved" role="status">This operation changes the document workflow or record state without field values.</p>
      <div class="rc-action-dialog-actions">
        <button class="rc-secondary-button" type="button" @click="emit('close')">Cancel</button>
        <button v-if="!plan.error && !plan.needs_input" class="rc-primary-button" type="button" :disabled="busy" @click="emit('approve')">{{ busy ? "Applying..." : "Approve" }}</button>
      </div>
    </div>
  </div>
</template>
