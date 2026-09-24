import assert from "node:assert/strict";
import test from "node:test";

import { canAsk, normalizeAnalyticsResponse, normalizeAskResponse, normalizeForecastingResponse } from "./chat_logic.mjs";

test("normal ask response becomes assistant message", () => {
  const message = normalizeAskResponse({
    ok: true,
    answer: { answer: "Use the payment reminder.", confidence: "high", source: "local_llm" },
    cache_hit: true,
    provider: "local_llm",
    model: "llama",
  });

  assert.equal(message.text, "Use the payment reminder.");
  assert.equal(message.meta.cacheHit, true);
  assert.equal(message.meta.provider, "local_llm");
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

test("analytics response keeps structured table and chart data", () => {
  const message = normalizeAnalyticsResponse({
    ok: true,
    agent: "analytics",
    narrative: "I found 3 permitted records.",
    intent: "breakdown",
    table: { columns: [{ key: "group", label: "Customer" }], rows: [{ group: "Crystal Traders" }] },
    chart: { type: "bar", labels: ["Crystal Traders"], datasets: [{ label: "Total", data: [250] }] },
  });

  assert.equal(message.text, "I found 3 permitted records.");
  assert.equal(message.meta.provider, "Analytics Agent");
  assert.equal(message.meta.analytics.chart.type, "bar");
  assert.equal(message.meta.analytics.table.rows[0].group, "Crystal Traders");
});

test("forecasting response keeps compact forecast and safety metadata", () => {
  const message = normalizeForecastingResponse({
    ok: true,
    agent: "forecasting",
    narrative: "The outlook is expected to increase.",
    intent: "forecast",
    safety: { read_only: true, writes: false, model_training: false },
    forecast: { values: [120, 140] },
    anomalies: [],
  });

  assert.equal(message.text, "The outlook is expected to increase.");
  assert.equal(message.meta.provider, "Forecasting Agent");
  assert.deepEqual(message.meta.forecasting.forecast.values, [120, 140]);
  assert.equal(message.meta.forecasting.safety.writes, false);
});
