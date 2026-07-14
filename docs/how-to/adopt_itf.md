# Adopting ITF for Your Project

This guide covers how to integrate ITF into an existing project, configure
your conftest for different test levels, and set up the DUT composition for
your specific target environments.

## Overview

ITF separates **what** your DUT is made of (contracts) from **when** things
happen (lifecycle). Your project configures:

1. **Which plugins to load** — target + capabilities for your hardware/environment
2. **Which aliases to expose** — project-level vocabulary for your test authors
3. **Which test levels to run** — unit, component, integration, system

---

## 1. Project structure

A typical project using ITF looks like this:

```
my_project/
├── MODULE.bazel          # ITF dependency
├── .bazelrc              # registry + options
├── conftest.py           # root conftest: plugins + aliases
├── tests/
│   ├── conftest.py       # test-level aliases (optional overrides)
│   ├── unit/             # no DUT needed — pure pytest
│   │   └── test_logic.py
│   ├── component/        # mock target — fast, no HW
│   │   ├── conftest.py
│   │   └── test_service.py
│   ├── integration/      # Docker target — CI-friendly
│   │   ├── conftest.py
│   │   └── test_deploy.py
│   └── system/           # QEMU or real HW — full stack
│       ├── conftest.py
│       └── test_e2e.py
└── BUILD
```

---

## 2. Root conftest — load ITF and register aliases

Your top-level `conftest.py` declares ITF as the engine and registers
project-wide aliases:

```python
# conftest.py
import pytest

# Load the ITF engine and generic fixtures
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.targets.fixtures",
]


@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    """Project vocabulary — tests use these names, never raw contracts."""
    dut.alias("shell", "itf/cap/exec")
    dut.alias("file_transfer", "itf/cap/file_transfer")
    dut.alias("restart", "itf/cap/restart")
    dut.alias("ssh", "itf/cap/ssh")
    dut.alias("ping", "itf/cap/ping")
    dut.alias("ip", "itf/net/ip_address")
    dut.alias("target", "ctf/target")
```

> **Tip**: Aliases are locked after the aliases phase — they cannot be modified
> from fixtures, tests, or sub-directory conftests.

---

## 3. Test levels via per-directory conftest

Each test level loads the appropriate target plugin and (optionally) adds
level-specific aliases or verification hooks.

### Unit tests — no ITF needed

Pure logic tests don't need a DUT. They run with plain pytest:

```python
# tests/unit/test_logic.py
def test_parse_config():
    from my_app import config
    assert config.parse("key=value") == {"key": "value"}
```

No conftest, no plugins, no ITF. Fast.

### Component tests — mock target

Use the mock target for testing service logic without real infrastructure:

```python
# tests/component/conftest.py
import pytest

pytest_plugins = [
    "score.itf.plugins.targets.mock.plugin",
]
```

```python
# tests/component/test_service.py
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("exec")
def test_service_responds(dut):
    shell = dut["shell"]
    exit_code, output = shell.execute("echo ok")
    assert exit_code == 0
```

The mock target provides `exec` and `file_transfer` with in-memory
implementations. No Docker, no network — millisecond tests.

### Integration tests — Docker target

Docker tests run real binaries in a container:

```python
# tests/integration/conftest.py
import pytest

pytest_plugins = [
    "score.itf.plugins.targets.docker.plugin",
    "score.itf.plugins.capabilities.ping.plugin",
]


@pytest.hookimpl
def pytest_itf_verify(dut, config):
    """Verify the container is responsive before running tests."""
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo ready")
    assert exit_code == 0, "Container not responsive"
```

```python
# tests/integration/test_deploy.py
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("exec", "file_transfer")
def test_deploy_config(dut, tmp_path):
    ft = dut["file_transfer"]
    shell = dut["shell"]

    config_file = tmp_path / "app.yaml"
    config_file.write_text("port: 8080\n")

    ft.upload(str(config_file), "/etc/app/app.yaml")
    exit_code, _ = shell.execute("test -f /etc/app/app.yaml")
    assert exit_code == 0
```

