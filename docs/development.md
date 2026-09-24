# Reckon Copilot Development

Copyright: Reckon Technologies Ltd. Website: www.reckon.tech, email: hello@reckon.tech

## Target Platform

- Frappe Framework v16+
- ERPNext v16+
- Python 3.11+

## Phase 0 Verification

Run dependency-free unit tests:

```powershell
python -m unittest discover -s reckon_copilot/tests -p "test_*.py"
```

From a Frappe v16+ bench that includes ERPNext, verify install and migrate:

```powershell
bench get-app reckon_copilot <path-or-repository-url>
bench --site <site> install-app reckon_copilot
bench --site <site> migrate
bench --site <site> execute reckon_copilot.api.health.status
```

The health endpoint is available as:

```text
/api/method/reckon_copilot.api.health.status
```

No real AI provider is configured or called in Phase 0. Use a fake provider in tests to validate the provider interface only.

## Phase 1 Verification

Run frontend state tests:

```powershell
node --test reckon_copilot/public/js/copilot/shell_state.test.mjs
```

From the bench, install declared frontend dependencies, build assets and migrate:

```powershell
cd apps/reckon_copilot
yarn install --frozen-lockfile
cd ../..
bench build --app reckon_copilot
bench --site <site> migrate
bench --site <site> run-tests --app reckon_copilot
```

Verify the shell on a Desk Form, List, Report and Workspace. Confirm open, close, minimize, keyboard focus, responsive layout and persisted sound settings.

## Phase 4 Verification

Run the backend and frontend checks:

```powershell
python -m unittest discover reckon_copilot\tests
python -m compileall -q reckon_copilot
node --test reckon_copilot/public/js/copilot/*.test.mjs
node scripts/validate_vue.mjs
```

From a Frappe bench, run `bench --site <site> migrate` after pulling Phase 4 so the Knowledge Source, Document, Chunk, Ingestion Job and Vector Index DocTypes are installed.

Manual verification should cover creating manual knowledge, submitting a URL, processing PDF/DOCX content, approving a source, searching for compact evidence, confirming source attribution and confirming unapproved or permission-incompatible knowledge is excluded.

## Phase 5 Verification

Run the standard checks plus cache tests:

```powershell
python -m unittest discover reckon_copilot\tests
python -m compileall -q reckon_copilot
node --test reckon_copilot/public/js/copilot/*.test.mjs
node scripts/validate_vue.mjs
```

Manual verification on a Frappe bench should confirm Redis-backed cache access works, cache misses do not break normal requests when Redis is unavailable, and repeated equivalent RAG retrievals reuse cached evidence only within the same permission scope.

## Phase 10 Verification

Run the standard checks plus Analytics Agent coverage:

```powershell
python -m unittest discover -s reckon_copilot\tests -p "test_*.py"
python -m compileall -q reckon_copilot
node --test reckon_copilot/public/js/copilot/*.test.mjs
node scripts/validate_vue.mjs
```

On a Frappe bench, migrate before testing. Open a permitted List or Dashboard,
choose `Analytics` in the conversation mode switch, and try a summary, a
breakdown such as "show sales by customer", and a trend question. Verify the
response contains a plain-language narrative, bounded metrics/table output
and chart-ready visualization. Repeat as a restricted user and confirm the
result stays inside Copilot without exposing data or showing a Frappe error.
Switch back to `Copilot` and verify ordinary questions still use the normal
provider path. Ask a dashboard or homepage question that returns a structured
briefing and verify the conversation shows a readable title, summary and
sections rather than a raw object dump. Do not test against production records
until a staging backup and rollback procedure are available.

If migration reports a missing `copilot_action_audit` module, confirm the app
contains both `copilot_action_audit.py` and `__init__.py` beside the DocType
JSON, then restart the bench processes before retrying migration.

## Phase 11 Verification

