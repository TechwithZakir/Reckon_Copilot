<script setup>
defineProps({
  prompts: { type: Array, default: () => [] },
  expanded: { type: Boolean, default: false },
  hasMore: { type: Boolean, default: false },
  moreCount: { type: Number, default: 0 },
});
defineEmits(["select", "toggle-more"]);

function promptLabel(prompt) {
  return typeof prompt === "string" ? prompt : prompt?.title || prompt?.prompt || "Question";
}

function promptValue(prompt) {
  return typeof prompt === "string" ? prompt : prompt?.prompt || prompt?.title || "";
}
</script>

<template>
  <section class="rc-block" aria-labelledby="rc-suggestions-title">
    <div class="rc-block-heading">
      <span class="rc-heading-icon" aria-hidden="true">?</span>
      <h3 id="rc-suggestions-title">Quick Questions</h3>
    </div>
    <div class="rc-chip-list">
      <button
        v-for="prompt in prompts"
        :key="promptLabel(prompt)"
        class="rc-chip"
        type="button"
        :title="promptValue(prompt)"
        @click="$emit('select', promptValue(prompt))"
      >
        {{ promptLabel(prompt) }}
      </button>
      <button
        v-if="hasMore || expanded"
        class="rc-chip rc-chip-more"
        type="button"
        :aria-expanded="expanded"
        @click="$emit('toggle-more')"
      >
        {{ expanded ? "Show fewer" : `More (${moreCount})` }}
      </button>
    </div>
  </section>
</template>
