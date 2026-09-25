# Reckon Copilot Release Readiness

This checklist is the next milestone after the completion of Phases 0 through
19. Run it on staging before production. Do not use production records for
write-action testing.

## 1. Local verification

From the repository root:

```powershell
python -m unittest discover -s reckon_copilot\tests -p "test_*.py"
python -m compileall -q reckon_copilot
node --test reckon_copilot/public/js/copilot/*.test.mjs
node scripts/validate_vue.mjs
git diff --check
```

The release gate is all tests passing, Vue compilation passing and no diff
errors.

## 2. Staging deployment

Create a site backup before migration. From the Frappe bench, after the app
commit is available:

```text
bench --site <site> backup --with-files
bench --site <site> migrate
bench build --app reckon_copilot
bench restart
bench --site <site> clear-cache
bench --site <site> execute reckon_copilot.api.health.status
```

Confirm the health response is successful, the installed app version is
`reckon_copilot`, and all workers have restarted after the migration. Check
the browser uses the rebuilt Desk assets rather than a stale bundle.

## 3. Administrator configuration

In `Copilot Provider`, verify:

- the provider is enabled and its Base URL is reachable from the bench
- `Model` is set to an installed model
- `Allowed Models` contains only models the site may use
- `Stream Response` matches the provider capability
- timeout and retry values are appropriate for the staging provider

Then open the Copilot panel and confirm the model selector contains only the
server-provided allowlist. Selecting a model must change the server-side
provider request and usage-log metadata.

## 4. User acceptance matrix

Test as Administrator and as a restricted business user.

| Context | Verify |
| --- | --- |
| Homepage | Current-date briefing, relevant actions and readable response |
| Workspace/Desktop | Workspace-specific suggestions and navigation targets |
| List | Current DocType, filters, search/sort and selected rows are reflected |
| Form | Current document, status, fields and related records are reflected |
| Report | Report name, filters, date range and bounded results are reflected |
| Dashboard | KPI/chart summary uses compact metrics, not raw page HTML |

For each context, confirm unrelated DocTypes do not appear, restricted data is
not exposed, empty results say that nothing was found, and completed responses
show `Completed` progress rather than an unfinished loader.

## 5. Agent checks

- Copilot: ask a normal page-specific question and verify readable formatting.
- Analytics: run summary, breakdown and trend questions.
- Forecast: use at least three dated numeric observations.
- Anomalies: include one deliberately unusual value and verify the reason.
- Suggested Actions: verify reason, priority, source and action type.
- Cancel: start a request and cancel it; no stale response may appear later.
- Streaming: verify progress and token updates, then retry after a timeout.

All read-only agents must report `writes: false` and `model_training: false`.

## 6. Write-action checks

On a staging copy of a permitted Form:

1. Start Create, Update, Delete, Submit or Approve from a Suggested Action.
2. Review the target, values, risk and plan hash in the preview.
3. Cancel and confirm the ERP record is unchanged.
4. Reopen the preview and click `Approve` once.
5. Confirm the native Frappe transaction completes and the audit row records
   the confirming user, plan hash, result and final status.
6. Repeat the same request and confirm it is idempotent.

Repeat as a user without the required native permission. The panel should show
a useful access message and no Frappe error modal. Test an unknown field,
protected field and changed plan; each must be rejected without a mutation.
There is no separate Administrator approval queue or final Execute step.

## 7. Document import checks

Test a small CSV/TSV/JSON import and a text-based PDF/DOCX preview. Confirm
mapping and extracted values are visible before confirmation, canceling makes
no change, the current user's native create permission is rechecked, and the
completed import is audited. Test malformed, empty, oversized and unsupported
files for panel-safe messages.

## 8. Rollback and exit criteria

Keep the pre-migration backup and the previous app commit available. If a
staging migration or smoke test fails, stop the rollout, capture the worker and
browser errors, restore only through the approved site rollback procedure, and
rerun the local suite before retrying.

Release is ready only when migrations, assets, health, permissions, agent
responses, write confirmations, audit logs and rollback rehearsal all pass for
both Administrator and restricted-user paths.
