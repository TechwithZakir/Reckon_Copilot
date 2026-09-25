<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

import {
  askCopilotStream,
  approveDocumentImportPlan,
  executeDocumentImport,
  prepareExtractedDocumentImportPlan,
  prepareDocumentImportPlan,
  previewDocumentImport,
  runAnalytics,
  runForecasting,
} from "./api";
import { formatAnswer } from "./answer_format.mjs";
import { canAsk, normalizeAnalyticsResponse, normalizeAskResponse, normalizeForecastingResponse } from "./chat_logic.mjs";

const props = defineProps({
  initialPrompt: { type: String, default: "" },
  routeContext: { type: Object, default: null },
  models: { type: Array, default: () => [] },
  selectedModel: { type: String, default: "" },
  agentMode: { type: String, default: "copilot" },
});
const emit = defineEmits(["update:selectedModel", "update:agentMode"]);
const draft = ref(props.initialPrompt);
const messages = ref([]);
const isSending = ref(false);
const fileInput = ref(null);
const selectedFile = ref(null);
const uploadError = ref("");
const progressTimers = new Set();
const typingTimers = new Set();

const progressStages = [
  "Reading page context",
  "Checking permissions",
  "Searching approved knowledge",
  "Contacting LLM provider",
  "Composing response",
];
const analyticsStages = [
  "Reading page context",
  "Checking permissions",
  "Running bounded analysis",
  "Preparing results",
];
const forecastingStages = [
  "Reading page context",
  "Checking permissions",
  "Selecting permitted time series",
  "Calculating bounded result",
  "Preparing readable results",
];
const importStages = [
  "Reading attachment",
  "Checking page permissions",
  "Inspecting document",
  "Preparing preview",
];

watch(() => props.initialPrompt, (value) => {
  draft.value = value;
});

async function send() {
  const question = draft.value.trim();
  const attachment = selectedFile.value;
  if ((!canAsk(question, props.routeContext) && !attachment) || isSending.value) return;
  const userText = question || `Preview ${attachment.name}`;
  messages.value.push({
    role: "user",
    text: userText,
    tone: "normal",
    attachmentName: attachment?.name || "",
  });
  const assistantMessage = createProgressMessage(attachment ? "import" : props.agentMode);
  messages.value.push(assistantMessage);
  startProgress(assistantMessage);
  const requestId = createRequestId();
  draft.value = "";
  selectedFile.value = null;
  uploadError.value = "";
  isSending.value = true;
  try {
    if (attachment) {
      const response = await previewDocumentImport(
        attachment.name,
        attachment.base64,
        attachment.type,
        props.routeContext,
        props.routeContext?.doctype || "",
      );
      completeImportPreview(assistantMessage, response, attachment);
      return;
    }
    const isForecasting = ["forecasting", "anomalies"].includes(props.agentMode);
    const response = props.agentMode === "analytics"
      ? await runAnalytics(question, props.routeContext)
      : isForecasting
        ? await runForecasting(question, props.routeContext, props.agentMode)
        : await askCopilotStream({
        requestId,
        question,
        context: props.routeContext,
        selectedModel: props.selectedModel,
        onEvent: (event) => applyStreamEvent(assistantMessage, event),
      });
    if (!assistantMessage.streamDone) {
      const normalized = props.agentMode === "analytics"
        ? normalizeAnalyticsResponse(response)
        : isForecasting
          ? normalizeForecastingResponse(response)
          : normalizeAskResponse(response);
      finishProgress(assistantMessage, normalized, { reveal: !["analytics", "forecasting", "anomalies"].includes(props.agentMode) });
    }
  } catch (error) {
    finishProgress(
      assistantMessage,
      {
        role: "assistant",
        tone: "warning",
        text: error?.message || "Copilot could not answer right now.",
      },
      { reveal: true },
    );
  } finally {
    isSending.value = false;
  }
}

function createProgressMessage(mode = props.agentMode) {
  const importing = mode === "import";
  const analytics = mode === "analytics";
  const forecasting = ["forecasting", "anomalies"].includes(mode);
  return {
    role: "assistant",
    tone: "normal",
    text: "",
    progress: {
      active: true,
      stageIndex: 0,
      stages: importing ? importStages : analytics ? analyticsStages : forecasting ? forecastingStages : progressStages,
      startedAt: Date.now(),
      elapsed: "0s",
      percent: 8,
    },
    meta: {
      provider: importing ? "Document preview" : analytics ? "Analytics Agent" : forecasting ? "Forecasting Agent" : "LLM provider",
      stream: !importing && !analytics && !forecasting,
    },
    streamDone: false,
  };
}

