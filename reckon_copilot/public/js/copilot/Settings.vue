<script setup>
import { Switch } from "frappe-ui";

const props = defineProps({ preferences: { type: Object, required: true } });
const emit = defineEmits(["change"]);

function update(field, value) {
  const next = { ...props.preferences, [field]: value };
  emit("change", next);
}
</script>

<template>
  <section class="rc-section" aria-labelledby="rc-settings-title">
    <h3 id="rc-settings-title">Settings</h3>
    <Switch
      label="Copilot enabled"
      :model-value="preferences.enabled"
      @update:model-value="update('enabled', $event)"
    />
    <Switch
      label="Notifications"
      :model-value="preferences.notifications_enabled"
      @update:model-value="update('notifications_enabled', $event)"
    />
    <Switch
      label="Response sound"
      :model-value="preferences.response_sound_enabled"
      @update:model-value="update('response_sound_enabled', $event)"
    />
  </section>
</template>
