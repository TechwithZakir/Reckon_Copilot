<script setup>
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
    <label class="rc-switch-row">
      <span>Copilot enabled</span>
      <input
        type="checkbox"
        :checked="preferences.enabled"
        @change="update('enabled', $event.target.checked)"
      />
    </label>
    <label class="rc-switch-row">
      <span>Notifications</span>
      <input
        type="checkbox"
        :checked="preferences.notifications_enabled"
        @change="update('notifications_enabled', $event.target.checked)"
      />
    </label>
    <label class="rc-switch-row">
      <span>Response sound</span>
      <input
        type="checkbox"
        :checked="preferences.response_sound_enabled"
        @change="update('response_sound_enabled', $event.target.checked)"
      />
    </label>
  </section>
</template>