### System tests — QEMU or real hardware

System-level tests use a full VM or physical board:

```python
# tests/system/conftest.py
import pytest

pytest_plugins = [
    "score.itf.plugins.targets.qemu.plugin",
    "score.itf.plugins.capabilities.ssh.plugin",
    "score.itf.plugins.capabilities.ping.plugin",
]


@pytest.hookimpl
def pytest_itf_verify(dut, config):
    """Wait for the VM to boot and become SSH-reachable."""
    ping = dut["ping"]
    assert ping.ping(timeout=120), "Target did not become pingable"

    ssh = dut["ssh"]
    with ssh.ssh(timeout=10, n_retries=30, retry_interval=2) as conn:
        exit_code = conn.execute_command("echo ready")
        assert exit_code == 0
```

```python
# tests/system/test_e2e.py
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("exec", "ssh", "ping")
def test_full_boot_and_service(dut):
    shell = dut["shell"]
    exit_code, output = shell.execute("systemctl is-active my_service")
    assert exit_code == 0
    assert output.decode().strip() == "active"
```

---

## 4. Bazel BUILD configuration

Each test level maps to a `py_itf_test` target with different plugins:

```starlark
load("@score_itf//:defs.bzl", "py_itf_test")

# Component — fast, no Docker required
py_itf_test(
    name = "test_component",
    srcs = ["tests/component/test_service.py"],
    plugins = [
        "@score_itf//score/itf/plugins:mock_plugin",
    ],
)

# Integration — Docker, runs in CI
py_itf_test(
    name = "test_integration",
    srcs = ["tests/integration/test_deploy.py"],
    args = [
        "--docker-image=my-app:latest",
    ],
    plugins = [
        "@score_itf//score/itf/plugins:docker_plugin",
        "@score_itf//score/itf/plugins:ping_plugin",
    ],
)

# System — QEMU, manual or nightly CI
py_itf_test(
    name = "test_system",
    srcs = ["tests/system/test_e2e.py"],
    args = [
        "--qemu-config=$(location :qemu_config)",
        "--qemu-image=$(location :system_image)",
    ],
    data = [":qemu_config", ":system_image"],
    plugins = [
        "@score_itf//score/itf/plugins:qemu_plugin",
        "@score_itf//score/itf/plugins:ssh_plugin",
        "@score_itf//score/itf/plugins:ping_plugin",
    ],
    tags = ["manual"],  # don't run in CI by default
)
```

---

## 5. Capability gating — write portable tests

Use `@requires_capabilities` to declare what a test needs. If the current
target doesn't provide it, the test is **skipped** (not failed):

```python
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("exec")
def test_basic(dut):
    """Runs on any target with exec (mock, docker, qemu, hw)."""
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo ok")
    assert exit_code == 0

@requires_capabilities("ssh", "ping")
def test_network_service(dut):
    """Only runs on targets that provide SSH + ping (qemu, hw)."""
    ping = dut["ping"]
    assert ping.ping(timeout=5)
```

This means the **same test file** can be collected against different targets.
Capability gating auto-skips tests whose requirements aren't met.

---

## 6. Custom verify hooks — startup checks

Add project-specific health checks that run before any test. Just implement
the hook — ITF auto-times and auto-reports each one:

```python
# conftest.py
import pytest

@pytest.hookimpl
def pytest_itf_verify(dut, config):
    """Verify our application is running."""
    shell = dut["shell"]
    exit_code, output = shell.execute("curl -s http://localhost:8080/health")
    assert exit_code == 0, f"Health check failed: {output.decode()}"
```

**Failure semantics depend on the source:**

- **Conftest** verify hooks always abort the session (your project invariants)
- **Plugin** verify hooks respect the run mode:
  - `LOOSE` (default) — failure logs a warning and continues
  - `STRICT` — failure aborts the session

