import assert from "node:assert/strict";
import test from "node:test";

import { formatAnswer, parseStructuredAnswer } from "./answer_format.mjs";

test("formats a JSON briefing into readable sections", () => {
  const result = formatAnswer(JSON.stringify({
    title: "Daily Briefing for Crystal Traders",
    company: "Crystal Traders",
    priority: "High",
    next_areas: ["Review Sales Forecast for Q4 2026", "Update Inventory Levels"],
    visible_kpi_cards: [{ label: "Sales Growth", value: "Unavailable" }],
    charts: [{ label: "Sales by Region", data: "Unavailable" }],
  }));

  assert.equal(result.kind, "structured");
  assert.equal(result.title, "Daily Briefing for Crystal Traders");
  assert.deepEqual(result.details, [
    { label: "Company", value: "Crystal Traders" },
    { label: "Priority", value: "High" },
  ]);
  assert.deepEqual(result.sections.map((section) => section.title), [
    "Next areas",
    "Key figures",
    "Charts",
  ]);
  assert.match(result.plainText, /Sales by Region: Unavailable/);
  assert.doesNotMatch(result.plainText, /^\{.*\}$/s);
});

test("parses the safe subset of Python-style provider literals", () => {
  const parsed = parseStructuredAnswer("{'title': 'Daily Briefing', 'filters': [{'Region': ['North', 'South']}], 'ready': True}");

  assert.deepEqual(parsed, {
    title: "Daily Briefing",
    filters: [{ Region: ["North", "South"] }],
    ready: true,
  });
});

test("keeps normal prose as normal prose", () => {
  const result = formatAnswer("Review the overdue sales orders before sending reminders.");

  assert.equal(result.kind, "text");
  assert.equal(result.plainText, "Review the overdue sales orders before sending reminders.");
  assert.deepEqual(result.sections, []);
});
