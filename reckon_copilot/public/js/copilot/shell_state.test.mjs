import assert from "node:assert/strict";
import test from "node:test";

import { createShellState, reduceShellState } from "./shell_state.mjs";

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
