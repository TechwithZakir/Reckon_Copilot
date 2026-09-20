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
