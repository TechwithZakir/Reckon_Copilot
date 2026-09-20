<script setup>
defineProps({ pageType: { type: String, default: "Page" } });
</script>

<template>
  <div class="rc-context-header">
    <span class="rc-context-label">Current context</span>
    <strong>{{ pageType }}</strong>
  </div>
</template>
