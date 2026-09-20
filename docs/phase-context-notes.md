# Reckon Copilot Phase Context Notes

## Current status

Phase 1 is complete as a Desk shell and overlay UI.

Phase 2 is implemented as route synchronization, sanitized context shape and deterministic fingerprinting. The current frontend can identify page type and display a visible context label, but route and DOM heuristics are not sufficient as the long-term foundation for Copilot intelligence.

## Important product direction

Do not rely on browser-only heuristics for serious DocType, module, report, dashboard or record recognition.

The better architecture for Phase 3 is:

1. Client detects the Desk route and sends only minimal sanitized hints.
2. Server resolves the context authoritatively using Frappe APIs and metadata.
3. Server enforces Frappe permissions before returning any context.
4. Server returns a canonical context object used for prompts, insights, cache keys and fingerprints.

## Phase 3 target resolver

Add a server-side resolver similar to:

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
- Do not call an LLM or add RAG until permission-safe context extraction is complete.
- Frappe Role Permission and User Permission checks must be authoritative.
- Fingerprints should be based on canonical server-resolved context, not raw browser state.

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