function completeImportPreview(message, response, attachment) {
  if (!response?.ok) {
    throw new Error(response?.message || "The document preview could not be prepared.");
  }
  const preview = response.preview || {};
  const recordCount = Number(preview.record_count || 0);
  const fields = Array.isArray(preview.fields) ? preview.fields : [];
  const rows = (Array.isArray(preview.records) ? preview.records : []).slice(0, 3).map((record) => ({
    cells: Object.entries(record || {}).slice(0, 8).map(([label, value]) => ({ label, value })),
  }));
  message.importPreview = {
    ...preview,
    fields,
    rows,
    suggestedDoctypes: Array.isArray(preview.suggested_doctypes) ? preview.suggested_doctypes : [],
    warnings: Array.isArray(preview.warnings) ? preview.warnings : [],
  };
  message.sourceAttachment = attachment;
  const summary = recordCount
    ? `Preview ready: ${recordCount} record${recordCount === 1 ? "" : "s"} found in ${preview.file_name || "the attachment"}.`
    : preview.text_excerpt
      ? `Readable text extracted from ${preview.file_name || "the attachment"}. It is ready for review; structured import mapping is not available for this format.`
    : "No records were found in the attachment. The preview is still read-only.";
  finishProgress(message, {
    role: "assistant",
    tone: "normal",
    text: summary,
    meta: { provider: "Document preview", source: "Import preflight" },
  }, { reveal: false });
}

async function prepareImportPlan(message) {
  if (!message?.sourceAttachment || message.importingPlan) return;
  const preview = message.importPreview || {};
  const target = preview.target_doctype || props.routeContext?.doctype || preview.suggestedDoctypes?.[0] || "";
  if (!target) {
    message.importPlanError = "Open a target DocType page before preparing an import plan.";
    return;
  }
  message.importingPlan = true;
  message.importPlanError = "";
  try {
    const attachment = message.sourceAttachment;
    const response = await prepareDocumentImportPlan(
      attachment.name,
      attachment.base64,
      attachment.type,
      props.routeContext,
      target,
    );
    if (!response?.ok) throw new Error(response?.message || "The import plan could not be prepared.");
    message.importPlan = response.plan || null;
  } catch (error) {
    message.importPlanError = error?.message || "The import plan could not be prepared.";
  } finally {
    message.importingPlan = false;
    nextTick(scrollConversationToEnd);
  }
}

async function prepareExtractedImportPlan(message) {
  if (!message?.sourceAttachment || message.importingPlan) return;
  const preview = message.importPreview || {};
  const target = preview.target_doctype || props.routeContext?.doctype || preview.suggestedDoctypes?.[0] || "";
  if (!target) {
    message.importPlanError = "Open a target DocType page before preparing a review plan.";
    return;
  }
  const fields = Array.isArray(preview.extracted_fields) ? preview.extracted_fields : [];
  if (!fields.length) {
    message.importPlanError = "No extracted fields are available to validate.";
    return;
  }
  message.importingPlan = true;
  message.importPlanError = "";
  try {
    const attachment = message.sourceAttachment;
    const reviewedRecord = Object.fromEntries(fields.map((field) => [field.fieldname, field.value]));
    const response = await prepareExtractedDocumentImportPlan(
      attachment.name,
      attachment.base64,
      attachment.type,
      props.routeContext,
      target,
      reviewedRecord,
    );
    if (!response?.ok) throw new Error(response?.message || "The review plan could not be prepared.");
    message.importPlan = response.plan || null;
  } catch (error) {
    message.importPlanError = error?.message || "The review plan could not be prepared.";
  } finally {
    message.importingPlan = false;
    nextTick(scrollConversationToEnd);
  }
}

async function approveImportPlan(message) {
  if (!message?.importPlan || message.importApproving || message.importApproved) return;
  message.importApproving = true;
  message.importPlanError = "";
  try {
    const response = await approveDocumentImportPlan(message.importPlan);
    if (!response?.ok || !response.approval_token) {
      throw new Error(response?.message || "Approval could not be recorded.");
    }
    message.importApprovalToken = response.approval_token;
    message.importApproved = true;
  } catch (error) {
    message.importPlanError = error?.message || "Approval could not be recorded.";
  } finally {
    message.importApproving = false;
  }
}

