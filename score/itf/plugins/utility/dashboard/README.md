# Dashboard Plugin

Live web UI showing the composition graph, lifecycle phases, startup checks,
and test progress. Generates offline HTML snapshots on completion or crash.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.utility.dashboard.plugin",
]
```

## CLI Options

| Option | Default | Description |
|---|---|---|
| `--itf-dashboard` | off | Enable the dashboard |
| `--itf-dashboard-port` | `8099` | Port to serve the live UI on |
| `--itf-dashboard-snapshot` | none | Path for HTML snapshot on completion/crash |

## Contracts

This plugin is a **utility observer** — it does not provide or require any
contracts. It reads composition state from the DUT and registry.

## Features

- **Live graph** — visualizes contract dependency edges and tiers
- **Phase timeline** — shows which lifecycle phases have completed
- **Startup checks** — verify phase results with pass/fail and duration
- **Test progress** — collected, passed, failed, skipped counters
- **Materialized resources** — which contracts are currently live
- **Crash snapshot** — if the session crashes, dumps the last known state

## HTTP API

| Endpoint | Description |
|---|---|
| `GET /` | Live HTML dashboard (auto-refreshes every 1s) |
| `GET /api/state` | JSON snapshot of current state |

## Offline Snapshots

When `--itf-dashboard-snapshot` is set, the plugin dumps a self-contained HTML
file at session end. This is useful for CI artifacts:

```bash
pytest --itf-dashboard \
       --itf-dashboard-snapshot=report/dashboard.html \
       tests/
```

The snapshot is static (no polling) and can be opened in any browser.

## Example

```bash
pytest --itf-dashboard --itf-dashboard-port=9000 tests/
# Open http://localhost:9000 in your browser
```
