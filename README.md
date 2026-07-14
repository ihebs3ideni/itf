<!--
*******************************************************************************
Copyright (c) 2025 Contributors to the Eclipse Foundation
See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.
This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0
SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->
# Integration Test Framework (ITF)

ITF is a [`pytest`](https://docs.pytest.org/en/latest/contents.html)-based testing framework built on a **Composable Target Framework (CTF)** — a contract-based dependency-injection engine for ECU and embedded testing. Tests declare *what* they need as contract strings; the framework assembles the environment deterministically for any target.

## Key Features

- **Contract-Based Composition**: Tests and plugins couple through string contracts — no shared imports
- **Phased Lifecycle**: declare → bind → aliases → init → provision → verify → tests → teardown
- **Target-Blind Tests**: Write once, run on Docker, QEMU, mock, or real hardware
- **Fail-Fast**: Composition errors surface at session start, not mid-test
- **Aliases**: Project-level vocabulary — tests say `dut["shell"]` not `dut.require("itf/cap/exec")`
- **Bindings**: Redirect a plugin's dependency to a different contract without modifying the plugin
- **Governance**: Optional namespace/alias integrity validation (off / warn / strict)
- **Bazel Integration**: Seamless via `py_itf_test` macro

## Quick Start

### Installation

Add ITF to your `MODULE.bazel`:
```starlark
bazel_dep(name = "score_itf", version = "0.1.0")
```

Configure your `.bazelrc`:
```
common --registry=https://raw.githubusercontent.com/eclipse-score/bazel_registry/main/
common --registry=https://bcr.bazel.build
```

### Root conftest — load ITF and configure

```python
# conftest.py
import pytest

pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.targets.docker.plugin",
    "score.itf.plugins.capabilities.ping.plugin",
    "score.itf.plugins.utility.logger.plugin",
]


@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    """Project vocabulary — tests use these short names."""
    dut.alias("shell", "itf/cap/exec")
    dut.alias("file_transfer", "itf/cap/file_transfer")
    dut.alias("restart", "itf/cap/restart")
    dut.alias("ping", "itf/cap/ping")
    dut.alias("ip", "itf/net/ip_address")
    dut.alias("target", "ctf/target")


@pytest.hookimpl
def pytest_itf_bindings(registry, config):
    """Redirect plugin requirements for this project's topology."""
    # Example: UDP heartbeat uses a dedicated interface
    # registry.bind("itf/cap/udp_heartbeat",
    #               "itf/net/ip_address", "itf/net/heartbeat_ip")
```

### Basic Test

```python
# test_example.py
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("exec")
def test_deploy(dut):
    shell = dut["shell"]
    exit_code, output = shell.execute("echo 'Hello from target!'")
    assert exit_code == 0
```

### BUILD Configuration

```starlark
load("@score_itf//:defs.bzl", "py_itf_test")

py_itf_test(
    name = "test_example",
    srcs = ["test_example.py"],
    args = ["--docker-image=ubuntu:24.04"],
    plugins = ["@score_itf//score/itf/plugins:docker_plugin"],
)
```

## Architecture At A Glance

The framework is layered: **target plugins** produce hardware/container handles, **capability plugins** transform those into test-facing interfaces, and **tests** consume capabilities through the DUT. Each layer couples only through contract strings.

### 1. Target Plugin (provides the anchor)

A target plugin owns the lifecycle of the actual target — Docker container, QEMU VM, or real hardware. It publishes `ctf/target` and any network facts:

```python
# score/itf/plugins/targets/my_target/plugin.py
from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.target import TARGET_ANCHOR

@provides(TARGET_ANCHOR)  # "ctf/target"
@requires("itf/target/image", "itf/target/config")
def my_target_anchor(image, config):
    """Start the target and return a handle. Teardown on generator close."""
    handle = start_target(image, config)
    yield handle          # tests run while yielded
    handle.shutdown()     # teardown (reverse order)


def pytest_itf_declare(registry, config):
    """Phase: DECLARE — register target descriptors and anchor provider."""
    registry.add_descriptor(Descriptor("itf/target/image", config.getoption("--image")))
    registry.add_descriptor(Descriptor("itf/target/config", {"network": "bridge"}))
    registry.add_descriptor(Descriptor("itf/net/ip_address", "10.0.0.2"))
    registry.add_descriptor(Descriptor("itf/net/ssh_endpoint", {
        "host": "10.0.0.2", "port": 22, "username": "root",
    }))
    registry.register(my_target_anchor)
```

### 2. Capability Plugins (transform target facts into interfaces)

A capability plugin requires target facts and provides a test-facing interface. It knows nothing about *which* target — only the contract it needs:

```python
# score/itf/plugins/capabilities/exec/plugin.py
from score.itf.core.ctf.contracts import provides, requires

@provides("itf/cap/exec")
@requires("ctf/target")
def exec_capability(target):
    """Wrap the raw target handle into an exec interface."""
    return ExecInterface(target)


class ExecInterface:
    """What tests see — execute commands, get (exit_code, output)."""

    def __init__(self, target):
        self._target = target

    def execute(self, command: str) -> tuple[int, str]:
        return self._target.run(command)

    def execute_async(self, binary, args=None):
        return self._target.start_process(binary, args)
```

Another capability — same pattern, different contract:

```python
# score/itf/plugins/capabilities/file_transfer/plugin.py
from score.itf.core.ctf.contracts import provides, requires

@provides("itf/cap/file_transfer")
@requires("ctf/target")
def file_transfer_capability(target):
    """Wrap the target handle into a file transfer interface."""
    return FileTransferInterface(target)


class FileTransferInterface:
    """What tests see — push/pull files to/from target."""

    def __init__(self, target):
        self._target = target

    def upload(self, local_path: str, remote_path: str) -> None:
        self._target.copy_to(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        self._target.copy_from(remote_path, local_path)
```

Each capability is its own plugin — loaded independently, coupled only through contracts.

### 3. Root Conftest (wires plugins together)

The conftest is the only place that knows which *specific* plugins to load. Tests never import plugins directly:

```python
# conftest.py
import pytest

pytest_plugins = [
    "score.itf.core.itf_plugin",                        # CTF engine
    "score.itf.plugins.targets.docker.plugin",          # target: Docker
    "score.itf.plugins.capabilities.ssh.plugin",        # cap: SSH
    "score.itf.plugins.capabilities.ping.plugin",       # cap: ping
    "score.itf.plugins.utility.logger.plugin",          # observability
]

@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    dut.alias("shell", "itf/cap/exec")
    dut.alias("files", "itf/cap/file_transfer")
    dut.alias("target", "ctf/target")
```

### 4. The Test (target-blind)

Tests only know aliases and contract interfaces. Swap the target plugin in conftest and the same test runs on Docker, QEMU, or silicon:

```python
# test_deployment.py
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("exec", "file_transfer")
def test_deploy_and_verify(dut):
    files = dut["files"]
    files.upload("/tmp/app.bin", "/opt/app.bin")

    shell = dut["shell"]
    code, out = shell.execute("/opt/app.bin --self-test")
    assert code == 0, f"Self-test failed: {out}"

def test_network_reachable(dut):
    assert dut.available("itf/cap/ping")
    ping = dut.require("itf/cap/ping")
    assert ping.check()
```

### What flows where

```
┌─────────────────────────────────────────────────────────────┐
│                        conftest.py                           │
│  loads: target plugin + capability plugins + aliases        │
└──────────────────────────────┬──────────────────────────────┘
                               │ pytest_itf_declare
              ┌────────────────▼────────────────┐
              │         CTF Registry            │
              │  descriptors: ip, ssh_endpoint  │
              │  providers:   target → exec     │
              └────────────────┬────────────────┘
                               │ resolve
              ┌────────────────▼────────────────┐
              │           DUT                    │
              │  dut["shell"] → ExecInterface   │
              │  dut["files"] → FileTransfer    │
              └────────────────┬────────────────┘
                               │ inject
              ┌────────────────▼────────────────┐
              │           Test                   │
              │  code, out = shell.execute(...)  │
              └─────────────────────────────────┘
```

---

## Architecture

### Two Planes, One Seam

| Layer | Responsibility | Pytest-free? |
|-------|----------------|--------------|
| **CTF** (engine) | Registry → Resolver → Assembly → DUT | Yes |
| **ITF** (plugin) | Phased lifecycle hooks on pytest | No |

They meet at one line: `dut.require("contract")` — a lifecycle hook asks the DUT for a resolved capability by contract string.

### Contracts

A contract is a string — identity, not shape. Plugins agree on names the way web services agree on URLs:

| Prefix | Meaning |
|--------|---------|
| `ctf/target` | Engine anchor — only one per run |
| `itf/cap/*` | Capabilities (exec, file_transfer, ssh, restart, ping) |
| `itf/net/*` | Network facts (ip_address, ssh_endpoint) |
| `itf/target/*` | Target-specific descriptors (image, config) |
| `itf/env/*` | Environment controllers (heartbeat, faults) |

### Providers & Descriptors

```python
from score.itf.core.ctf.contracts import provides, requires

@provides("itf/cap/exec")
@requires("ctf/target")
def docker_exec(target):
    return DockerExecClient(target)
```

- **Provider**: a factory that `@provides` one contract and `@requires` others
- **Descriptor**: a static fact (config value, IP address, image path)
- **SSOT**: exactly one provider per contract. Two = hard error.
- **Tiers**: derived from the graph, never declared

### Lifecycle Phases

```
declare → bind → aliases → init → provision → verify → tests → teardown
```

Plugins implement only the hooks they need:

```python
@pytest.hookimpl
def pytest_itf_declare(registry, config):
    """Register providers/descriptors."""

@pytest.hookimpl
def pytest_itf_verify(dut, config):
    """Health check — just raise on failure. ITF auto-times and reports."""
    shell = dut["shell"]
    code, _ = shell.execute("echo ok")
    assert code == 0
```

### Aliases

Short project-level names that map to contract strings. Registered in the root conftest only, locked after the aliases phase:

```python
dut.alias("shell", "itf/cap/exec")
# Tests use: dut["shell"]
```

### Bindings

Per-provider requirement redirects. A generic plugin asks for `itf/net/ip_address`; the conftest redirects it to a project-specific contract:

```python
registry.bind("itf/cap/udp_heartbeat",    # the consumer
              "itf/net/ip_address",         # what it asks for
              "itf/net/heartbeat_ip")       # what it gets
```

Other consumers of `itf/net/ip_address` are unaffected — bindings are scoped.

### Governance

Optional contract/alias integrity enforcement via the governance plugin:

```ini
# pytest.ini
itf_governance = strict  # off | warn | strict
```

Validates namespace conventions, alias targets, and composition integrity at session start.

### Typed Contracts (Optional Governance Layer)

String contracts maximize decoupling but sacrifice discoverability. The solution: a **dependency-free vocabulary module** that lives alongside the contracts — not inside any plugin.

```python
# contracts.py — zero deps, just typing.Protocol + string constants
from typing import Protocol, runtime_checkable

EXEC = "automation/exec"
FILE_TRANSFER = "automation/file_transfer"
NETWORK_INFO = "automation/network_info"

@runtime_checkable
class ExecCapability(Protocol):
    def execute(self, cmd: str) -> tuple[int, str]: ...

@runtime_checkable
class FileTransfer(Protocol):
    def push(self, local: str, remote: str) -> None: ...
    def pull(self, remote: str, local: str) -> None: ...

class TypedDut:
    """Thin typed wrapper — gives tests full autocomplete for free."""
    def __init__(self, dut): self._dut = dut

    @property
    def exec(self) -> ExecCapability: return self._dut.require(EXEC)
    @property
    def files(self) -> FileTransfer: return self._dut.require(FILE_TRANSFER)
```

Expose it as a fixture in conftest:

```python
@pytest.fixture
def target(dut) -> TypedDut:
    return TypedDut(dut)
```

Tests get full autocomplete with zero annotations:

```python
def test_deploy(target):
    code, out = target.exec.execute("uname -a")  # IDE resolves .execute()
    target.files.push("/tmp/fw.bin", "/opt/fw.bin")  # IDE resolves .push()
```

The verify hook can enforce protocol compliance:

```python
@pytest.hookimpl
def pytest_itf_verify(dut, config):
    assert isinstance(dut.require(EXEC), ExecCapability), "Bad exec provider!"
```

**Key principle**: this is a *downstream governance choice*, not an ITF concern. ITF stays untyped and decoupled; teams that want typing create their own vocabulary layer. See `examples/governance_protocols/` for a complete working demo.

### Capability Gating

The `@requires_capabilities` decorator auto-skips tests whose requirements aren't met:

```python
from score.itf.core.capability_gating import requires_capabilities

@requires_capabilities("exec", "file_transfer")
def test_deploy(dut):
    # Only runs on targets providing both capabilities
    ...

# Device-scoped: check availability on a specific device
@requires_capabilities("ssh", device="integ")
def test_remote_integ(dut):
    ssh = dut["integ"]["ssh"]
    ...

# Stacked: require capabilities on multiple devices
@requires_capabilities("ping", device="safety")
@requires_capabilities("ping", device="integ")
def test_both_reachable(dut):
    ...
```

### Fault Injection & Recovery

```python
def test_degraded_mode(dut):
    dut.disable("file_transfer")       # block a capability
    # ... test graceful degradation ...
    dut.enable("file_transfer")        # restore

def test_crash_recovery(dut):
    dut.rebuild()                      # tear down and re-realize from scratch
```

## Plugin Categories

| Category | Purpose | Examples |
|----------|---------|----------|
| **targets/** | Provide `ctf/target` anchor + inherent capabilities | docker, qemu, mock |
| **capabilities/** | Additive capabilities requiring target facts | ssh, ping, dlt |
| **utility/** | Observe and report (never affect DUT) | governance, logger, dashboards |
| **domain/** | Persist data (results, artifacts) | sqlite_logger |
| **env/** | Simulate conditions | heartbeat, fault injection |

## Structured Logging

ITF includes a structured file logger plugin that captures the entire lifecycle with visual section separators:

```bash
pytest test/ -p score.itf.plugins.utility.logger.plugin \
    --itf-logfile=test.log --itf-loglevel=DEBUG
```

Or add it to your conftest's `pytest_plugins`:
```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.targets.docker.plugin",
    "score.itf.plugins.utility.logger.plugin",  # structured file logger
]
```

The log output shows the full lifecycle with section separators:
```
═══════════════════════════════════════════════════════════════════════════════
║ DECLARE — Graph Construction
═══════════════════════════════════════════════════════════════════════════════
[2026-07-08 13:39:11.177] [INF] [itf_plugin]   [provider] ctf/target ← image, config  (docker_anchor)
[2026-07-08 13:39:11.177] [INF] [itf_plugin]   [provider] itf/cap/exec ← ctf/target  (docker_exec)

═══════════════════════════════════════════════════════════════════════════════
║ COMPOSITION GRAPH — Resolved
═══════════════════════════════════════════════════════════════════════════════
[...] Mode: loose
[...]   ┌─ Tier 0 (2 nodes)
[...]   │  ● itf/target/docker/config [descriptor]
[...]   │  ● itf/target/docker/image [descriptor]
[...]   └────────────────────────────────────────

═══════════════════════════════════════════════════════════════════════════════
║ VERIFY — Startup Checks
═══════════════════════════════════════════════════════════════════════════════
║ CHECK — ping
[...] Ping startup check: localhost OK
[...] Result: PASSED (1.013s)
║ CHECK — docker
[...] Docker startup check: container exec OK
[...] Result: PASSED (2.348s)
║ VERIFY SUMMARY — 4 passed (4 total)

═══════════════════════════════════════════════════════════════════════════════
║ TEST CALL — test_docker_runs_1
═══════════════════════════════════════════════════════════════════════════════
[...] Result: PASSED (0.127s)
```

**Architecture**: The ITF plugin emits phase markers as log records with a special `_itf_section` attribute. The logger plugin's formatter detects these and renders them as visual blocks. Without the logger plugin, they appear as normal INFO messages. This means:
- ITF owns the lifecycle and emits all diagnostic info
- The logger plugin is purely a rendering layer — no coupling to ITF internals
- Any custom handler can consume the same structured records

## Running Tests

### With Bazel

```bash
bazel test //test/...                         # all tests
bazel test //test:test_docker --test_output=all
bazel test //test:test_docker --test_arg="-s"  # pytest output
```

### Without Bazel (development)

```bash
PYTHONPATH=. python -m pytest tests/integration/ \
    --docker-image=ubuntu:24.04 -v

PYTHONPATH=. python -m pytest tests/component/ -v  # mock target
```

## QEMU Setup (Linux)

```bash
# Check KVM support
ls -l /dev/kvm

# Install (Ubuntu/Debian)
sudo apt-get install qemu-kvm libvirt-daemon-system \
    libvirt-clients bridge-utils qemu-utils
sudo adduser $(id -un) libvirt
sudo adduser $(id -un) kvm
```

ITF auto-detects KVM and falls back to TCG emulation if unavailable.

## Development

```bash
bazel run //:requirements.update   # regenerate deps
bazel run //:format.fix            # format code
bazel test //test/... --test_output=all --nocache_test_results
```

## Contributing

Contributions are welcome! Please ensure:
- All tests pass: `bazel test //test/...`
- Code is formatted: `bazel run //:format.fix`
- New features include tests and documentation

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.
