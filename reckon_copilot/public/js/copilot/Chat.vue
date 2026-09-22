<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

import { askCopilot } from "./api";
import { canAsk, normalizeAskResponse } from "./chat_logic.mjs";

const props = defineProps({
  initialPrompt: { type: String, default: "" },
  routeContext: { type: Object, default: null },
});
const draft = ref(props.initialPrompt);
const messages = ref([]);
const isSending = ref(false);
const progressTimers = new Set();
const typingTimers = new Set();

const progressStages = [
  "Reading page context",
  "Checking permissions",
  "Searching approved knowledge",
  "Contacting LLM provider",
  "Composing response",
];

watch(() => props.initialPrompt, (value) => {
  draft.value = value;
});

async function send() {
  const question = draft.value.trim();
  if (!canAsk(question, props.routeContext) || isSending.value) return;
  messages.value.push({ role: "user", text: question, tone: "normal" });
  const assistantMessage = createProgressMessage();
  messages.value.push(assistantMessage);
  startProgress(assistantMessage);
  draft.value = "";
  isSending.value = true;
  try {
    const response = await askCopilot(question, props.routeContext);
    finishProgress(assistantMessage, normalizeAskResponse(response));
  } catch (error) {
    finishProgress(assistantMessage, {
      role: "assistant",
      tone: "warning",
      text: error?.message || "Copilot could not answer right now.",
    });
  } finally {
    isSending.value = false;
  }
}

function createProgressMessage() {
  return {
    role: "assistant",
    tone: "normal",
    text: "",
    progress: {
      active: true,
      stageIndex: 0,
      stages: progressStages,
      startedAt: Date.now(),
      elapsed: "0s",
      percent: 8,
    },
    meta: {
      provider: "LLM provider",
      stream: true,
    },
  };
}

function startProgress(message) {
  let tick = 0;
  const timer = window.setInterval(() => {
    if (!message.progress?.active) {
      window.clearInterval(timer);
      progressTimers.delete(timer);
      return;
    }
    tick += 1;
    message.progress.elapsed = `${Math.max(1, Math.round((Date.now() - message.progress.startedAt) / 1000))}s`;
    if (tick % 3 === 0 && message.progress.stageIndex < message.progress.stages.length - 1) {
      message.progress.stageIndex += 1;
    }
    const stageFloor = Math.round((message.progress.stageIndex / message.progress.stages.length) * 78);
    const softTick = Math.min(14, tick * 2);
    message.progress.percent = Math.min(92, Math.max(message.progress.percent, stageFloor + softTick));
    nextTick(scrollConversationToEnd);
  }, 1000);
  progressTimers.add(timer);
}

function finishProgress(message, normalized) {
  message.tone = normalized.tone || "normal";
  message.meta = {
    ...(normalized.meta || {}),
    stream: true,
  };
  message.progress = {
    ...(message.progress || {}),
    active: false,
    stageIndex: progressStages.length - 1,
    elapsed: message.progress?.elapsed || "0s",
    percent: 100,
  };
  typeAnswer(message, normalized.text || "");
}

function typeAnswer(message, text) {
  message.text = "";
  if (!text) return;
  let index = 0;
  const step = Math.max(3, Math.ceil(text.length / 80));
  const timer = window.setInterval(() => {
    index = Math.min(text.length, index + step);
    message.text = text.slice(0, index);
    if (index >= text.length) {
      window.clearInterval(timer);
      typingTimers.delete(timer);
      nextTick(scrollConversationToEnd);
    }
  }, 18);
  typingTimers.add(timer);
}

function scrollConversationToEnd() {
  const el = document.querySelector(".rc-conversation");
  if (el) el.scrollTop = el.scrollHeight;
}

function clearConversation() {
  messages.value = [];
}

onBeforeUnmount(() => {
  for (const timer of progressTimers) window.clearInterval(timer);
  for (const timer of typingTimers) window.clearInterval(timer);
  progressTimers.clear();
  typingTimers.clear();
});
</script>

<template>
  <section class="rc-composer-shell" aria-labelledby="rc-chat-title">
    <div class="rc-chat-toolbar">
      <h3 id="rc-chat-title">Conversation</h3>
      <button
        v-if="messages.length"
        class="rc-clear-chat"
        type="button"
        :disabled="isSending"
        @click="clearConversation"
      >
        Clear
      </button>
    </div>
    <div v-if="messages.length" class="rc-conversation" aria-live="polite">
      <article
        v-for="(message, index) in messages"
        :key="`${message.role}-${index}`"
        class="rc-message"
        :class="[`is-${message.role}`, { 'is-warning': message.tone === 'warning' }]"
      >
        <p>{{ message.text }}</p>
        <div v-if="message.progress" class="rc-progress-card" :class="{ 'is-complete': !message.progress.active }">
          <div class="rc-progress-line">
            <span class="rc-progress-spinner" aria-hidden="true"></span>
            <strong>{{ message.progress.stages[message.progress.stageIndex] }}</strong>
            <em>{{ message.progress.elapsed }}</em>
          </div>
          <div
            class="rc-progress-meter"
            role="progressbar"
            :aria-valuenow="message.progress.percent"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <span :style="{ width: `${message.progress.percent}%` }"></span>
          </div>
          <ol class="rc-progress-stages">
            <li
              v-for="(stage, stageIndex) in message.progress.stages"
              :key="stage"
              :class="{
                'is-done': stageIndex < message.progress.stageIndex || !message.progress.active,
                'is-active': stageIndex === message.progress.stageIndex && message.progress.active,
              }"
            >
              {{ stage }}
            </li>
          </ol>
        </div>
        <small v-if="message.meta">
          {{ message.meta.intent || message.meta.source || message.meta.provider || "copilot" }}
          <span v-if="message.meta.cacheHit">cached</span>
          <span v-if="message.meta.model">Model: {{ message.meta.model }}</span>
          <span v-if="message.meta.stream">Live progress</span>
        </small>
        <div v-if="message.meta?.evidence?.length" class="rc-evidence-list" aria-label="Evidence">
          <span
            v-for="item in message.meta.evidence"
            :key="item.chunk_id"
            class="rc-evidence-chip"
            :title="item.locator"
          >
            {{ item.source_title || item.chunk_id }}
          </span>
        </div>
        <ul v-if="message.meta?.warnings?.length" class="rc-message-notes">
          <li v-for="warning in message.meta.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <div v-if="message.meta?.followups?.length" class="rc-followups">
          <button
            v-for="followup in message.meta.followups"
            :key="followup"
            class="rc-followup"
            type="button"
            @click="draft = followup"
          >
            {{ followup }}
          </button>
        </div>
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
