# Reckon Copilot

Copyright: Reckon Technologies Ltd. Website: www.reckon.tech, email: hello@reckon.tech

Reckon Copilot is a native Frappe app targeting Frappe Framework v16+ and ERPNext v16+.

Implemented phases 0 through 19 include the Desk Copilot shell, route-aware
permission-scoped context, knowledge retrieval, caching, configurable LLM
providers with streaming, insights, alerts, the Contextual Agent Advisor,
Analytics, Forecasting and Anomalies agents, the Suggested Actions catalog and
feedback loop, safe document previews/imports, and user-confirmed ERP actions.

Write actions use a simple preview-first flow: the current user reviews the
target and values, clicks `Approve`, and the server rechecks native Frappe
permissions before applying the transaction. Every confirmed action is audited.
There is no separate Administrator approval queue or extra encryption-key
configuration for these actions.

The implementation is ready for staging release hardening and user acceptance.
See [docs/release-readiness.md](docs/release-readiness.md) for the deployment,
verification and rollback checklist.
