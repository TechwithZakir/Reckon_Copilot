# Reckon Copilot Phase Context Notes

## Current status

Phase 1 is complete as a Desk shell and overlay UI.

Phase 2 is implemented as route synchronization, sanitized context shape and deterministic fingerprinting. The frontend displays the active context label and the backend returns a canonical, versioned context object with a deterministic fingerprint.

Phase 3 is implemented as the server-side permission boundary for Copilot capabilities. Context, knowledge, cache and provider calls must use `reckon_copilot.permissions.boundary` instead of ad-hoc permission checks. Permission failures must be shown in the Copilot panel and must not surface as Frappe server-error modals.

Phase 4 is implemented as the Knowledge Engine and RAG-ready retrieval foundation. It includes Knowledge Source, Knowledge Document, Knowledge Chunk, Knowledge Ingestion Job and Knowledge Vector Index records, source/version/status metadata, extraction/chunking/retrieval services, compact evidence objects and permission-aware retrieval boundaries.

Phase 5 is implemented as permission-safe caching. Cache identities include context fingerprint, permission scope, site, capability, provider/model, prompt/data versions and question/evidence details. Cache failures must degrade to direct computation.

Phase 6 is implemented as the local-first LLM provider path. The current implementation uses configurable `Copilot Provider` records, no hard-coded model, provider usage logs, timeout/retry settings, optional `Stream Response`, detailed metadata logging and Frappe realtime streaming for token/progress events.

Phase 7 foundation is implemented as deterministic, permission-bound insights. The implementation adds a reusable `reckon_copilot.insights` responsibility area, a whitelisted insights API, structured findings with severity/source/confidence/suggested prompts, evidence compaction and visible Key Insights cards/counters in the Copilot panel.

Phase 8 foundation is implemented as proactive, permission-bound notifications and alerts. The implementation adds a reusable `reckon_copilot.notifications` responsibility area, a whitelisted notifications API, deterministic alert IDs, panel-safe permission-denied alerts and a Copilot panel Alerts section driven by warning/critical findings.

The next planned phase should extend notifications into persistence, user dismissal state and optional scheduled/server-pushed alert jobs after the latest Phase 8 commit is pushed, deployed, migrated if needed, cache-cleared and manually verified on the target bench.

## Phase 9 planned scope

Phase 9 will add the Contextual Agent Advisor and Safe Action Planning layer. Its provider work must include a multi-model provider contract: administrators can configure an allowlisted set of models, the Copilot selector sends the selected model to the server, the server validates it against the active provider and capability policy, and the selected model is included in permission-safe cache identities and usage logs. The selector must never be cosmetic or allow arbitrary model names from the browser.

Phase 9 implementation has started with a permission-bound Agent Advisor API and service. It generates context-specific read-only questions and review-plan actions for List, Form, Report, Dashboard and Workspace contexts. Mutating actions are intentionally not exposed yet; future action execution must add explicit approval and audit handling.

The provider contract now includes an administrator-managed `Allowed Models` allowlist. Server-side provider selection rejects any model not in that allowlist; the future Copilot selector must consume these validated options and never submit arbitrary browser model names.

The Phase 9 UI now receives the validated model list from the server and sends the selected model with each ask/stream request. The provider manager re-validates the selection before calling the LLM, and the selected model remains part of the permission-safe cache identity.

The Phase 9 Copilot composer was visually refined with a compact model control, cleaner input hierarchy and deduplicated contextual recommendations so Actions and Quick Questions do not repeat the same prompts.

The model selector is positioned in the runtime footer beside the LLM provider status, keeping provider choice separate from message composition while preserving server-side validation.

The runtime footer uses responsive alignment for provider and model controls. Placeholder usage text was removed; actual token estimates remain attached to completed conversation responses.

Phase 9 now includes a preview-first action planner for create, update, delete, submit and approve intents. Plans are permission-bound, redact secret-like values, mark high-risk operations, require confirmation metadata and carry a deterministic plan hash. Execution remains disabled until the explicit approval and audit workflow is implemented.

The frontend API boundary now exposes preview requests for the upcoming approval dialog. No execution endpoint is exposed; the next UI step must render the plan, risk and hash and require explicit approval before any future execution capability is enabled.

The Copilot panel now renders a preview approval dialog for Form contexts, including target, execution mode, risk and plan hash. Approving closes the preview only; it does not execute an ERPNext write.

