export const DEFAULT_PREFERENCES = Object.freeze({
  enabled: true,
  notifications_enabled: true,
  response_sound_enabled: false,
});

export function createShellState(preferences = {}) {
  return {
    isOpen: true,
    isMinimized: false,
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
