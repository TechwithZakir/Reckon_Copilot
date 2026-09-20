<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Button } from "frappe-ui";

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
  <Button
    v-if="!state.isOpen"
    class="rc-launcher"
    variant="solid"
    @click="dispatch({ type: 'open' })"
  >
    Reckon Copilot
  </Button>

  <aside
    v-else
    class="rc-panel"
    :class="{ 'is-minimized': state.isMinimized }"
    aria-label="Reckon Copilot"
  >
    <header class="rc-panel-header">
      <div>
        <strong>Reckon Copilot</strong>
        <span>Phase 1 shell</span>
      </div>
      <div class="rc-header-actions">
        <Button
          variant="ghost"
          icon="lucide-settings"
          :aria-label="settingsOpen ? 'Close settings' : 'Open settings'"
          @click="settingsOpen = !settingsOpen"
        />
        <Button
          variant="ghost"
          icon="lucide-minus"
          :aria-label="panelLabel"
          @click="dispatch({ type: 'toggle-minimize' })"
        />
        <Button
          variant="ghost"
          icon="lucide-x"
          aria-label="Close Reckon Copilot"
          @click="dispatch({ type: 'close' })"
        />
      </div>
    </header>

    <template v-if="!state.isMinimized">
      <ContextHeader :page-type="pageType" />
      <p v-if="state.status === 'loading'" class="rc-status" role="status">
        Loading preferences...
      </p>
      <p v-if="state.error" class="rc-error" role="status">{{ state.error }}</p>
      <Settings
        v-if="settingsOpen"
        :preferences="state.preferences"
        @change="updatePreferences"
      />
      <SuggestedPrompts :prompts="prompts" @select="selectedPrompt = $event" />
      <NotificationCenter v-if="state.preferences.notifications_enabled" />
      <Chat :initial-prompt="selectedPrompt" />
    </template>
  </aside>
</template>
