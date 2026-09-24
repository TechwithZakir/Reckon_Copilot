<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { getAgentAdvice, getInsights, getNotifications, getShellConfig, savePreferences } from "./api";
import Chat from "./Chat.vue";
import ContextHeader from "./ContextHeader.vue";
import NotificationCenter from "./NotificationCenter.vue";
import Settings from "./Settings.vue";
import SuggestedPrompts from "./SuggestedPrompts.vue";
import { createShellState, reduceShellState } from "./shell_state.mjs";

const props = defineProps({
  pageType: { type: String, default: "Page" },
  routeContext: { type: Object, default: null },
  contextAlert: { type: String, default: "" },
});
const state = ref(createShellState());
const prompts = ref([]);
const selectedPrompt = ref("");
const settingsOpen = ref(false);
const insights = ref([]);
const insightCounts = ref({ critical: 1, warning: 1, info: 1 });
const notifications = ref([]);
const advisorQuestions = ref([]);
const advisorActions = ref([]);
const models = ref([]);
const selectedModel = ref("");

const actionPrompts = computed(() => {
  const fromAdvisor = advisorActions.value.map((item) => item.title || item.prompt).filter(Boolean);
  const fromInsights = insights.value.flatMap((item) => item.suggested_prompts || []);
  const defaults = ["Explain this page", "What should I review?", "Which filters may help?"];
  return [...new Set([...fromAdvisor, ...fromInsights, ...defaults])].slice(0, 4);
});

const contextualPrompts = computed(() => [
  ...advisorQuestions.value.map((item) => item.title || item.prompt).filter(Boolean),
  ...prompts.value,
]);

const panelLabel = computed(() =>
  state.value.isMinimized ? "Expand Reckon Copilot" : "Minimize Reckon Copilot",
);

const summaryText = computed(() => {
  const type = props.routeContext?.page_type || props.pageType || "Page";
  if (props.routeContext?.access_denied) {
    return `I can see this is a ${type.toLowerCase()} page, but your current permissions do not allow Copilot to read its context.`;
  }
  return `I am ready to help with this ${type.toLowerCase()} context. Phase 2 uses sanitized route context only.`;
});

const contextFingerprint = computed(() => props.routeContext?.fingerprint || "");

