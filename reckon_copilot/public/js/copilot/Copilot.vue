<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { getShellConfig, savePreferences } from "./api";
import Chat from "./Chat.vue";
import ContextHeader from "./ContextHeader.vue";
import NotificationCenter from "./NotificationCenter.vue";
import Settings from "./Settings.vue";
import SuggestedPrompts from "./SuggestedPrompts.vue";
import { createShellState, reduceShellState } from "./shell_state.mjs";

const props = defineProps({ pageType: { type: String, default: "Page" } });
const state = ref(createShellState());
const prompts = ref([]);
const selectedPrompt = ref("");
const settingsOpen = ref(false);

const panelLabel = computed(() =>
  state.value.isMinimized ? "Expand Reckon Copilot" : "Minimize Reckon Copilot",
);

const summaryText = computed(() => {
  const type = props.pageType || "Page";
  return `I am ready to help with this ${type.toLowerCase()} context. Phase 1 is running in UI-only mode.`;
});

function dispatch(action) {
  state.value = reduceShellState(state.value, action);
}

async function loadConfiguration() {
  dispatch({ type: "configuration-loading" });
  try {
    const config = await getShellConfig(props.pageType);
    prompts.value = config.suggested_prompts || [];
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

onMounted(loadConfiguration);
watch(() => props.pageType, loadConfiguration);
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

  <ContextHeader v-if="state.isOpen && !state.isMinimized" :page-type="pageType" />

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
          <span aria-hidden="true">S</span>
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
          <span aria-hidden="true">N</span>
        </button>
        <button
          class="rc-icon-button"
          type="button"
          :aria-label="settingsOpen ? 'Close settings' : 'Open settings'"
          title="Settings"
          @click="settingsOpen = !settingsOpen"
        >
          <span aria-hidden="true">*</span>
        </button>
        <button
          class="rc-icon-button"
          type="button"
          :aria-label="panelLabel"
          title="Minimize"
          @click="dispatch({ type: 'toggle-minimize' })"
        >
          <span aria-hidden="true">-</span>
        </button>
        <button
          class="rc-icon-button"
          type="button"
          aria-label="Close Reckon Copilot"
          title="Close"
          @click="dispatch({ type: 'close' })"
        >
          <span aria-hidden="true">x</span>
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
          </div>
          <div class="rc-metric-grid" aria-label="Current insight summary">
            <div class="rc-metric is-critical">
              <strong>1</strong>
              <span>Critical</span>
            </div>
            <div class="rc-metric is-warning">
              <strong>1</strong>
              <span>Warning</span>
            </div>
            <div class="rc-metric is-info">
              <strong>1</strong>
              <span>Info</span>
            </div>
          </div>
        </section>

        <NotificationCenter v-if="state.preferences.notifications_enabled" />

        <section class="rc-block" aria-labelledby="rc-actions-title">
          <div class="rc-block-heading">
            <span class="rc-heading-icon" aria-hidden="true">A</span>
            <h3 id="rc-actions-title">Suggested Actions</h3>
          </div>
          <div class="rc-action-list">
            <button class="rc-action" type="button" @click="selectedPrompt = 'What should I review?'">
              <span>?</span>
              What should I review?
            </button>
            <button class="rc-action" type="button" @click="selectedPrompt = 'Show related records'">
              <span>?</span>
              Show related records
            </button>
            <button class="rc-action" type="button" @click="selectedPrompt = 'Explain this page'">
              <span>?</span>
              Explain this page
            </button>
            <button class="rc-action" type="button" @click="selectedPrompt = 'Create a reminder'">
              <span>?</span>
              Create a reminder
            </button>
          </div>
          <button class="rc-link-button rc-more-button" type="button">
            More suggestions
          </button>
        </section>

        <SuggestedPrompts :prompts="prompts" @select="selectedPrompt = $event" />
      </div>

      <div class="rc-panel-footer">
        <Chat :initial-prompt="selectedPrompt" />
        <div class="rc-runtime">
          <span><i aria-hidden="true"></i>Using Ollama (local)</span>
          <span>Tokens: 248</span>
        </div>
      </div>
    </template>
  </aside>
</template>
