export const DEFAULT_PREFERENCES = Object.freeze({
  enabled: true,
  notifications_enabled: true,
  response_sound_enabled: false,
});

export const PANEL_STATE_STORAGE_KEY = "reckon_copilot.panel_state.v1";

function getStorage(storage) {
  if (storage !== undefined) return storage;
  try {
    return globalThis.localStorage;
  } catch (_error) {
    return null;
  }
}

export function readPersistedPanelState(storage) {
  const target = getStorage(storage);
  if (!target) return {};
  try {
    const value = JSON.parse(target.getItem(PANEL_STATE_STORAGE_KEY) || "{}");
    return {
      ...(typeof value?.isOpen === "boolean" ? { isOpen: value.isOpen } : {}),
      ...(typeof value?.isMinimized === "boolean" ? { isMinimized: value.isMinimized } : {}),
    };
  } catch (_error) {
    return {};
  }
}

export function persistPanelState(state, storage) {
  const target = getStorage(storage);
  if (!target) return;
  try {
    target.setItem(
      PANEL_STATE_STORAGE_KEY,
      JSON.stringify({
        isOpen: Boolean(state?.isOpen),
        isMinimized: Boolean(state?.isMinimized),
      }),
    );
  } catch (_error) {
    // Private browsing and storage quotas must not prevent the shell opening.
  }
}

export function createShellState(preferences = {}, panelState = readPersistedPanelState()) {
  return {
    isOpen: panelState.isOpen !== false,
    isMinimized: panelState.isMinimized === true,
    status: "idle",
    error: "",
    preferences: { ...DEFAULT_PREFERENCES, ...preferences },
  };
}

export function reduceShellState(state, action) {
  switch (action.type) {
    case "open":
      return { ...state, isOpen: true, isMinimized: false };
    case "close":
      return { ...state, isOpen: false, isMinimized: false };
    case "toggle-minimize":
      return { ...state, isMinimized: !state.isMinimized };
    case "configuration-loading":
      return { ...state, status: "loading", error: "" };
    case "configuration-loaded":
      return {
        ...state,
        status: "ready",
        error: "",
        preferences: { ...state.preferences, ...action.preferences },
      };
    case "configuration-error":
      return {
        ...state,
        status: "degraded",
        error: action.message || "Preferences are temporarily unavailable.",
      };
    default:
      return state;
  }
}
