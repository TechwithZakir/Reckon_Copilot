<script setup>
defineProps({ prompts: { type: Array, default: () => [] } });
defineEmits(["select"]);
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
        :key="prompt"
        class="rc-chip"
        type="button"
        @click="$emit('select', prompt)"
      >
        {{ prompt }}
      </button>
      <button class="rc-chip rc-chip-more" type="button" aria-label="More quick questions">
        ...
      </button>
    </div>
  </section>
</template>