This means conftest checks are hard gates you control, while plugin
startup checks are advisory by default. To opt into strict plugin
verification, configure the run mode to `STRICT`.

---

## 7. Contract bindings — redirect plugin dependencies

When a generic plugin asks for a contract (e.g. `itf/net/ip_address`) but your
project's hardware topology requires it to use a *different* contract, use
**bindings** in the root conftest:

```python
# conftest.py
import pytest

@pytest.hookimpl
def pytest_itf_bindings(registry, config):
    """Redirect plugin dependencies to project-specific contracts."""
    # The UDP heartbeat plugin generically requires itf/net/ip_address,
    # but our target has multiple IPs — use the dedicated heartbeat interface
    registry.bind("itf/cap/udp_heartbeat",
                  "itf/net/ip_address",       # what the plugin asks for
                  "itf/net/heartbeat_ip")      # what it actually gets
```

**Key properties:**
- **Scoped**: only the named provider is redirected — other consumers of
  `itf/net/ip_address` (ping, SSH, etc.) are unaffected
- **Validated**: binding a nonexistent provider or requirement = hard error
- **Root conftest only**: sub-conftests cannot register bindings
- **Locked after phase**: no late mutation from fixtures or tests

This keeps plugins generic and reusable while letting the project wire them to
the correct resources for its specific hardware topology.

---

## 8. Domain-specific aliases

Aliases are registered **only in the root conftest** (or installed plugins).
Sub-directory conftests cannot add or override aliases. This prevents
per-directory drift and keeps the project vocabulary in one place:

```python
# conftest.py (root)
@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    dut.alias("shell", "itf/cap/exec")
    dut.alias("file_transfer", "itf/cap/file_transfer")
    dut.alias("diag", "itf/cap/diagnostics")
    dut.alias("flash", "itf/cap/flash")
```

```python
# tests/system/test_flash.py
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("itf/cap/flash")
def test_flash_update(dut):
    flash = dut["flash"]
    flash.update("/path/to/firmware.bin")
```

---

## 9. Fault injection and recovery

Tests can disable capabilities to verify graceful degradation:

```python
@requires_capabilities("exec", "file_transfer")
def test_degraded_mode(dut):
    """Verify the app works without file_transfer (falls back to inline)."""
    # Simulate loss of file_transfer
    dut.disable("file_transfer")

    shell = dut["shell"]
    exit_code, _ = shell.execute("my_app --check-degraded")
    assert exit_code == 0

    # Restore
    dut.enable("file_transfer")
```

For full target recovery after a crash:

```python
@requires_capabilities("exec", "restart")
def test_crash_recovery(dut):
    shell = dut["shell"]
    shell.execute("kill -9 $(pidof my_service)")

    # Restart and rebuild all handles
    restart = dut["restart"]
    restart.restart()
    dut.rebuild()

    # Verify recovery
    shell = dut["shell"]
    exit_code, _ = shell.execute("systemctl is-active my_service")
    assert exit_code == 0
```

---

## 10. Running locally (without Bazel)

For quick iteration, run tests directly with pytest:

```bash
# Integration tests against Docker
PYTHONPATH=. python -m pytest tests/integration/ \
    --docker-image=my-app:latest \
    -v

# Component tests with mock target
PYTHONPATH=. python -m pytest tests/component/ -v

# System tests (QEMU)
PYTHONPATH=. python -m pytest tests/system/ \
    --qemu-config=path/to/config.json \
    --qemu-image=path/to/system.img \
    -v
```

---

## 11. Multi-device setups (multi-SoC boards)

When your board has multiple SoCs, each device gets its own registry and
assembly. Contract strings are never modified — the same `"itf/cap/ssh"` lives
independently in each device scope. Shared facts cascade from root.

