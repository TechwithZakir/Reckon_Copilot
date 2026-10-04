# Reckon Copilot Architecture

Copyright: Reckon Technologies Ltd. Website: www.reckon.tech, email: hello@reckon.tech

## Phase 0 Scope

Reckon Copilot is a native Frappe app targeting Frappe v16+ and ERPNext v16+. Phase 0 establishes only the app foundation:

- installable Python package metadata
- Frappe hook metadata
- a small authenticated health/status endpoint
- a provider interface skeleton
- tests for imports, hooks, health, and a fake provider contract

Phase 0 does not implement Desk UI, RAG, LLM calls, analytics, caching, background jobs, autonomous actions, or modifications to Frappe or ERPNext core.

## Package Boundaries

The app package is `reckon_copilot`. Backend API modules live under `reckon_copilot.api`. Provider contracts live under `reckon_copilot.providers`.

## Phase 1 Desk Shell

The Desk shell is a Vue 3 component tree compiled by Frappe's native esbuild pipeline and included through `app_include_js` and `app_include_css`. It mounts alongside ERPNext Desk and does not replace Desk routing or layout.

Preferences are stored in `Copilot User Preference`. Browser requests never select a user: authenticated API methods bind reads and writes to `frappe.session.user`. Direct DocType access remains limited to System Manager.

The shell reads only the active route type in Phase 1. It does not read document fields or send page data to a provider.

Later phases should add new responsibilities behind these boundaries without sending unrestricted ERPNext data to provider implementations.

## Phase 4 Knowledge Engine

Phase 4 adds a knowledge-first retrieval engine for RAG. In Reckon Copilot, "learn" means ingesting approved content into a retrievable index: register, extract, normalize, chunk, index, approve and retrieve. It does not mean fine-tuning an LLM or modifying model weights.

Supported source types are `ERP_DATABASE`, `INTERNAL_DOCUMENT`, `WEB_URL`, `MANUAL_URL`, `PDF`, `DOCX` and `MANUAL_TEXT`. Knowledge is separated into Source, Document and Chunk records, each with status, version and content hash metadata. Only approved sources are returned by retrieval.

The baseline retriever uses deterministic keyword scoring and Frappe-compatible storage shapes. A provider-neutral `VectorStore` interface is also introduced with upsert, delete, similarity search, rebuild and health operations. The current implementation is native/in-memory for tests and local operation; a dedicated vector database can be added later behind the same interface without changing RAG callers.

Retrieved content is always treated as untrusted data. RAG orchestration returns compact evidence objects with source attribution instead of whole documents.

## Phase 5 Permission Safe Caching

Phase 5 adds cache primitives for expensive Copilot operations. Cache keys include site, capability, context fingerprint, permission-scope hash, question hash, provider/model and prompt/data versions. This prevents reuse across incompatible users, roles, companies or provider/prompt versions.

The cache manager is compatible with Frappe/Redis through a backend adapter and uses a deterministic in-memory backend for unit tests. Single-flight request deduplication ensures concurrent equivalent cache misses compute once when possible. Cache failures degrade to direct computation so ERPNext remains usable if Redis is unavailable.

## MCP reference alignment and post-Phase 19 roadmap

The next optional integration milestone is a first-party Model Context Protocol
(MCP) boundary for Reckon Copilot. MCP is an interoperability layer for
external agent clients and internal tool discovery; it is not a replacement for
Frappe APIs, the Copilot provider contract, the Desk shell or the existing
permission boundary.

### Reference repositories

The following public repositories are design references and must not become
runtime dependencies of this app:

