<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  plan: { type: Object, default: null },
  approved: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "approve", "execute", "replan"]);
const fieldRows = ref([]);
const needsValues = computed(() => ["create", "update"].includes(props.plan?.action));
const editableFields = computed(() => props.plan?.editable_fields || []);
const hasValues = computed(() => Object.keys(props.plan?.values || {}).length > 0);
const canRefresh = computed(() => fieldRows.value.some((row) => String(row.field || "").trim()));

function resetFields(plan) {
  const values = plan?.values || {};
  const entries = Object.entries(values).map(([field, value]) => ({ field, value: String(value ?? "") }));
  fieldRows.value = needsValues.value && !entries.length ? [{ field: "", value: "" }] : entries;
}

watch(() => props.plan, resetFields, { immediate: true });

function addField() {
  fieldRows.value.push({ field: "", value: "" });
}

function removeField(index) {
  fieldRows.value.splice(index, 1);
  if (!fieldRows.value.length && needsValues.value) addField();
}

function refreshPreview() {
  const values = {};
  for (const row of fieldRows.value) {
    const field = String(row.field || "").trim();
    if (field) values[field] = row.value;
  }
  emit("replan", values);
}
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
      <p v-if="plan.high_risk" class="rc-action-risk" role="alert">High-risk operation. Review carefully before approval.</p>
      <section v-if="needsValues && !approved && !plan.error" class="rc-action-fields" aria-labelledby="rc-action-fields-title">
        <div class="rc-action-fields-heading">
          <strong id="rc-action-fields-title">Proposed field changes</strong>
          <small>Refresh the preview before approval.</small>
        </div>
        <div v-for="(row, index) in fieldRows" :key="index" class="rc-action-field-row">
          <select v-if="editableFields.length" v-model="row.field" aria-label="Field to change">
            <option value="">Choose a field</option>
            <option v-for="field in editableFields" :key="field.fieldname" :value="field.fieldname">
              {{ field.label }}
            </option>
          </select>
          <input v-else v-model="row.field" type="text" placeholder="Field name" aria-label="Field name" />
          <input v-model="row.value" type="text" placeholder="New value" aria-label="New value" />
          <button class="rc-icon-button" type="button" aria-label="Remove field" @click="removeField(index)">×</button>
        </div>
        <div class="rc-action-fields-actions">
          <button class="rc-secondary-button" type="button" @click="addField">Add field</button>
          <button class="rc-secondary-button" type="button" :disabled="!canRefresh" @click="refreshPreview">Refresh preview</button>
        </div>
        <small v-if="!hasValues">Add at least one permitted field before approval.</small>
      </section>
      <div v-if="hasValues && !needsValues" class="rc-action-values">
        <strong>Approved operation</strong>
        <span>No field values are required for this operation.</span>
      </div>
      <dl class="rc-action-details">
        <dt>Execution</dt><dd>{{ plan.execution }}</dd>
        <dt>Approval</dt><dd>Required</dd>
        <dt>Plan hash</dt><dd>{{ plan.plan_hash }}</dd>
      </dl>
      <div class="rc-action-dialog-actions">
        <button class="rc-secondary-button" type="button" @click="emit('close')">Cancel</button>
        <button v-if="!plan.error && !approved && (!needsValues || hasValues)" class="rc-primary-button" type="button" @click="emit('approve')">Approve action</button>
        <button v-else-if="!plan.error" class="rc-primary-button" type="button" @click="emit('execute')">Execute approved action</button>
      </div>
    </div>
  </div>
</template>