Phase 9 now issues short-lived HMAC approval tokens scoped to the exact plan hash, user and site. The approval endpoint records approval intent but returns `execution: disabled`; no token can execute a write until a separately audited executor is implemented.

## Phase 9 completion

Phase 9 is complete. It delivers the contextual Agent Advisor, server-validated multi-model selection, preview-first action planning, permission-bound Form action previews, redacted plan values, deterministic plan hashes and short-lived signed approval tokens. The phase deliberately stops before ERPNext mutation: approved plans still return `execution: disabled`. Actual create, update, delete, submit and approve execution belongs to the next action-execution phase and must add native DocType permission checks, audit records, idempotency, transaction/error handling and rollback or compensation behavior.

The next phase is the separate read-only Analytics Agent. Controlled ERP
actions remain a later phase and must not contaminate the lightweight Copilot
path.

## Phase 10 analytics agent

Phase 10 adds a separate, read-only Analytics Agent. The agent is reached
through `reckon_copilot.api.analytics.run` and the `Analytics` mode in the
Copilot conversation. Intent routing selects only one of three registered
tools: current-page summary, grouped breakdown or time trend. User text is
never converted into SQL, Python or an arbitrary tool name.

The service authorizes the canonical context with `analytics.run` before any
data access. Frappe-backed analysis reads only allowlisted metadata fields via
permission-aware ORM list access, caps the row count and output points, and
returns a compact narrative, metrics, table and chart-ready dataset. Dashboard
analysis uses the existing permission-scoped KPI/chart snapshot. The metrics
engine uses Pandas when the bench provides it and a bounded Python fallback
when it does not; callers do not change between engines.

The panel defaults to the normal Copilot path, so basic questions stay on the
lower-cost provider flow. Users can explicitly choose Analytics and see the
bounded analysis progress, readable metrics/table output and chart bars. Each
run is recorded through the existing usage logger with the analytics
capability, selected tool, engine and duration.

## Phase 10 completion

Phase 10 is complete. It delivers the separate Analytics Agent UI mode,
allowlisted intent routing, permission-aware Frappe data access, bounded
Python/Pandas metrics, chart-ready results, human-readable analysis
narratives, execution limits and usage logging. The analytics tests cover
summary relevance, breakdown and trend output, dashboard snapshots,
permission boundaries, row limits and audit/usage records.

The audit DocType package includes its standard Frappe controller module and
package initializer, so bench migration can import
`reckon_copilot.reckon_copilot.doctype.copilot_action_audit` successfully.

The human-readable response formatter remains part of the Copilot shell and
keeps provider briefings usable for non-technical users. Controlled writes,
invoice/document import and large-file migration remain later phases because
they require separate approval, dependency and rollback boundaries.

## Phase 11 read-only forecasting and anomaly agent

Phase 11 has started with a separate deterministic Forecasting Agent. It is
available through `reckon_copilot.api.forecasting.run` and the `Forecast` and
`Anomalies` modes in the Copilot conversation. The service authorizes the
canonical context with the dedicated read-only `forecasting.run` capability
before reading any rows or dashboard chart series.

The agent uses bounded, explainable calculations only: a linear trend for a
short forecast horizon and a recent-history deviation check for anomalies. It
supports permitted List/Form data through the existing ORM data source and
compact Dashboard chart snapshots. It returns a plain-language narrative,
small metrics/table/chart payloads and compact anomaly observations. It does
not call an LLM, write ERPNext records, create action plans or train/update a
model. The response explicitly reports `read_only`, `writes: false` and
`model_training: false` safeguards.

The Phase 11 UI shows the agent's bounded progress stages and renders forecast
values and anomaly observations as readable results. Insufficient history is a
normal user-facing result rather than an error. Tests cover forecast relevance,
outlier detection, dashboard series, insufficient history, permission
boundaries, usage logging and the no-write/no-training contract.

The forecasting import also has a rolling-deployment compatibility fallback:
workers that have loaded the new forecasting API but still have the older
permission boundary reuse the existing read-only `analytics.run` capability
until the worker restarts with the Phase 11 boundary. New workers use the
dedicated `forecasting.run` capability.

## Phase 12 controlled write actions

Phase 12 has started with the controlled action path for create, update, delete,
submit and approve operations. The path is separate from normal Copilot,
Analytics and Forecasting requests. A Form action must first pass the native
permission boundary, produce a deterministic plan hash and show a preview. A
second explicit approval issues a short-lived user/site/plan-scoped token; a
final execution click is still required before mutation.

