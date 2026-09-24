<script setup>
defineProps({
  prompts: { type: Array, default: () => [] },
  expanded: { type: Boolean, default: false },
  hasMore: { type: Boolean, default: false },
  moreCount: { type: Number, default: 0 },
});
defineEmits(["select", "feedback", "toggle-more"]);

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
      <span v-for="prompt in prompts" :key="promptLabel(prompt)" class="rc-chip-wrap">
        <button
          class="rc-chip"
          type="button"
          :title="promptValue(prompt)"
          @click="$emit('select', prompt)"
        >
          {{ promptLabel(prompt) }}
        </button>
        <button
          v-if="typeof prompt !== 'string' && prompt.source === 'catalog'"
          class="rc-chip-feedback"
          type="button"
          title="Not useful"
          aria-label="Mark suggestion as not useful"
          @click.stop="$emit('feedback', prompt)"
        >
          ×
        </button>
      </span>
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