async function executeImport(message) {
  if (!message?.importPlan || !message.importApprovalToken || !message.sourceAttachment || message.importExecuting) return;
  message.importExecuting = true;
  message.importPlanError = "";
  try {
    const attachment = message.sourceAttachment;
    const response = await executeDocumentImport(
      message.importPlan,
      message.importApprovalToken,
      attachment.name,
      attachment.base64,
      attachment.type,
    );
    if (!response?.ok) throw new Error(response?.message || "Import could not be completed.");
    message.importResult = response.result_name || `Imported ${response.created_count || 0} record(s).`;
    message.importApprovalToken = "";
    message.importApproved = false;
    message.sourceAttachment = null;
  } catch (error) {
    message.importPlanError = error?.message || "Import could not be completed.";
  } finally {
    message.importExecuting = false;
  }
}

function startProgress(message) {
  let tick = 0;
  const timer = window.setInterval(() => {
    if (!message.progress?.active) {
      window.clearInterval(timer);
      progressTimers.delete(timer);
      return;
    }
    tick += 1;
    message.progress.elapsed = `${Math.max(1, Math.round((Date.now() - message.progress.startedAt) / 1000))}s`;
    const stageFloor = Math.round((message.progress.stageIndex / message.progress.stages.length) * 78);
    const softTick = Math.min(14, tick * 2);
    message.progress.percent = Math.min(92, Math.max(message.progress.percent, stageFloor + softTick));
    nextTick(scrollConversationToEnd);
  }, 1000);
  progressTimers.add(timer);
}

function applyStreamEvent(message, event) {
  if (message.cancelled) return;
  if (event.event === "stage") {
    const stageIndex = message.progress.stages.indexOf(event.stage);
    if (stageIndex >= 0) {
      message.progress.stageIndex = stageIndex;
    }
    message.progress.percent = Math.max(message.progress.percent || 0, Number(event.percent || 0));
    message.meta = {
      ...(message.meta || {}),
      provider: event.provider || message.meta?.provider,
      model: event.model || message.meta?.model,
      stream: true,
    };
    nextTick(scrollConversationToEnd);
    return;
  }
  if (event.event === "token") {
    message.text = `${message.text || ""}${event.text || ""}`;
    message.progress.percent = Math.max(message.progress.percent || 0, Number(event.percent || 0));
    nextTick(scrollConversationToEnd);
    return;
  }
  if (event.event === "done") {
    message.streamDone = true;
    finishProgress(message, normalizeAskResponse(event.result), { reveal: false });
    return;
  }
  if (event.event === "error") {
    message.streamDone = true;
    finishProgress(message, normalizeAskResponse(event), { reveal: false });
  }
}

function finishProgress(message, normalized, options = {}) {
  if (message.cancelled) return;
  const responseText = normalized.text || "No answer was found for this page context.";
  const answer = formatAnswer(responseText);
  message.tone = normalized.tone || "normal";
  message.answer = answer;
  message.answerReady = !options.reveal;
  message.analytics = normalized.meta?.analytics || null;
  message.forecasting = normalized.meta?.forecasting || null;
  message.meta = {
    ...(normalized.meta || {}),
    stream: Boolean(message.meta?.stream),
    tokens: message.meta?.tokens || estimateTokens(message.text || responseText),
  };
  message.progress = {
    ...(message.progress || {}),
    active: false,
    stageIndex: (message.progress?.stages || progressStages).length - 1,
    elapsed: message.progress?.elapsed || "0s",
    percent: 100,
  };
  message.progress.label = "Completed";
  if (options.reveal) {
    typeAnswer(message, answer.plainText || responseText);
  } else {
    message.text = answer.plainText || responseText;
    message.meta.tokens = estimateTokens(message.text);
  }
}

function estimateTokens(text) {
  return Math.max(1, Math.ceil(String(text || "").length / 4));
}

function chartBarWidth(chart, index) {
  const values = chart?.datasets?.[0]?.data || [];
  const numeric = values.map((value) => Number(value)).filter((value) => Number.isFinite(value));
  const current = Number(values[index]);
  if (!Number.isFinite(current) || !numeric.length) return "0%";
  const maximum = Math.max(...numeric.map((value) => Math.abs(value)), 1);
  return `${Math.max(4, Math.round((Math.abs(current) / maximum) * 100))}%`;
}

