<script setup>
defineProps({ pageType: { type: String, default: "Page" } });
</script>

<template>
  <div class="rc-context-pill">
    <span class="rc-context-dot" aria-hidden="true"></span>
    <span>Context: {{ pageType }}</span>
  </div>
</template>
