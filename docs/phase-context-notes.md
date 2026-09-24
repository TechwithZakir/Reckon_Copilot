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

## UI refinement after Phase 8

The Copilot panel now keeps urgent findings in Alerts and shows only supporting information findings under Key Insights, avoiding duplicate warnings. Suggested Actions are derived from returned insight prompts with concise fallbacks. Conversation responses explicitly show when no answer was found, and completed streamed requests display a 100% Completed progress state.

The composer UI now uses icon controls, functional Enter/Shift+Enter behavior, response-level token estimates and a non-placeholder runtime label. Model selection remains server-controlled until a multi-model provider contract is added.

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
