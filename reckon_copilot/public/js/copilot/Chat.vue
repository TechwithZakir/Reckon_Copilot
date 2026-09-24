<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

import { askCopilotStream } from "./api";
import { formatAnswer } from "./answer_format.mjs";
import { canAsk, normalizeAskResponse } from "./chat_logic.mjs";

const props = defineProps({
  initialPrompt: { type: String, default: "" },
  routeContext: { type: Object, default: null },
  models: { type: Array, default: () => [] },
  selectedModel: { type: String, default: "" },
});
const emit = defineEmits(["update:selectedModel"]);
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
  const requestId = createRequestId();
  draft.value = "";
  isSending.value = true;
  try {
    const response = await askCopilotStream({
      requestId,
      question,
      context: props.routeContext,
      selectedModel: props.selectedModel,
      onEvent: (event) => applyStreamEvent(assistantMessage, event),
    });
    if (!assistantMessage.streamDone) {
      finishProgress(assistantMessage, normalizeAskResponse(response), { reveal: true });
    }
  } catch (error) {
    finishProgress(
      assistantMessage,
      {
        role: "assistant",
        tone: "warning",
        text: error?.message || "Copilot could not answer right now.",
      },
      { reveal: true },
    );
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
    streamDone: false,
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
    const stageFloor = Math.round((message.progress.stageIndex / message.progress.stages.length) * 78);
    const softTick = Math.min(14, tick * 2);
    message.progress.percent = Math.min(92, Math.max(message.progress.percent, stageFloor + softTick));
    nextTick(scrollConversationToEnd);
  }, 1000);
  progressTimers.add(timer);
}

function applyStreamEvent(message, event) {
  if (message.cancelled) return;
  if (event.event === "stage") {
    const stageIndex = progressStages.indexOf(event.stage);
    if (stageIndex >= 0) {
      message.progress.stageIndex = stageIndex;
    }
    message.progress.percent = Math.max(message.progress.percent || 0, Number(event.percent || 0));
    message.meta = {
      ...(message.meta || {}),
      provider: event.provider || message.meta?.provider,
      model: event.model || message.meta?.model,
      stream: true,
    };
    nextTick(scrollConversationToEnd);
    return;
  }
  if (event.event === "token") {
    message.text = `${message.text || ""}${event.text || ""}`;
    message.progress.percent = Math.max(message.progress.percent || 0, Number(event.percent || 0));
    nextTick(scrollConversationToEnd);
    return;
  }
  if (event.event === "done") {
    message.streamDone = true;
    finishProgress(message, normalizeAskResponse(event.result), { reveal: false });
    return;
  }
  if (event.event === "error") {
    message.streamDone = true;
    finishProgress(message, normalizeAskResponse(event), { reveal: false });
  }
}

function finishProgress(message, normalized, options = {}) {
  if (message.cancelled) return;
  const responseText = normalized.text || "No answer was found for this page context.";
  const answer = formatAnswer(responseText);
  message.tone = normalized.tone || "normal";
  message.answer = answer;
  message.answerReady = !options.reveal;
  message.meta = {
    ...(normalized.meta || {}),
    stream: true,
    tokens: message.meta?.tokens || estimateTokens(message.text || responseText),
  };
  message.progress = {
    ...(message.progress || {}),
    active: false,
    stageIndex: progressStages.length - 1,
    elapsed: message.progress?.elapsed || "0s",
    percent: 100,
  };
  message.progress.label = "Completed";
  if (options.reveal) {
    typeAnswer(message, answer.plainText || responseText);
  } else {
    message.text = answer.plainText || responseText;
    message.meta.tokens = estimateTokens(message.text);
  }
}

function estimateTokens(text) {
  return Math.max(1, Math.ceil(String(text || "").length / 4));
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
      message.answerReady = true;
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

function cancelConversation() {
  const message = messages.value[messages.value.length - 1];
  if (!message || !isSending.value) return;
  message.cancelled = true;
  message.tone = "warning";
  message.text = "Request cancelled. No response was sent.";
  message.progress = {
    ...(message.progress || {}),
    active: false,
    label: "Cancelled",
    percent: message.progress?.percent || 0,
  };
  isSending.value = false;
}

function createRequestId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `rc-${Date.now()}-${Math.random().toString(16).slice(2)}`;
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
        v-if="isSending"
        class="rc-clear-chat rc-cancel-chat"
        type="button"
        @click="cancelConversation"
      >
        Cancel
      </button>
      <button
        v-else-if="messages.length"
        class="rc-clear-chat"
        type="button"
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
        <template v-if="message.answerReady && message.answer?.kind === 'structured'">
          <div class="rc-answer-content">
            <h4>{{ message.answer.title }}</h4>
            <p v-if="message.answer.summary" class="rc-answer-summary">{{ message.answer.summary }}</p>
            <dl v-if="message.answer.details?.length" class="rc-answer-details">
              <div v-for="detail in message.answer.details" :key="`${detail.label}-${detail.value}`">
                <dt>{{ detail.label }}</dt>
                <dd>{{ detail.value }}</dd>
              </div>
            </dl>
            <section v-for="section in message.answer.sections" :key="section.title" class="rc-answer-section">
              <h5>{{ section.title }}</h5>
              <ul>
                <li v-for="item in section.items" :key="item">{{ item }}</li>
              </ul>
            </section>
          </div>
        </template>
        <p v-else>{{ message.text }}</p>
        <div v-if="message.progress" class="rc-progress-card" :class="{ 'is-complete': !message.progress.active }">
          <div class="rc-progress-line">
            <span class="rc-progress-spinner" aria-hidden="true"></span>
            <strong>{{ message.progress.active ? message.progress.stages[message.progress.stageIndex] : message.progress.label }}</strong>
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
          <span v-if="message.meta.stream">Realtime stream</span>
          <span v-if="message.meta.tokens">Tokens: {{ message.meta.tokens }}</span>
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
      <button class="rc-attach-button" type="button" disabled aria-label="Attach context" title="Context is attached automatically">
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m21.4 11.6-8.8 8.8a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 1 1-2.8-2.8l8.5-8.5" />
        </svg>
      </button>
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
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="m5 12 14-7-4 14-3-6-7-1Z" />
          <path d="m12 13 7-8" />
        </svg>
      </button>
    </div>
    <div class="rc-composer-help">
      <span>Enter to send · Shift + Enter for new line</span>
      <span>/ to see prompts</span>
    </div>
  </section>
</template>
