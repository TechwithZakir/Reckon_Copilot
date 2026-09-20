<script setup>
import { ref, watch } from "vue";

const props = defineProps({ initialPrompt: { type: String, default: "" } });
const draft = ref(props.initialPrompt);

watch(() => props.initialPrompt, (value) => {
  draft.value = value;
});
</script>

<template>
  <section class="rc-chat" aria-labelledby="rc-chat-title">
    <h3 id="rc-chat-title">Conversation</h3>
    <div class="rc-empty-state">
      <strong>No conversation yet</strong>
      <span>Choose a suggestion or enter a question.</span>
    </div>
    <div class="rc-composer">
      <textarea v-model="draft" rows="3" placeholder="Ask about this page" disabled />
      <button class="rc-button rc-button-solid" type="button" disabled>Send</button>
    </div>
  </section>
</template>