The executor revalidates native permissions immediately before the write,
rejects protected or unknown fields, records a `Copilot Action Audit` record,
prevents duplicate execution of a completed plan and rolls back the current
transaction on mutation failure. Approval now rechecks the exact target before
issuing a token, and preview/approval failures return panel-safe messages rather
than Frappe error modals. No action is triggered by an ordinary question, and
no action runs automatically from catalog refresh, feedback learning or the
read-only Phase 11 agents. Create and update previews without explicit field
values stop at a clear next step and cannot be approved; submit and approve
previews remain the simple no-value approval path.

## Phase 9 Suggested Actions Catalog alignment

`Reckon_Copilot_Suggested_Actions_Catalog.md` is now the product reference for
contextual Suggested Actions and Quick Questions in Phase 9. The catalog is a
design and data contract, not executable instructions. It extends the Phase 9
core advisor with the following rules:

- Build candidates from trusted live context first, then verified business
  signals, administrator-approved action templates, approved knowledge and
  privacy-safe aggregate feedback.
- Rank by impact, urgency, confidence, page/DocType match, record state,
  active scope and freshness. Permissions, installed features, available
  fields and current schema are hard eligibility gates, not ranking bonuses.
- Put a permission-safe next best action first for a verified overdue item,
  blocked workflow, approval, exception or other actionable condition. Show
  the reason, evidence and scope used. Suppress duplicate, stale, unsupported
  and low-confidence candidates.
- Keep Suggested Actions and Quick Questions as separate ranked result sets,
  with independent `More suggestions` and `More Quick Questions` expansion.
  Do not use fixed limits such as two actions or three questions as the
  product contract.
- Generate page-aware candidates for Homepage, module/workspace, Dashboard,
  List, draft/submitted Form, Report, Setup/configuration and error/validation
  contexts. Resolve the actual installed app, module, DocType, fields,
  workflow/status, filters, company/date scope and permitted linked records
  before showing a field, report, feature or action.
- Keep recommendations read-only by default. A proposed create, update,
  delete, submit or approve operation must expose its target, values, risk,
  evidence and expected effect, then require explicit confirmation and a
  separately audited executor. Candidate generation and nightly refresh must
  never execute writes, change workflows or retrain the model.
- Quick Questions must be grounded in approved, version-matched knowledge and
  return source attribution. They must distinguish official product behavior
  from Reckon-specific configuration and must not suggest absent fields,
  reports or features.

The current Phase 9 core implements the runtime advisor contract, structured
reasons/priority/source/action type, page-specific prompts, permission-bound
previews and safe model selection. The catalog's continuous-learning
extension remains tracked in Phase 9: administrator-controlled source and
template records, incremental scheduled ingestion, candidate validation and
approval, versioned index snapshots with rollback, independent expansion,
privacy-safe aggregate feedback and the associated ranking/ingestion tests.
These additions must reuse the existing context, knowledge, vector-search,
cache and permission boundaries rather than introducing feature-local checks.

The first catalog runtime slice is now implemented. Advisor candidates are
deduplicated and ranked deterministically by priority, evidence source and
semantic action type without server-side truncation. The Copilot panel shows a
focused first viewport, then exposes functional independent expansion for
additional Suggested Actions and Quick Questions. Expansion state resets when
the authorized page context changes, and no new write capability is introduced.
The ranking contract is covered by advisor tests and the UI remains compatible
with older deployments because it consumes the existing advisor response.

The catalog implementation is complete for this phase. It uses the reusable
`AdvisorCatalog` interface with approved read-only templates and covers the
document mappings in the supplied catalog across Framework, ERPNext Accounts,
Selling, Buying, Stock, Manufacturing, Assets, Projects, CRM, POS and HRMS.
Each supported DocType has context-specific List and Form actions/questions
with source references, catalog versions, reasons, priorities and intent types.
Templates are shown only when the resolved page type, actual DocType and
required effective fields match. Unsafe write intents, disabled templates,
missing fields and unrelated DocTypes are rejected before recommendations reach
the panel. A future Frappe repository can supply administrator-managed
templates through this interface without changing advisor callers.

This catalog completion has no dependency on Phase 11. Phase 11 can consume
the same read-only advisor results while adding deterministic forecasting and
anomaly calculations; it does not need to change catalog callers.

## Controlled advisor learning completion

