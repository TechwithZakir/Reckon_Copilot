<script setup>
defineProps({
  pageType: { type: String, default: "Page" },
  fingerprint: { type: String, default: "" },
});
</script>

<template>
  <div class="rc-context-pill">
    <span class="rc-context-dot" aria-hidden="true"></span>
    <span>Context: {{ pageType }}</span>
    <span v-if="fingerprint" class="rc-context-fingerprint">
      {{ fingerprint.slice(0, 8) }}
    </span>
  </div>
</template>