function typeAnswer(message, text) {
  message.text = "";
  if (!text) return;
  let index = 0;
  const step = Math.max(3, Math.ceil(text.length / 80));
  const timer = window.setInterval(() => {
    index = Math.min(text.length, index + step);
    message.text = text.slice(0, index);
    if (index >= text.length) {
      window.clearInterval(timer);
      typingTimers.delete(timer);
      message.answerReady = true;
      nextTick(scrollConversationToEnd);
    }
  }, 18);
  typingTimers.add(timer);
}

function scrollConversationToEnd() {
  const el = document.querySelector(".rc-conversation");
  if (el) el.scrollTop = el.scrollHeight;
}

function clearConversation() {
  messages.value = [];
  selectedFile.value = null;
  uploadError.value = "";
}

function openFilePicker() {
  if (!props.routeContext || props.routeContext.access_denied || isSending.value) return;
  fileInput.value?.click();
}

function clearAttachment() {
  selectedFile.value = null;
  uploadError.value = "";
}

function handleFileSelected(event) {
  const file = event.target?.files?.[0];
  event.target.value = "";
  if (!file) return;
  if (file.size > 4 * 1024 * 1024) {
    selectedFile.value = null;
    uploadError.value = "Choose a document smaller than 4 MB for a safe preview.";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = String(reader.result || "");
    const separator = dataUrl.indexOf(",");
    if (separator < 0) {
      uploadError.value = "The selected document could not be read.";
      return;
    }
    selectedFile.value = {
      name: file.name,
      type: file.type,
      size: file.size,
      base64: dataUrl.slice(separator + 1),
    };
    uploadError.value = "";
  };
  reader.onerror = () => {
    selectedFile.value = null;
    uploadError.value = "The selected document could not be read.";
  };
  reader.readAsDataURL(file);
}

function cancelConversation() {
  const message = messages.value[messages.value.length - 1];
  if (!message || !isSending.value) return;
  message.cancelled = true;
  message.tone = "warning";
  message.text = "Request cancelled. No response was sent.";
  message.progress = {
    ...(message.progress || {}),
    active: false,
    label: "Cancelled",
    percent: message.progress?.percent || 0,
  };
  isSending.value = false;
}