Phase 11 adds a separate read-only Forecasting Agent. Run the complete checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s reckon_copilot\tests -p "test_*.py"
.\.venv\Scripts\python.exe -m compileall -q reckon_copilot
node --test reckon_copilot/public/js/copilot/*.test.mjs
node scripts/validate_vue.mjs
```

On a staging Frappe bench, migrate and open a permitted List with at least
three dated numeric observations. In the Copilot conversation select `Forecast`
and ask for the outlook. Confirm that the response shows a readable narrative,
forecast periods, a compact chart and `Forecasting Agent` metadata. Select
`Anomalies` and ask for unusual values; confirm that outliers show their period,
observed value, expected value and priority. Open a permitted Dashboard with a
visible time-series chart and confirm that its compact chart snapshot can be
forecast without exposing raw dashboard rows.

Verify that a page with fewer than three usable time points returns a helpful
"at least 3 are needed" message, not a server error. Repeat as a restricted
user and confirm the result remains inside the Copilot panel. Inspect the usage
log for capability `forecasting.run`. The result must remain deterministic and
read-only: no ERP record is created, changed, submitted, approved or deleted,
no action preview is opened, and no model-training or prompt-learning record is
created. Do not test against production records until a staging backup and
rollback procedure are available.

## Phase 12 Verification

Phase 12 is the approval-gated write path. On staging, open an existing Form
as a System Manager and select a write-preview suggestion. Confirm that the
panel shows the target DocType, record, action, risk and plan hash. Confirm that
closing the dialog or cancelling does not change the record.

Approve the plan and verify that the UI changes to `ready_to_execute`; approval
alone must not mutate data. Select `Execute approved action` only after checking
the preview, then confirm the expected native Frappe result and a completed
`Copilot Action Audit` record. Repeat the same execution request and confirm it
returns an idempotent result without applying the change twice.

Test an unauthorized user, a changed plan, an expired token, an unknown field,
and a protected field. Each must remain inside the Copilot panel with a useful
message and must not show a Frappe server-error modal. Test submit/delete/approve
as high-risk operations and verify that each still requires the same explicit
approval plus final execution click. Do not use production records until backup,
rollback and audit review procedures are approved.

## Suggested Actions Catalog Verification

The catalog is complete before Phase 11 and remains read-only. Run the advisor
tests and verify representative pages:

```powershell
python -m unittest reckon_copilot.tests.test_advisor
```

Open a permitted Purchase Order, Sales Order, Sales Invoice, Item, Work Order,
CRM Lead, POS Profile, Employee or Leave Application List/Form. Confirm that
Suggested Actions and Quick Questions use the current DocType, show a reason,
priority, source and action type, and that unrelated or field-incomplete
DocTypes do not receive catalog suggestions. Confirm every catalog suggestion
only starts a Copilot read-only prompt; it must not create, update, submit,
approve or delete an ERP record.

## Controlled Advisor Learning Verification

The catalog improvement loop is deliberately administrator-controlled. The
browser records only aggregate suggestion outcomes and never stores raw page
HTML, document values, document names or user identity in feedback records.

After migration, verify the new administrator-only workspace links:

- `Copilot Suggestion Feedback` contains aggregate counts only.
- `Copilot Catalog Candidate` contains pending candidates after repeated
  `not relevant` or `too generic` feedback.
- Candidate validation reports the installed-field and native-read-permission
  result before approval is possible.
- A System Manager can approve a `VALID` candidate, creating an enabled,
  versioned `Copilot Suggested Action Template`.
- A non-administrator cannot publish a candidate, and an approved template
  remains read-only guidance that only starts a prompt.
- Publishing creates a `Copilot Catalog Snapshot`; only its template manifest
  is active at runtime. The Candidate list provides `Generate Candidates`, a
  retired Snapshot form provides `Activate This Snapshot`, and rollback creates
  a new published snapshot while preserving the previous history.

The scheduled job is safe to run repeatedly: candidate generation is
idempotent, and it never publishes templates or executes ERPNext writes.
The endpoints are:

```text
/api/method/reckon_copilot.api.catalog_learning.record_suggestion_feedback
/api/method/reckon_copilot.api.catalog_learning.generate_catalog_candidates
/api/method/reckon_copilot.api.catalog_learning.approve_catalog_candidate
```

Run the automated checks before and after migration:

```powershell
python -m unittest discover -s reckon_copilot/tests -p "test_*.py"
python -m compileall -q reckon_copilot
node --test reckon_copilot/public/js/copilot/*.test.mjs
node scripts/validate_vue.mjs
```
