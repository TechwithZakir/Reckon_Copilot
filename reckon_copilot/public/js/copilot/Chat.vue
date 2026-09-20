<script setup>
import { ref, watch } from "vue";

const props = defineProps({ initialPrompt: { type: String, default: "" } });
const draft = ref(props.initialPrompt);

watch(() => props.initialPrompt, (value) => {
  draft.value = value;
});
</script>

<template>
  <section class="rc-composer-shell" aria-labelledby="rc-chat-title">
    <h3 id="rc-chat-title" class="rc-sr-only">Conversation</h3>
    <div class="rc-composer-box">
      <button class="rc-attach-button" type="button" disabled aria-label="Attach context">+</button>
      <textarea
        v-model="draft"
        rows="2"
        placeholder="Ask anything about this page..."
        disabled
      />
      <button class="rc-send-button" type="button" disabled aria-label="Send message">
        &gt;
      </button>
    </div>
    <div class="rc-composer-help">
      <span>Shift + Enter for new line</span>
      <span>/ to see prompts</span>
    </div>
  </section>
</template>