- [`frappe/frappectl`](https://github.com/frappe/frappectl) is a reference for
  human- and agent-friendly Frappe REST v2 verbs, metadata discovery, compact
  JSON output, read-only profiles and caller-owned confirmation semantics.
- [`sanjay-kumar001/ai_chatbot`](https://github.com/sanjay-kumar001/ai_chatbot)
  is a reference for tool registries, permission-filtered tool schemas,
  relevant-tool routing, Frappe realtime progress, structured results,
  document extraction and feedback-oriented agent workflows.

Reckon Copilot must not import `ai_chatbot`, launch `frappectl` as a subprocess
for each request, copy an unrestricted CRUD tool set, or create a second
permission system. Patterns may be reimplemented behind native Copilot
services. Any reused MIT-licensed code must retain its license and attribution;
reimplementation is preferred when it keeps the boundary smaller.

### Native MCP boundary

The intended flow is:

```text
Copilot shell or external MCP client
        -> MCP adapter and bounded agent orchestrator
        -> native context/advisor/provider/cache/action services
        -> Frappe permission checks, realtime events and audit records
```

The in-app shell may call the shared native services directly for low latency.
An optional MCP server exposes the same services through standard MCP
resources, tools and prompts. It must never bypass the signed-in Frappe user,
the canonical context resolver or native DocType permissions.

Initial read-only resources and tools should be narrow and structured:

- current page context, DocType metadata and safe document summaries
- list/report/dashboard/workspace snapshots with bounded rows and aggregates
- approved knowledge search and page-specific advisor recommendations
- action and import previews, with no mutation in the preview operation

Write operations are separate from read tools. A write path remains
`preview -> explicit current-user confirmation -> permission recheck -> execute
-> audit`. `execute_approved_action` and `execute_approved_import` may be
exposed only after this native plan/approval contract is satisfied. There is no
Administrator approval queue, encryption-key configuration or automatic write
execution hidden behind MCP.

### Low-token and local-first policy

MCP must preserve the preliminary architecture priorities:

- Prefer deterministic context extraction, advisor rules, analytics and
  bounded reports before asking an LLM to synthesize an answer.
- Prefer the configured small local model for routine synthesis. A larger or
  remote model is an explicit provider choice, not a hidden fallback.
- Discover and expose only the tools relevant to the current page type,
  capability and user request. Do not send a full tool catalog on every turn.
- Keep tool arguments and results compact: field metadata instead of raw HTML,
  aggregates instead of complete charts, bounded rows instead of unrestricted
  documents, and evidence references instead of copied source documents.
- Cap tool rounds, detect repeated calls, cancel stale runs and return a
  readable partial result when a provider is unavailable.
- Reuse the existing permission-safe cache identity. MCP cache keys must include
  site, user/permission scope, canonical context fingerprint, capability,
  question or arguments, provider/model and prompt/data versions. Never share
  sensitive results across users or cache a mutation as a read result.
- Use single-flight deduplication and versioned invalidation on document,
  provider, prompt, knowledge-index or permission-scope changes. Cache failure
  must degrade to direct computation.

Token streaming remains a UI/provider concern delivered through the existing
Frappe realtime progress events. MCP tool results should be structured and
auditable; an MCP transport must not require a second streaming protocol.

### Continuous enhancement policy

Feedback may be aggregated by context, prompt, tool, model and outcome. The
system may generate candidate prompt/catalog improvements and validate them
against installed fields, current permissions and the contract tests. A
versioned candidate still requires administrator review before publication and
supports rollback. This is controlled catalog improvement, not automatic model
training, weight updates or unapproved prompt deployment.

### MCP development phases

These phases are intentionally additive and begin after the completed product
plan (Phases 0–19):

1. **MCP-A contract and inventory**: define the capability matrix, resource,
   tool and prompt schemas; map each operation to existing native services;
   publish a read-only contract and reference-only dependency decision.
2. **MCP-B bounded read server**: implement the first-party registry and
   context/metadata/list/report/dashboard/knowledge resources and tools with
   native permission checks, compact schemas, structured errors and contract
   tests.
3. **MCP-C local agent bridge**: connect the Copilot orchestrator to the MCP
   registry, dynamically filter relevant tools, cap rounds, preserve progress
   stages and keep deterministic/local-small-LLM fallback behavior.
4. **MCP-D cache and reuse**: cache permission-safe resource/tool results with
   single-flight, scope isolation, versioning and invalidation; measure token
   and latency reduction without changing answer correctness.
5. **MCP-E contextual prompts**: expose page-specific prompts and advisor
   recommendations for Form, List, Report, Dashboard, Workspace and Homepage
   contexts, using current date, company scope and compact page signals.
6. **MCP-F confirmed actions and imports**: expose only preview and
   execute-after-confirmation operations for Create, Update, Delete, Submit and
   import workflows. Reuse native Frappe permissions, plan hashes,
   idempotency and `Copilot Action Audit` records.
7. **MCP-G external interoperability**: optionally add a Streamable HTTP MCP
   endpoint for trusted clients. Keep stdio/Inspector support for development;
   treat legacy SSE as compatibility only. Add authentication/session mapping,
   host allowlists, quotas and per-tool exposure controls before external use.
8. **MCP-H governed continuous enhancement**: aggregate feedback, generate and
   validate candidate prompt/catalog changes, require administrator approval,
   publish versioned snapshots and support rollback. Do not auto-train models.
9. **MCP-I release verification**: test with MCP Inspector and a real client,
   restricted Frappe users, missing DocTypes, empty results, cache isolation,
   stale approvals, cancellation, realtime fallback and load limits before
   enabling the endpoint in production.
