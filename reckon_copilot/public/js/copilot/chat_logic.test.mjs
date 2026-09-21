import assert from "node:assert/strict";
import test from "node:test";

import { canAsk, normalizeAskResponse } from "./chat_logic.mjs";

test("normal ask response becomes assistant message", () => {
  const message = normalizeAskResponse({
    ok: true,
    answer: { answer: "Use the payment reminder.", confidence: "high", source: "ollama" },
    cache_hit: true,
    provider: "ollama",
    model: "llama",
  });

  assert.equal(message.text, "Use the payment reminder.");
  assert.equal(message.meta.cacheHit, true);
  assert.equal(message.meta.provider, "ollama");
});

test("permission response stays inside copilot as warning", () => {
  const message = normalizeAskResponse({ ok: false, access_denied: true, message: "No access" });

  assert.equal(message.tone, "warning");
  assert.equal(message.text, "No access");
});

test("ask is disabled when context is missing or denied", () => {
  assert.equal(canAsk("Hello", null), false);
  assert.equal(canAsk("Hello", { access_denied: true }), false);
  assert.equal(canAsk("Hello", { page_type: "List" }), true);
});
