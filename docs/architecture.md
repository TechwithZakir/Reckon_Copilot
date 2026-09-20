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

Later phases should add new responsibilities behind these boundaries without sending unrestricted ERPNext data to provider implementations.

