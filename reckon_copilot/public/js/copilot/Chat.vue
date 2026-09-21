<script setup>
import { ref, watch } from "vue";

import { askCopilot } from "./api";
import { canAsk, normalizeAskResponse } from "./chat_logic.mjs";

const props = defineProps({
  initialPrompt: { type: String, default: "" },
  routeContext: { type: Object, default: null },
});
const draft = ref(props.initialPrompt);
const messages = ref([]);
const isSending = ref(false);

watch(() => props.initialPrompt, (value) => {
  draft.value = value;
});

async function send() {
  const question = draft.value.trim();
  if (!canAsk(question, props.routeContext) || isSending.value) return;
  messages.value.push({ role: "user", text: question, tone: "normal" });
  draft.value = "";
  isSending.value = true;
  try {
    const response = await askCopilot(question, props.routeContext);
    messages.value.push(normalizeAskResponse(response));
  } catch (error) {
    messages.value.push({
      role: "assistant",
      tone: "warning",
      text: error?.message || "Copilot could not answer right now.",
    });
  } finally {
    isSending.value = false;
  }
}
</script>

<template>
  <section class="rc-composer-shell" aria-labelledby="rc-chat-title">
    <h3 id="rc-chat-title" class="rc-sr-only">Conversation</h3>
    <div v-if="messages.length" class="rc-conversation" aria-live="polite">
      <article
        v-for="(message, index) in messages"
        :key="`${message.role}-${index}`"
        class="rc-message"
        :class="[`is-${message.role}`, { 'is-warning': message.tone === 'warning' }]"
      >
        <p>{{ message.text }}</p>
        <small v-if="message.meta">
          {{ message.meta.source || message.meta.provider || "copilot" }}
          <span v-if="message.meta.cacheHit">cached</span>
        </small>
      </article>
    </div>
    <div class="rc-composer-box">
      <button class="rc-attach-button" type="button" disabled aria-label="Attach context">+</button>
      <textarea
        v-model="draft"
        rows="2"
        placeholder="Ask anything about this page..."
        :disabled="!routeContext || routeContext.access_denied || isSending"
        @keydown.enter.exact.prevent="send"
      />
      <button
        class="rc-send-button"
        type="button"
        :disabled="!canAsk(draft, routeContext) || isSending"
        aria-label="Send message"
        @click="send"
      >
        &gt;
      </button>
    </div>
    <div class="rc-composer-help">
      <span>Shift + Enter for new line</span>
      <span>/ to see prompts</span>
    </div>
  </section>
</template>