The catalog now has a controlled feedback loop before Phase 11. The browser
records only coarse outcomes for catalog suggestions (`selected` and
`not_relevant`/`too_generic`), keyed by a hash of the template and safe page
identity. It never stores a user, document name, raw prompt, document value or
page HTML in feedback aggregates.

Repeated negative feedback is converted into a pending `Copilot Catalog
Candidate`. The daily job generates candidates only; it never publishes a
prompt, retrains an LLM, changes a workflow or executes an ERP action. Each
candidate is validated against the currently installed field names and native
read permission before it can be approved. A System Manager must explicitly
publish it through the approval endpoint, after which it is stored as an
enabled, versioned, read-only `Copilot Suggested Action Template` and is
merged into the advisor without changing its callers. Unsafe write action types
are rejected at both candidate validation and runtime template loading.

The new aggregate, candidate, approved-template and snapshot DocTypes are
available in the Reckon Copilot workspace and administrator sidebar. Candidate
forms expose administrator-only approve/reject controls, candidate lists can
run generation, and retired snapshots expose an administrator-only activation
control. Runtime loading is restricted to the active published snapshot, with
rollback creating a new published snapshot that preserves history. This
completes the catalog's privacy-safe continuous-improvement boundary before
Phase 11; it is controlled prompt improvement, not automatic model training.

The advisor API also has a rolling-deployment compatibility fallback. If an
older worker raises because it has not loaded `authorize_action`, the endpoint
returns read-only page advice with a compatibility notice instead of allowing
an AttributeError to become a Frappe server-error modal. The fallback never
exposes document data or enables a write preview; workers should still be
restarted after deployment so the full Phase 9 boundary and catalog are used.

## Phase 9 advisor relevance enhancement

The Agent Advisor was strengthened using Frappe v16's native permission and metadata model. The implementation follows the documented behavior of `frappe.has_permission`, `frappe.get_meta`, permission-aware `frappe.db.get_list` and the document permission hooks described in the Frappe Framework documentation. Structural metadata is read only after route authorization and is reduced to safe signals: required field labels, field count, status/workflow presence, submit capability, report source DocType and compact dashboard/workspace counts. No document values, report rows, chart data or unrestricted workspace content are returned by the advisor.

Questions and actions are now page-specific and structured with stable ids, prompts, category, priority, source and a user-facing reason. List pages react to filter presence and status-like filters; Forms react to required fields, new-record state, workflow/submission metadata and native write/submit permissions; Reports react to active filters and source DocType; Dashboards and Workspaces react to compact structural counts. Form preview actions are generated from the advisor response instead of hardcoded page-type buttons.

The shared `CopilotPermissionBoundary.authorize_action` now checks native DocType/document permissions for create, update, delete, submit and approve previews. This prevents a read-only user from receiving a misleading write preview and gives the future executor one reusable permission gate. The planner and advisor both use this boundary; they do not call Frappe permissions ad hoc.

The advisor also fails closed during a rolling deployment if an old worker has not loaded `authorize_action` yet: it suppresses write previews and continues with read-only advice instead of raising a server error. Workers should still be restarted after deployment so all processes load the same boundary implementation.

Relevance and security coverage includes metadata-aware questions, filter-specific questions, permission-filtered action visibility, native document permission enforcement and safe advisor signals. The next action phase must reuse these structured recommendations and perform a second permission check immediately before any approved mutation.

The advisor output is now an end-user helpline contract (`advisor_version: v2`). Every recommendation includes a human-readable reason, priority, source label, semantic action type, execution mode and a full prompt. Domain-aware guidance is selected from the authorized page identity and safe metadata for common Sales, Purchasing, Inventory, Accounts, Projects and People flows. List guidance reacts to active filters and status fields; Form guidance reacts to required fields, workflow/submission state and new-record state; Report, Dashboard and Workspace guidance explains scope, source and next navigation. The panel renders the reason and metadata badges, while quick-question chips send the full prompt behind the short label.

## Later planned capabilities: approved actions and import workflows

Future action phases will support permission-bound actionable prompts for creating, updating, deleting, submitting and approving DocType records. Every mutating operation must produce a compact preview of the intended changes, identify the target DocType and records, validate the user's capability through the shared permission boundary, and require explicit user approval immediately before execution. Delete, submit and approve operations require an additional high-risk confirmation and must be fully audited.

Future document import phases will support uploading invoices or other business documents, extracting structured fields, mapping them to an approved target DocType, showing validation warnings and a draft preview, and inserting only after explicit approval. The original file, extracted values, confidence and final document linkage must be recorded without exposing unrestricted content to the provider.