function createRequestId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `rc-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

onBeforeUnmount(() => {
  for (const timer of progressTimers) window.clearInterval(timer);
  for (const timer of typingTimers) window.clearInterval(timer);
  progressTimers.clear();
  typingTimers.clear();
});
</script>

<template>
  <section class="rc-composer-shell" aria-labelledby="rc-chat-title">
    <div class="rc-chat-toolbar">
      <h3 id="rc-chat-title">Conversation</h3>
      <div class="rc-agent-mode" role="group" aria-label="Choose agent">
        <button
          type="button"
          :class="{ 'is-active': agentMode === 'copilot' }"
          :aria-pressed="agentMode === 'copilot'"
          @click="emit('update:agentMode', 'copilot')"
        >
          Copilot
        </button>
        <button
          type="button"
          :class="{ 'is-active': agentMode === 'analytics' }"
          :aria-pressed="agentMode === 'analytics'"
          @click="emit('update:agentMode', 'analytics')"
        >
          Analytics
        </button>
        <button
          type="button"
          :class="{ 'is-active': agentMode === 'forecasting' }"
          :aria-pressed="agentMode === 'forecasting'"
          @click="emit('update:agentMode', 'forecasting')"
        >
          Forecast
        </button>
        <button
          type="button"
          :class="{ 'is-active': agentMode === 'anomalies' }"
          :aria-pressed="agentMode === 'anomalies'"
          @click="emit('update:agentMode', 'anomalies')"
        >
          Anomalies
        </button>
      </div>
      <button
        v-if="isSending"
        class="rc-clear-chat rc-cancel-chat"
        type="button"
        @click="cancelConversation"
      >
        Cancel
      </button>
      <button
        v-else-if="messages.length"
        class="rc-clear-chat"
        type="button"
        @click="clearConversation"
      >
        Clear
      </button>
    </div>
    <div v-if="messages.length" class="rc-conversation" aria-live="polite">
      <article
        v-for="(message, index) in messages"
        :key="`${message.role}-${index}`"
        class="rc-message"
        :class="[`is-${message.role}`, { 'is-warning': message.tone === 'warning' }]"
      >
        <template v-if="message.answerReady && message.answer?.kind === 'structured'">
          <div class="rc-answer-content">
            <h4>{{ message.answer.title }}</h4>
            <p v-if="message.answer.summary" class="rc-answer-summary">{{ message.answer.summary }}</p>
            <dl v-if="message.answer.details?.length" class="rc-answer-details">
              <div v-for="detail in message.answer.details" :key="`${detail.label}-${detail.value}`">
                <dt>{{ detail.label }}</dt>
                <dd>{{ detail.value }}</dd>
              </div>
            </dl>
            <section v-for="section in message.answer.sections" :key="section.title" class="rc-answer-section">
              <h5>{{ section.title }}</h5>
              <ul>
                <li v-for="item in section.items" :key="item">{{ item }}</li>
              </ul>
            </section>
          </div>
        </template>
        <p v-else>{{ message.text }}</p>
        <div v-if="message.analytics" class="rc-analytics-result">
          <div v-if="message.analytics.metrics?.length" class="rc-analytics-metrics">
            <span v-for="metric in message.analytics.metrics" :key="`${metric.label}-${metric.value}`">
              <small>{{ metric.label }}</small>
              <strong>{{ metric.value }}</strong>
            </span>
          </div>
          <table v-if="message.analytics.table?.rows?.length" class="rc-analytics-table">
            <thead>
              <tr>
                <th v-for="column in message.analytics.table.columns" :key="column.key">{{ column.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in message.analytics.table.rows" :key="rowIndex">
                <td v-for="column in message.analytics.table.columns" :key="column.key">{{ row[column.key] }}</td>
              </tr>
            </tbody>
          </table>
          <div
            v-if="message.analytics.chart?.labels?.length && message.analytics.chart?.datasets?.length"
            class="rc-analytics-chart"
            role="img"
            :aria-label="message.analytics.chart.title"
          >
            <strong>{{ message.analytics.chart.title }}</strong>
            <div v-for="(label, chartIndex) in message.analytics.chart.labels" :key="`${label}-${chartIndex}`" class="rc-chart-row">
              <span>{{ label }}</span>
              <i><b :style="{ width: chartBarWidth(message.analytics.chart, chartIndex) }"></b></i>
              <em>{{ message.analytics.chart.datasets[0].data[chartIndex] }}</em>
            </div>
          </div>
          <small class="rc-analytics-source">Read-only analysis · {{ message.analytics.tool_label }}</small>
        </div>
        <div v-if="message.forecasting" class="rc-analytics-result rc-forecasting-result">
          <div v-if="message.forecasting.metrics?.length" class="rc-analytics-metrics">
            <span v-for="metric in message.forecasting.metrics" :key="`${metric.label}-${metric.value}`">
              <small>{{ metric.label }}</small>
              <strong>{{ metric.value }}</strong>
            </span>
          </div>
          <table v-if="message.forecasting.table?.rows?.length" class="rc-analytics-table">
            <thead>
              <tr>
                <th v-for="column in message.forecasting.table.columns" :key="column.key">{{ column.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in message.forecasting.table.rows" :key="rowIndex">
                <td v-for="column in message.forecasting.table.columns" :key="column.key">{{ row[column.key] }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="message.forecasting.anomalies?.length" class="rc-forecasting-anomalies">
            <strong>Observations to review</strong>
            <p v-for="item in message.forecasting.anomalies" :key="`${item.period}-${item.value}`">
              {{ item.period }}: {{ item.value }} vs expected {{ item.expected }} ({{ item.severity }} priority)
            </p>
          </div>
          <small class="rc-analytics-source">Read-only deterministic result · {{ message.forecasting.tool_label }}</small>
        </div>
        <div v-if="message.importPreview" class="rc-import-preview">
          <div class="rc-import-preview-heading">
            <strong>Document preview</strong>
            <span>{{ message.importPreview.format?.toUpperCase() }}</span>
          </div>
          <p>
            {{ message.importPreview.file_name }} · {{ message.importPreview.record_count }} record{{ message.importPreview.record_count === 1 ? "" : "s" }}
          </p>
          <div v-if="message.importPreview.fields?.length" class="rc-import-fields">
            <span v-for="field in message.importPreview.fields" :key="field">{{ field }}</span>
          </div>
          <div v-for="(row, rowIndex) in message.importPreview.rows" :key="rowIndex" class="rc-import-row">
            <span v-for="cell in row.cells" :key="`${rowIndex}-${cell.label}`">
              <b>{{ cell.label }}:</b> {{ cell.value }}
            </span>
          </div>
          <p v-if="message.importPreview.text_excerpt" class="rc-import-excerpt">
            {{ message.importPreview.text_excerpt }}
          </p>
          <div v-if="message.importPreview.extracted_fields?.length" class="rc-import-extracted">
            <strong>Extracted fields for review</strong>
            <div v-for="field in message.importPreview.extracted_fields" :key="field.fieldname" class="rc-import-extracted-row">
              <span>
                <b>{{ field.label }}</b>
                <small>{{ field.source }} · {{ field.confidence }} confidence</small>
              </span>
              <input v-model="field.value" class="rc-import-extracted-input" :aria-label="`Review ${field.label}`" />
            </div>
          </div>
          <ul v-if="message.importPreview.extraction_warnings?.length" class="rc-message-notes">
            <li v-for="warning in message.importPreview.extraction_warnings" :key="warning">{{ warning }}</li>
          </ul>
          <p v-if="message.importPreview.suggestedDoctypes?.length" class="rc-import-suggestion">
            Possible DocType: {{ message.importPreview.suggestedDoctypes.join(", ") }}
          </p>
          <ul v-if="message.importPreview.warnings?.length" class="rc-message-notes">
            <li v-for="warning in message.importPreview.warnings" :key="warning">{{ warning }}</li>
          </ul>
          <small class="rc-analytics-source">Preview only · No ERP document was created or changed.</small>
          <button
            v-if="message.sourceAttachment && message.importPreview.structured !== false && !message.importPlan && (message.importPreview.target_doctype || routeContext?.doctype || message.importPreview.suggestedDoctypes?.length)"
            class="rc-import-plan-button"
            type="button"
            :disabled="message.importingPlan"
            @click="prepareImportPlan(message)"
          >
            {{ message.importingPlan ? "Preparing dry run..." : "Prepare import plan" }}
          </button>
          <button
            v-if="message.sourceAttachment && message.importPreview.structured === false && message.importPreview.extracted_fields?.length && !message.importPlan && (message.importPreview.target_doctype || routeContext?.doctype || message.importPreview.suggestedDoctypes?.length)"
            class="rc-import-plan-button"
            type="button"
            :disabled="message.importingPlan"
            @click="prepareExtractedImportPlan(message)"
          >
            {{ message.importingPlan ? "Checking reviewed fields..." : "Prepare review plan" }}
          </button>
          <p v-if="message.importPlanError" class="rc-import-plan-error">{{ message.importPlanError }}</p>
          <div v-if="message.importPlan" class="rc-import-plan">
            <div class="rc-import-preview-heading">
              <strong>Dry-run import plan</strong>
              <span>{{ message.importPlan.target_doctype }}</span>
            </div>
            <p>
              {{ message.importPlan.row_count }} row{{ message.importPlan.row_count === 1 ? "" : "s" }} ·
              {{ message.importPlan.mappings?.length || 0 }} mapped field{{ message.importPlan.mappings?.length === 1 ? "" : "s" }}
            </p>
            <dl class="rc-import-plan-stats">
              <div><dt>Errors</dt><dd>{{ message.importPlan.error_count }}</dd></div>
              <div><dt>Unmapped</dt><dd>{{ message.importPlan.unmapped_fields?.length || 0 }}</dd></div>
              <div><dt>Approval</dt><dd>{{ message.importPlan.ready_for_approval ? "Ready later" : "Needs review" }}</dd></div>
            </dl>
            <ul v-if="message.importPlan.errors?.length" class="rc-message-notes rc-import-plan-errors">
              <li v-for="error in message.importPlan.errors" :key="error.row">
                Row {{ error.row }}: {{ error.messages.join("; ") }}
              </li>
            </ul>
            <ul v-if="message.importPlan.warnings?.length" class="rc-message-notes">
              <li v-for="warning in message.importPlan.warnings" :key="warning">{{ warning }}</li>
            </ul>
            <small v-if="message.importPlan.execution === 'review_only'" class="rc-analytics-source">Review plan only · PDF/DOCX approval and execution are not available yet.</small>
            <small v-else class="rc-analytics-source">Dry run validated · Approval is required before any ERP document is created.</small>
            <div v-if="message.importPlan.ready_for_approval" class="rc-import-plan-actions">
              <button
                v-if="!message.importApproved"
                class="rc-import-plan-button"
                type="button"
                :disabled="message.importApproving"
                @click="approveImportPlan(message)"
              >
                {{ message.importApproving ? "Requesting approval..." : "Approve import" }}
              </button>
              <button
                v-else
                class="rc-import-plan-button is-primary"
                type="button"
                :disabled="message.importExecuting"
                @click="executeImport(message)"
              >
                {{ message.importExecuting ? "Importing..." : "Execute approved import" }}
              </button>
            </div>
            <p v-if="message.importResult" class="rc-import-result">{{ message.importResult }}</p>
          </div>
        </div>
        <div v-if="message.progress" class="rc-progress-card" :class="{ 'is-complete': !message.progress.active }">
          <div class="rc-progress-line">
            <span class="rc-progress-spinner" aria-hidden="true"></span>
            <strong>{{ message.progress.active ? message.progress.stages[message.progress.stageIndex] : message.progress.label }}</strong>
            <em>{{ message.progress.elapsed }}</em>
          </div>
          <div
            class="rc-progress-meter"
            role="progressbar"
            :aria-valuenow="message.progress.percent"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <span :style="{ width: `${message.progress.percent}%` }"></span>
          </div>
          <ol class="rc-progress-stages">
            <li
              v-for="(stage, stageIndex) in message.progress.stages"
              :key="stage"
              :class="{
                'is-done': stageIndex < message.progress.stageIndex || !message.progress.active,
                'is-active': stageIndex === message.progress.stageIndex && message.progress.active,
              }"
            >
              {{ stage }}
            </li>
          </ol>
        </div>
        <small v-if="message.meta">
          {{ message.meta.intent || message.meta.source || message.meta.provider || "copilot" }}
          <span v-if="message.meta.cacheHit">cached</span>
          <span v-if="message.meta.model">Model: {{ message.meta.model }}</span>
          <span v-if="message.meta.stream">Realtime stream</span>
          <span v-if="message.meta.tokens">Tokens: {{ message.meta.tokens }}</span>
        </small>
        <div v-if="message.meta?.evidence?.length" class="rc-evidence-list" aria-label="Evidence">
          <span
            v-for="item in message.meta.evidence"
            :key="item.chunk_id"
            class="rc-evidence-chip"
            :title="item.locator"
          >
            {{ item.source_title || item.chunk_id }}
          </span>
        </div>
        <ul v-if="message.meta?.warnings?.length" class="rc-message-notes">
          <li v-for="warning in message.meta.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <div v-if="message.meta?.followups?.length" class="rc-followups">
          <button
            v-for="followup in message.meta.followups"
            :key="followup"
            class="rc-followup"
            type="button"
            @click="draft = followup"
          >
            {{ followup }}
          </button>
        </div>
      </article>
    </div>
    <input
      ref="fileInput"
      class="rc-sr-only"
      type="file"
      accept=".csv,.tsv,.json,.txt,.md,.pdf,.docx,text/csv,application/json,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      @change="handleFileSelected"
    />
    <div v-if="selectedFile" class="rc-attachment-chip">
      <span aria-hidden="true">&#128206;</span>
      <strong>{{ selectedFile.name }}</strong>
      <button type="button" aria-label="Remove attachment" @click="clearAttachment">&times;</button>
    </div>
    <p v-if="uploadError" class="rc-upload-error">{{ uploadError }}</p>
    <div class="rc-composer-box">
      <button
        class="rc-attach-button"
        type="button"
        :disabled="!routeContext || routeContext.access_denied || isSending"
        aria-label="Attach document for preview"
        title="Attach a CSV, TSV, JSON, or text document for a read-only preview"
        @click="openFilePicker"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m21.4 11.6-8.8 8.8a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 1 1-2.8-2.8l8.5-8.5" />
        </svg>
      </button>
      <textarea
        v-model="draft"
        rows="2"
        placeholder="Ask anything about this page..."
        :disabled="!routeContext || routeContext.access_denied || isSending"
        @keydown.enter.exact.prevent="send"
      />
      <button
        class="rc-send-button"
        type="button"
        :disabled="!canAsk(draft, routeContext) || isSending"
        aria-label="Send message"
        @click="send"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="m5 12 14-7-4 14-3-6-7-1Z" />
          <path d="m12 13 7-8" />
        </svg>
      </button>
    </div>
    <div class="rc-composer-help">
      <span>Enter to send · Shift + Enter for new line</span>
      <span>/ to see prompts</span>
    </div>
  </section>
</template>
