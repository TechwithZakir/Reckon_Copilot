# Reckon Copilot Tests

Phase 0 tests cover the installable package foundation, import contract, Frappe hook metadata, health endpoint payload, and fake provider implementation against the base provider interface.

Run without extra dependencies:

```powershell
python -m unittest discover -s reckon_copilot/tests -p "test_*.py"
```

In a Frappe v16+ bench, also verify:

```powershell
bench --site <site> install-app reckon_copilot
bench --site <site> migrate
bench --site <site> execute reckon_copilot.api.health.status
```

