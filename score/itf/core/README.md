# ITF Plugin — Lifecycle Engine

The ITF plugin integrates the CTF composition engine with pytest. It owns the
phased lifecycle, exposes the `dut` fixture, and auto-reports startup checks.

## Loading

```python
# conftest.py
pytest_plugins = ["score.itf.core.itf_plugin"]
```

## Lifecycle Phases

The plugin drives eight phases in order:

1. **DECLARE** — plugins register providers/descriptors into the registry
2. **BIND** — conftest redirects plugin requirements via `registry.bind()`
3. **ALIASES** — conftest registers domain vocabulary on the DUT
4. **INIT** — target bring-up (assembly realizes the graph)
5. **PROVISION** — deploy artifacts, seed databases
6. **VERIFY** — health checks (conftest = always abort; plugin = respects run mode)
7. **TESTS** — pytest collects and runs user tests
8. **TEARDOWN** — reverse instantiation order, automatic

## The `dut` Fixture

Every test receives a composed DUT:

```python
def test_service(dut):
    shell = dut["shell"]              # alias
    code, _ = shell.execute("echo ok")
    assert code == 0
```

## Verify Phase Semantics

- **Conftest** verify hooks always abort the session on failure (your invariants).
- **Plugin** verify hooks respect the run mode:
  - `LOOSE` (default) — failure logs a warning, session continues.
  - `STRICT` — failure aborts the session.

## Startup Check Reporting

Plugins can report named checks:

```python
from score.itf.core.itf_plugin import report_startup_check

report_startup_check(config, name="my_check", status="pass", duration=0.3)
```

Utility plugins (dashboard, logger) consume these via `get_startup_checks(config)`.

## Public API

| Function / Class | Purpose |
|---|---|
| `dut` fixture | Composed DUT for tests |
| `itf_kernel` fixture | Access to registry, assembly, DUT |
| `get_dut(config)` | Programmatic DUT access from hooks |
| `get_startup_checks(config)` | Retrieve verify phase results |
| `report_startup_check(config, ...)` | Report a named startup check |