```python
# conftest.py — multi-SoC board
import pytest
from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf import Descriptor
from score.itf.plugins.capabilities.ssh.plugin import register_ssh
from score.itf.plugins.capabilities.ping.plugin import register_ping

pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.capabilities.ssh.plugin",   # auto-registers at root
    "score.itf.plugins.capabilities.ping.plugin",  # auto-registers at root
]


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    # Shared facts (visible to all devices via descriptor cascade)
    registry.add_descriptor(Descriptor("hw/device", {"name": "ecu-01", ...}))

    # Safety device — its own scope with its own providers + descriptors
    with registry.device("safety") as dev:
        @provides("ctf/target")
        @requires("hw/device")  # resolves from root
        def safety_anchor(device): ...

        dev.register(safety_anchor)
        dev.add_descriptor(Descriptor("itf/net/ip_address", "10.0.1.2"))
        dev.add_descriptor(Descriptor("itf/net/ssh_endpoint", {"host": "10.0.1.2", "port": 22}))

    register_ssh(registry, device="safety")
    register_ping(registry, device="safety")
```

**Test access:**

```python
def test_multi_soc(dut):
    # Root assembly — primary device (auto-registered plugins)
    ssh = dut.require("itf/cap/ssh")

    # Device-specific assembly
    safety_ssh = dut["safety"].require("itf/cap/ssh")

    # Availability per device
    assert dut["safety"].available("itf/cap/ping")

    # Independent rebuild
    dut["safety"].rebuild("ctf/target")  # only safety tears down
```

**Rules:**
- **Root assembly** = single-device or shared infra
- **`registry.device("name")`** = creates a child registry with its own assembly
- **Same contract strings** — no `@` tagging, no mangling
- **Descriptors cascade** from root → device (shared facts visible everywhere)
- **Providers are local** — register the same plugin in multiple scopes independently
- **`dut["device"]`** returns a `DeviceProxy` with its own `.require()`, `.rebuild()`, `.available()`

---

## 12. Inspecting providers at runtime

The DUT provides built-in introspection — use `dut.inspect()` and `dut.help()`
to auto-document what contracts are available, what they return, and what
methods the returned objects expose:

```python
def test_explore(dut):
    # Print help for all available contracts
    print(dut.help())

    # Inspect a single capability (before or after resolving)
    info = dut.inspect("itf/cap/ssh")
    print(info.return_type)       # e.g. "SshComponent"
    print(info.factory_name)      # e.g. "ssh_capability"
    print(info.requires)          # ("itf/net/ssh_endpoint",)

    # After resolving, methods are extracted from the live object
    dut.require("itf/cap/ssh")
    print(dut.help("itf/cap/ssh"))
    # Shows: .connect(timeout=15, n_retries=5, ...)
    #            Return an Ssh context manager pre-configured with endpoint details.

    # Works on device proxies too
    print(dut["safety"].help())
```

`inspect()` returns `ContractInfo` objects (or a list) with:
- `contract`, `kind` ("provider" or "descriptor"), `factory_name`
- `return_type` (from type annotation), `docstring`
- `requires` (dependency contracts)
- `public_methods` (list of `MethodInfo` with name, signature, docstring)
- `public_attributes`
- `is_materialized` (whether the resource is already resolved)

---

## 13. Summary — test level matrix

| Level       | Target   | Speed     | CI        | Capabilities            |
|-------------|----------|-----------|-----------|-------------------------|
| Unit        | None     | < 1s      | Always    | N/A (pure pytest)       |
| Component   | Mock     | < 5s      | Always    | exec, file_transfer     |
| Integration | Docker   | 10-30s    | Always    | exec, file_transfer, restart, ping |
| System      | QEMU/HW  | 1-5min    | Nightly   | All (ssh, ping, flash, diag, ...) |

The key insight: **tests don't change between levels**. The same
`dut["shell"]` call works on mock, Docker, or real silicon. What changes
is which plugin provides the contract — configured once in the conftest,
invisible to test authors.
