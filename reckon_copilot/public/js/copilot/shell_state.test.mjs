import assert from "node:assert/strict";
import test from "node:test";

import {
  createShellState,
  PANEL_STATE_STORAGE_KEY,
  persistPanelState,
  readPersistedPanelState,
  reduceShellState,
} from "./shell_state.mjs";

test("shell opens, minimizes, and closes without losing preferences", () => {
  let state = createShellState({ response_sound_enabled: true });

  state = reduceShellState(state, { type: "open" });
  assert.equal(state.isOpen, true);
  assert.equal(state.isMinimized, false);

  state = reduceShellState(state, { type: "toggle-minimize" });
  assert.equal(state.isMinimized, true);

  state = reduceShellState(state, { type: "close" });
  assert.equal(state.isOpen, false);
  assert.equal(state.preferences.response_sound_enabled, true);
});

test("backend errors retain usable local defaults", () => {
  let state = createShellState();
  state = reduceShellState(state, {
    type: "configuration-error",
    message: "Preferences are temporarily unavailable.",
  });

  assert.equal(state.isOpen, true);
  assert.equal(state.preferences.enabled, true);
  assert.equal(state.status, "degraded");
  assert.match(state.error, /temporarily unavailable/);
});

test("panel state persists independently from server preferences", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  };

  persistPanelState({ isOpen: true, isMinimized: true }, storage);
  assert.deepEqual(readPersistedPanelState(storage), { isOpen: true, isMinimized: true });
  assert.equal(values.has(PANEL_STATE_STORAGE_KEY), true);
  assert.equal(createShellState({}, readPersistedPanelState(storage)).isMinimized, true);
});

test("invalid panel storage is ignored", () => {
  const storage = {
    getItem: () => "not-json",
    setItem: () => null,
  };

  assert.deepEqual(readPersistedPanelState(storage), {});
  assert.equal(createShellState({}, readPersistedPanelState(storage)).isOpen, true);
});
