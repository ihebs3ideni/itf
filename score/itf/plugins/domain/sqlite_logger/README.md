# SQLite Logger Plugin

Persists test results, lifecycle events, and artifacts to a local SQLite
database for offline analysis, CI reporting, and historical tracking.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.domain.sqlite_logger.plugin",
]
```

## CLI Options

| Option | Default | Description |
|---|---|---|
| `--itf-sqlite` | off | Enable SQLite result logging |
| `--itf-sqlite-path` | `itf_results.db` | Path to the database file |

## Contracts

This plugin is a **domain observer** — it does not provide or require any
contracts. It hooks into the lifecycle to record events.

## Database Schema

| Table | Contents |
|---|---|
| `sessions` | Session metadata (start time, exit status, config) |
| `lifecycle_events` | Phase timeline (declare, init, provision, verify, teardown) |
| `test_results` | Per-test outcomes (nodeid, outcome, duration, stdout, stderr) |
| `artifacts` | Binary artifacts indexed by test nodeid |

## Lifecycle Hooks

Records timing for every phase: declare, init, provision, verify, teardown.
Also hooks into `pytest_runtest_logreport` for per-test outcomes.

## Storing Artifacts

```python
def test_capture(dut, itf_db):
    # ... run test ...
    screenshot = capture_screen()
    itf_db.store_artifact(
        name="failure_screenshot.png",
        data=screenshot,
        content_type="image/png",
        test_nodeid="tests/test_ui.py::test_capture",
    )
```

## Querying Results

```python
import sqlite3

conn = sqlite3.connect("itf_results.db")
cur = conn.execute("""
    SELECT nodeid, outcome, duration
    FROM test_results
    WHERE outcome = 'failed'
    ORDER BY duration DESC
""")
for row in cur:
    print(row)
```

## Example

```bash
pytest --itf-sqlite --itf-sqlite-path=results/run_001.db tests/
```
