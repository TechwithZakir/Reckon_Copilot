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
