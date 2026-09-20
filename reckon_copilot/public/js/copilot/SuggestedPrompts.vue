<script setup>
defineProps({ prompts: { type: Array, default: () => [] } });
defineEmits(["select"]);
</script>

<template>
  <section class="rc-section" aria-labelledby="rc-suggestions-title">
    <h3 id="rc-suggestions-title">Suggested prompts</h3>
    <div class="rc-prompt-list">
      <button
        v-for="prompt in prompts"
        :key="prompt"
        class="rc-prompt"
        type="button"
        @click="$emit('select', prompt)"
      >
        {{ prompt }}
      </button>
    </div>
  </section>
</template>