function titleCaseSlug(value) {
  return String(value || "")
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function routeLabel(context) {
  const route = Array.isArray(context?.route) ? context.route : [];
  if (route[1]) return titleCaseSlug(route[1]);
  if (route[0] && !["Form", "List", "Report", "Dashboard", "Workspace"].includes(route[0])) {
    return titleCaseSlug(route[0]);
  }
  return "";
}

function deskPathParts() {
  const match = window.location.pathname.match(/\/desk\/?([^?#]*)/);
  if (!match) return [];
  return match[1]
    .split("/")
    .filter(Boolean)
    .map((part) => decodeURIComponent(part));
}

function labelFromDeskPath(type) {
  const parts = deskPathParts();
  if (!parts.length) return type === "Workspace" ? "Home" : "";
  if (parts[0] === "dashboard-view") return titleCaseSlug(parts[1] || "Dashboard");
  if (parts[0] === "query-report") return titleCaseSlug(parts[1] || "Report");
  return titleCaseSlug(parts[0]);
}

function recordFromDeskPath(type) {
  const parts = deskPathParts();
  return type === "Form" && parts.length > 1 ? titleCaseSlug(parts[1]) : "";
}

const contextDetail = computed(() => {
  const context = props.routeContext;
  const type = context?.page_type || props.pageType || "Page";
  if (!context) return type;

  const label =
    context.doctype ||
    context.report_name ||
    context.dashboard_name ||
    context.workspace_name ||
    context.page_name ||
    routeLabel(context) ||
    labelFromDeskPath(type);
  const record =
    context.document_name ||
    (context.page_type === "Form" ? context.route?.[2] : "") ||
    recordFromDeskPath(type);
  return [type, label, record].filter(Boolean).join(" / ");
});

function dispatch(action) {
  state.value = reduceShellState(state.value, action);
}

async function loadConfiguration() {
  dispatch({ type: "configuration-loading" });
  try {
    const config = await getShellConfig(props.pageType);
    prompts.value = config.suggested_prompts || [];
    models.value = config.models || [];
    selectedModel.value = selectedModel.value || models.value[0] || "";
    dispatch({ type: "configuration-loaded", preferences: config.preferences });
  } catch (error) {
    prompts.value = ["What can I do here?", "Show available help"];
    dispatch({ type: "configuration-error", message: error.message });
  }
}

async function updatePreferences(preferences) {
  state.value = { ...state.value, preferences };
  try {
    const saved = await savePreferences(preferences);
    state.value = { ...state.value, preferences: saved, error: "" };
  } catch (_error) {
    dispatch({
      type: "configuration-error",
      message: "Settings could not be saved. Local defaults remain active.",
    });
  }
}

async function loadInsights() {
  if (!props.routeContext || props.routeContext.access_denied) {
    insights.value = [];
    notifications.value = [];
    advisorQuestions.value = [];
    advisorActions.value = [];
    insightCounts.value = { critical: 0, warning: props.routeContext?.access_denied ? 1 : 0, info: 0 };
    return;
  }
  try {
    const [result, notificationResult, advice] = await Promise.all([
      getInsights(props.routeContext),
      getNotifications(props.routeContext, [], state.value.preferences.notifications_enabled),
      getAgentAdvice(props.routeContext).catch(() => ({ questions: [], actions: [] })),
    ]);
    insights.value = result.findings || [];
    insightCounts.value = result.counts || { critical: 0, warning: 0, info: 0 };
    notifications.value = notificationResult.notifications || [];
    advisorQuestions.value = advice.questions || [];
    advisorActions.value = advice.actions || [];
  } catch (_error) {
    insights.value = [];
    notifications.value = [];
    advisorQuestions.value = [];
    advisorActions.value = [];
    insightCounts.value = { critical: 0, warning: 1, info: 0 };
  }
}

onMounted(loadConfiguration);
onMounted(loadInsights);
watch(() => props.pageType, loadConfiguration);
watch(contextFingerprint, loadInsights);
watch(() => state.value.preferences.notifications_enabled, loadInsights);
</script>

<template>
  <button
    v-if="!state.isOpen"
    class="rc-button rc-button-solid rc-launcher"
    type="button"
    @click="dispatch({ type: 'open' })"
  >
    Reckon Copilot
  </button>

  <ContextHeader
    v-if="state.isOpen && !state.isMinimized"
    :page-type="routeContext?.page_type || pageType"
    :detail="contextDetail"
    :fingerprint="contextFingerprint"
  />

  <aside
    v-if="state.isOpen"
    class="rc-panel"
    :class="{ 'is-minimized': state.isMinimized }"
    aria-label="Reckon Copilot"
  >
    <header class="rc-panel-header">
      <div class="rc-brand">
        <span class="rc-logo" aria-hidden="true">R</span>
        <div>
          <strong>Reckon Copilot</strong>
          <span>Beta</span>
        </div>
      </div>
      <div class="rc-header-actions">
        <button
          class="rc-icon-button"
          type="button"
          :aria-pressed="state.preferences.response_sound_enabled"
          title="Response sound"
          @click="
            updatePreferences({
              ...state.preferences,
              response_sound_enabled: !state.preferences.response_sound_enabled,
            })
          "
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M11 5 6 9H3v6h3l5 4V5Z" />
            <path d="M15.5 8.5a5 5 0 0 1 0 7" />
            <path d="M18.5 5.5a9 9 0 0 1 0 13" />
          </svg>
        </button>
        <button
          class="rc-icon-button"
          type="button"
          :aria-pressed="state.preferences.notifications_enabled"
          title="Notifications"
          @click="
            updatePreferences({
              ...state.preferences,
              notifications_enabled: !state.preferences.notifications_enabled,
            })
          "
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
            <path d="M13.7 21a2 2 0 0 1-3.4 0" />
          </svg>
        </button>
        <button
          class="rc-icon-button"
          type="button"
          :aria-label="settingsOpen ? 'Close settings' : 'Open settings'"
          title="Settings"
          @click="settingsOpen = !settingsOpen"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1A2 2 0 1 1 4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1A2 2 0 1 1 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.6V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.6h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1A2 2 0 1 1 19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.6 1h.1a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.6 1Z" />
          </svg>
        </button>
        <button
          class="rc-icon-button"
          type="button"
          :aria-label="panelLabel"
          title="Minimize"
          @click="dispatch({ type: 'toggle-minimize' })"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M8 3H5a2 2 0 0 0-2 2v3" />
            <path d="M16 3h3a2 2 0 0 1 2 2v3" />
            <path d="M8 21H5a2 2 0 0 1-2-2v-3" />
            <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
            <path d="M9 9h6v6H9z" />
          </svg>
        </button>
        <button
          class="rc-icon-button"
          type="button"
          aria-label="Close Reckon Copilot"
          title="Close"
          @click="dispatch({ type: 'close' })"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      </div>
    </header>

    <template v-if="!state.isMinimized">
      <p v-if="state.status === 'loading'" class="rc-status" role="status">
        Loading preferences...
      </p>
      <p v-if="state.error" class="rc-error" role="status">{{ state.error }}</p>
      <Settings
        v-if="settingsOpen"
        :preferences="state.preferences"
        @change="updatePreferences"
      />
      <div class="rc-panel-body">
        <section class="rc-hero-card" aria-label="Copilot summary">
          <div>
            <h2>Hi there,</h2>
            <p>{{ summaryText }}</p>
            <div class="rc-context-detail" aria-label="Detected context">
              {{ contextDetail }}
            </div>
          </div>
          <div class="rc-metric-grid" aria-label="Current insight summary">
            <div class="rc-metric is-critical">
              <strong>{{ insightCounts.critical }}</strong>
              <span>Critical</span>
            </div>
            <div class="rc-metric is-warning">
              <strong>{{ insightCounts.warning }}</strong>
              <span>Warning</span>
            </div>
            <div class="rc-metric is-info">
              <strong>{{ insightCounts.info }}</strong>
              <span>Info</span>
            </div>
          </div>
        </section>

        <NotificationCenter
          v-if="state.preferences.notifications_enabled"
          :context-alert="contextAlert"
          :insights="insights"
          :notifications="notifications"
        />

        <section class="rc-block" aria-labelledby="rc-actions-title">
          <div class="rc-block-heading">
            <span class="rc-heading-icon" aria-hidden="true">A</span>
            <h3 id="rc-actions-title">Suggested Actions</h3>
          </div>
          <div class="rc-action-list">
            <button
              v-for="prompt in actionPrompts"
              :key="prompt"
              class="rc-action"
              type="button"
              @click="selectedPrompt = prompt"
            >
              <span>?</span>
              {{ prompt }}
            </button>
          </div>
          <button class="rc-link-button rc-more-button" type="button">
            More suggestions
          </button>
        </section>

        <SuggestedPrompts :prompts="contextualPrompts" @select="selectedPrompt = $event" />
      </div>

      <div class="rc-panel-footer">
        <Chat :initial-prompt="selectedPrompt" :route-context="routeContext" :models="models" :selected-model="selectedModel" @update:selected-model="selectedModel = $event" />
        <div class="rc-runtime">
          <span><i aria-hidden="true"></i>Using LLM provider</span>
          <span>Usage is shown per response</span>
        </div>
      </div>
    </template>
  </aside>
</template>