Future migration phases will support large-file uploads with streaming/chunked processing, permission-safe data cleansing, duplicate detection, field/type validation, dependency-aware related DocType creation, a dry-run summary and an import plan. The agent must show the proposed records, errors, skipped rows and relationships before execution, then request Codex-style explicit approval for the final migration. Approval must be scoped to the exact plan hash, target site, user, DocTypes and row set; any material change invalidates approval. Resume, rollback or compensation behavior and an audit trail are required before production use.

## UI refinement after Phase 8

The Copilot panel now keeps urgent findings in Alerts and shows only supporting information findings under Key Insights, avoiding duplicate warnings. Suggested Actions are derived from returned insight prompts with concise fallbacks. Conversation responses explicitly show when no answer was found, and completed streamed requests display a 100% Completed progress state.

The composer UI now uses icon controls, functional Enter/Shift+Enter behavior, response-level token estimates and a non-placeholder runtime label. Model selection remains server-controlled until a multi-model provider contract is added.

The composer also provides a Cancel control during an active request. Cancellation stops UI rendering of later realtime events and marks the conversation as cancelled; server-side request cancellation remains a future transport capability.

## Important product direction

Do not rely on browser-only heuristics for serious DocType, module, report, dashboard or record recognition.

The implemented architecture is:

1. Client detects the Desk route and sends only minimal sanitized hints.
2. Server resolves the context authoritatively using Frappe APIs and metadata.
3. Server enforces Frappe permissions before returning any context.
4. Server returns a canonical context object used for prompts, insights, cache keys and fingerprints.

## Context resolver expectations

Maintain a server-side resolver similar to:

```python
resolve_context(route, page_type_hint, route_params)
```

Expected behavior:

- Form: resolve `doctype` and `name`, verify read permission, then expose only safe permitted metadata/fields.
- List: resolve `doctype`, verify read permission, sanitize filters and visible list settings.
- Report: resolve report by name, verify report access and roles, sanitize filters, do not expose rows until permission-safe.
- Workspace: resolve workspace or module from Frappe records, verify access, expose safe shortcut/card identity.
- Dashboard: resolve dashboard name, verify access, expose safe chart/card identity.

## Hard boundaries

- Never send full HTML to the server or to any provider.
- Never send unrestricted document data.
- Do not call an LLM, RAG, analytics or action code before permission-safe context extraction and authorization.
- Frappe Role Permission and User Permission checks must be authoritative.
- Fingerprints should be based on canonical server-resolved context, not raw browser state.
- Provider prompts must use compact sanitized context and compact evidence, never raw documents or page HTML.
- Realtime token streaming must publish only request-scoped `stage`, `token`, `done` and `error` events for the authenticated user.
- If the streaming endpoint is not available on a deployed server, the UI must fall back without showing a Frappe server-error modal.

## Phase 3 permission boundary

All future context, knowledge, cache, analytics and provider code must call the reusable permission boundary in `reckon_copilot.permissions` before returning or using ERPNext-derived context.

Do not add ad-hoc permission checks directly in feature modules. If a new capability needs security behavior, extend `CopilotPermissionBoundary` and add tests there first.

The boundary is responsible for:

- rejecting Guest users
- enforcing native Frappe read permissions for DocType and document contexts
- enforcing report, workspace and dashboard access through Frappe APIs
- applying User Permission scope checks such as company scope
- redacting sensitive filters and non-context route details
- rejecting unsupported or write capabilities unless explicitly permitted
- proving Copilot cannot be used as a side channel for restricted ERPNext data

## Phase 4 knowledge boundary

Knowledge ingestion and retrieval must keep source, status, version, permission metadata and content hash information. Retrieval must return compact evidence objects with source attribution, not entire source documents. Unapproved, stale or permission-incompatible knowledge must not be returned to prompts.

## Phase 5 cache boundary

Cache keys must remain permission-safe. Never cache provider, RAG, analytics or future insight results without including the permission-scope hash and canonical context fingerprint. Cache misses and backend failures must not block normal ERPNext use.

## Phase 6 provider and streaming boundary

Provider configuration is stored in `Copilot Provider`. The local provider name is `local_llm`, but UI text should use generic LLM language. Do not restore old hard-coded provider/model assumptions.

The Frappe realtime streaming path uses:

- `reckon_copilot.api.ask.ask_stream`
- realtime event name `reckon_copilot_stream`
- request-scoped client generated `request_id`
- events `stage`, `token`, `done` and `error`

The browser should subscribe before calling `ask_stream`, and must unsubscribe when the request completes. The frontend must keep a silent fallback to the normal `ask` method for older deployments or workers that have not restarted yet.

## Phase 7 starting point

Phase 7 introduced an `insights` responsibility area for deterministic rules and findings before adding proactive notification behavior. Insights must continue to:

- call the permission boundary first
- operate from canonical context and permission-safe knowledge evidence
- avoid LLM calls when a deterministic rule can produce a finding
- return structured findings with severity, source, confidence and suggested next question/action
- be testable without ERPNext network access
- not perform write actions

The Phase 7 API is `reckon_copilot.api.insights.get_insights`. It authorizes with `analytics.run`, returns panel-safe findings, and converts permission denials into panel-friendly insight messages instead of Frappe server-error modals.

## Phase 8 notification boundary

Phase 8 notifications are derived from authorized Phase 7 findings. Notifications must:

- use `reckon_copilot.notifications` instead of duplicating insight or permission logic
- call the permission-bound insights service before emitting alerts
- return compact alert objects with level, source, source id, action label and action prompt
- never include full documents, raw report rows or unrestricted ERPNext data
- convert permission failures into panel-safe alerts
- respect the user `notifications_enabled` preference in the client
- not perform write actions or scheduled pushes until persistence/dismissal rules are implemented

The Phase 8 API is `reckon_copilot.api.notifications.get_notifications`.

## Phase 9 dashboard advisor update

Dashboard responses must describe the page a user is looking at, not internal
Copilot implementation metadata. The provider prompt omits boundary labels,
capability codes, enforcement versions and scope hashes. Dashboard routes now
receive a compact server-built snapshot containing:

- the dashboard title and active filters
- visible chart titles, source DocTypes, measures and small aggregate data points
- visible number-card titles, source DocTypes, functions and aggregate values
- a short dashboard summary used by the advisor and LLM prompt

The snapshot supports both legacy `Dashboard` records and Frappe v16
Workspace-backed `dashboard-view` routes. Linked chart and number-card reads
are permission-aware, and only compact aggregates are returned. The advisor
now generates dashboard-summary, metric-review and chart-explanation questions
from the actual visible components instead of generic route questions.

The dashboard snapshot is refreshed server-side for context, advisor and ask
requests, and its addition changes the canonical context fingerprint. Tests
cover prompt metadata suppression, visible dashboard component extraction,
Workspace fallback, linked-component permission filtering and dashboard-specific
advisor recommendations.

## Context-aware prompt contract

The advisor now treats the following as separate user-facing processes:

- **Homepage:** current site date, user/company briefing scope, precomputed insight prompts and next-area navigation.
- **Form:** DocType, document identity, current workflow/status signals, required and relevant fields, plus Link and child-table structure.
- **List:** DocType, active filters and available list signals such as search, sort and selected-row hints when supplied by Desk.
- **Report:** report identity, source DocType, current filters, company and date-range analysis prompts.
- **Dashboard:** dashboard identity, compact KPI/chart snapshot, active filters and aggregate-value explanations.
- **Workspace:** visible workspace navigation and a recommended next area based on the current date and page purpose.

Suggested prompts include an explicit site-date phrase such as `As of
YYYY-MM-DD`, a concrete analysis goal and a page-specific next action. The
provider receives `analysis_date` and the relevant compact snapshot, while
internal permission labels remain outside the user-facing prompt.

The Desk adapter uses `frappe.get_route()` as its route hint, but the server
continues to canonicalize and authorize the resulting context before advisor,
insight, knowledge or provider use.

## Workspace route canonicalization

Module workspace URLs such as `/desk/selling`, `/desk/stock` and
`/desk/subcontracting` must be represented as `Workspace` context. They are
not DocTypes, even when Desk exposes list-like markup while the workspace is
loading. Private URLs such as `/desk/private/reckon-copilot` are resolved from
their slug to the stored Workspace name before permission checks.

The client prefers workspace DOM signals and private route slugs, while the
server resolves the final name against Frappe Workspace records. A real
DocType route remains a `List` route when that DocType exists, including tree
DocTypes such as Customer Group and Item Group. This prevents false `DocType
... not found` errors and keeps invalid or restricted contexts inside the
Copilot permission boundary.
