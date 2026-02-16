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

ITF is a [`pytest`](https://docs.pytest.org/en/latest/contents.html)-based testing framework designed for ECU (Electronic Control Unit) testing in automotive domains. It provides a flexible, plugin-based architecture that enables testing on multiple target environments including Docker containers, QEMU virtual machines, and real hardware.

## Key Features

- **Plugin-Based Architecture**: Modular design with support for Docker, QEMU, DLT, and custom plugins
- **Target Abstraction**: Unified `Target` interface with capability-based system for different test environments
- **Flexible Testing**: Write tests once, run across multiple targets (Docker, QEMU, hardware)
- **Capability System**: Tests can query and adapt based on available target capabilities
- **Bazel Integration**: Seamless integration with Bazel build system via `py_itf_test` macro
- **SCTF (Software Component Test Framework)**: Docker-based component testing with automatic OCI image packaging via `py_sctf_test` macro
- **Shared Docker Core**: Single `DockerContainer` abstraction used by both ITF and SCTF, with streaming stdout/stderr capture

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

### Basic Test Example

```python
# test_example.py
from score.itf.core.com.ssh import execute_command

def test_ssh_connection(target):
    with target.ssh() as ssh:
        execute_command(ssh, "echo 'Hello from target!'")
```

### BUILD Configuration

```starlark
load("//:defs.bzl", "py_itf_test")
load("//score/itf/plugins:plugins.bzl", "docker")

py_itf_test(
    name = "test_example",
    srcs = ["test_example.py"],
    args = ["--docker-image=ubuntu:24.04"],
    plugins = [docker],
)
```

## Architecture

### Target System

ITF uses a capability-based target system. The `Target` base class provides a common interface that all target implementations extend:

```python
from score.itf.plugins.core import Target

class MyTarget(Target):
    def __init__(self):
        super().__init__(capabilities={'ssh', 'sftp', 'exec'})
```

Tests can check for capabilities and adapt accordingly:

```python
from score.itf.plugins.core import requires_capabilities

@requires_capabilities("exec")
def test_docker_command(target):
    exit_code, output = target.exec_run("ls -la")
    assert exit_code == 0

@requires_capabilities("ssh", "sftp")
def test_file_transfer(target):
    with target.ssh() as ssh:
        # SSH operations
        pass
```

### Plugin System

ITF supports modular plugins that extend functionality:

- **`core`**: Basic functionality that is the entry point for plugin extensions and hooks
- **`docker`**: Docker container targets with `exec` capability
- **`qemu`**: QEMU virtual machine targets with `ssh` and `sftp` capabilities
- **`dlt`**: DLT (Diagnostic Log and Trace) message capture and analysis

## Writing Tests

### Basic Test Structure

Tests receive a `target` fixture that provides access to the target environment:

```python
def test_basic(target):
    # Use target methods based on capabilities
    if target.has_capability("ssh"):
        with target.ssh() as ssh:
            # Perform SSH operations
            pass
```

### Docker Tests

```python
def test_docker_exec(target):
    exit_code, output = target.exec_run("uname -a")
    assert exit_code == 0
    assert b"Linux" in output
```

BUILD file:
```starlark
py_itf_test(
    name = "test_docker",
    srcs = ["test_docker.py"],
    args = ["--docker-image=ubuntu:24.04"],
    plugins = [docker],
)
```

### QEMU Tests

```python
from score.itf.core.com.ssh import execute_command

def test_qemu_ssh(target):
    with target.ssh(username="root", password="") as ssh:
        result = execute_command(ssh, "uname -a")
```

BUILD file:
```starlark
py_itf_test(
    name = "test_qemu",
    srcs = ["test_qemu.py"],
    args = [
        "--qemu-image=$(location //path:qemu_image)",
        "--qemu-config=$(location qemu_config.json)",
    ],
    data = [
        "//path:qemu_image",
        "qemu_config.json",
    ],
    plugins = [qemu],
)
```

QEMU targets are configured using a JSON configuration file that specifies network settings, resource allocation, and other parameters:

```json
{
    "networks": [
        {
            "name": "tap0",
            "ip_address": "169.254.158.190",
            "gateway": "169.254.21.88"
        }
    ],
    "ssh_port": 22,
    "qemu_num_cores": 2,
    "qemu_ram_size": "1G"
}
```


### Capability-Based Tests

The `@requires_capabilities` decorator automatically skips tests if the target doesn't support required capabilities:

```python
from score.itf.plugins.core import requires_capabilities

@requires_capabilities("exec")
def test_docker_specific(target):
    # Only runs on targets with 'exec' capability
    target.exec_run("echo test")

@requires_capabilities("ssh", "sftp")
def test_network_features(target):
    # Only runs on targets with both 'ssh' and 'sftp'
    with target.ssh() as ssh:
        pass
```

## Communication APIs

### SSH Operations

```python
from score.itf.core.com.ssh import execute_command

def test_ssh_command(target):
    with target.ssh(username="root", password="") as ssh:
        result = execute_command(ssh, "ls -la /tmp")
```

### SFTP File Transfer

```python
def test_file_transfer(target):
    with target.sftp() as sftp:
        sftp.put("local_file.txt", "/tmp/remote_file.txt")
        sftp.get("/tmp/remote_file.txt", "downloaded_file.txt")
```

### Network Testing

```python
def test_ping(target):
    # Check if target is reachable
    assert target.ping(timeout=5)
    
    # Wait until target becomes unreachable
    target.ping_lost(timeout=30, interval=1)
```

## DLT Support

The DLT plugin enables capturing and analyzing Diagnostic Log and Trace messages. `DltWindow` captures DLT messages from a target and allows querying the recorded data:

```python
from score.itf.plugins.dlt.dlt_window import DltWindow
from score.itf.plugins.dlt.dlt_receive import Protocol
import re

def test_with_dlt_capture(target, dlt_config):
    # Create DltWindow to capture DLT messages via UDP
    with DltWindow(
        protocol=Protocol.UDP,
        host_ip="127.0.0.1",
        multicast_ips=["224.0.0.1"],
        print_to_stdout=False,
        binary_path=dlt_config.dlt_receive_path,
    ) as window:
        # Perform operations that generate DLT messages
        with target.ssh() as ssh:
            execute_command(ssh, "my_application")
        
        # Access the recorded DLT data
        record = window.record()
        
        # Query for specific DLT messages
        query = {
            "apid": re.compile(r"APP1"),
            "payload": re.compile(r".*Started successfully.*")
        }
        results = record.find(query=query)
        assert len(results) > 0
        
        # Or iterate through all messages
        for frame in record.find():
            if "error" in frame.payload.lower():
                print(f"Error found: {frame.payload}")
```

DLT messages can also be captured with TCP protocol and optional filters:

```python
# TCP connection to specific target
with DltWindow(
    protocol=Protocol.TCP,
    target_ip="192.168.1.100",
    print_to_stdout=True,
    binary_path=dlt_config.dlt_receive_path,
) as window:
    # Operations...
    pass

# With application/context ID filter
with DltWindow(
    protocol=Protocol.UDP,
    host_ip="127.0.0.1",
    multicast_ips=["224.0.0.1"],
    dlt_filter="APPID CTID",  # Filter by APPID and CTID
    binary_path=dlt_config.dlt_receive_path,
) as window:
    # Operations...
    pass
```

### DLT Configuration File

DLT settings can be specified in a JSON configuration file:

```json
{
    "target_ip": "192.168.122.76",
    "host_ip": "192.168.122.1",
    "multicast_ips": [
        "239.255.42.99"
    ]
}
```

This configuration file can be passed to tests via the `--dlt-config` argument in the BUILD file:

```starlark
py_itf_test(
    name = "test_with_dlt",
    srcs = ["test.py"],
    args = [
        "--dlt-config=$(location dlt_config.json)",
    ],
    data = ["dlt_config.json"],
    plugins = [dlt, docker],
)
```

## Advanced Features

### Target Lifecycle Management

Control whether targets persist across tests using the `--keep-target` flag:

```bash
# Keep target running between tests (faster, but shared state)
bazel test //test:my_test -- --test_arg="--keep-target"

# Default: Create fresh target for each test
bazel test //test:my_test
```

### Custom Docker Configuration

Override Docker settings in tests:

```python
import pytest

@pytest.fixture
def docker_configuration():
    return {
        "environment": {"MY_VAR": "value"},
        "command": "my-custom-command",
        "ports": {"8080/tcp": 8080},
    }

def test_with_custom_docker(target):
    # Uses custom configuration
    pass
```
## Running Tests

### Basic Test Execution

```bash
# Run all tests
bazel test //test/...

# Run specific test
bazel test //test:test_docker

# Show test output
bazel test //test:test_docker --test_output=all

# Show pytest output
bazel test //test:test_docker --test_arg="-s"

# Don't cache test results
bazel test //test:test_docker --nocache_test_results
```

### Docker Tests

```bash
bazel test //test:test_docker \
    --test_arg="--docker-image=ubuntu:24.04"
```

### QEMU Tests

```bash
# With pre-built QEMU image
bazel test //test:test_qemu \
    --test_arg="--qemu-image=/path/to/kernel.img"
```

## QEMU Setup (Linux)

### Prerequisites

Check KVM support:
```bash
ls -l /dev/kvm
```

If `/dev/kvm` exists, your system supports hardware virtualization.

### Installation (Ubuntu/Debian)

```bash
sudo apt-get install qemu-kvm libvirt-daemon-system \
    libvirt-clients bridge-utils qemu-utils

# Add user to required groups
sudo adduser $(id -un) libvirt
sudo adduser $(id -un) kvm

# Re-login to apply group changes
sudo login $(id -un)

# Verify group membership
groups
```

### KVM Acceleration

ITF automatically detects KVM availability and uses:
- **KVM acceleration** when `/dev/kvm` is accessible (fast)
- **TCG emulation** as fallback (slower, no virtualization)

## Development

### Regenerating Dependencies

```bash
bazel run //:requirements.update
```

### Code Formatting

```bash
bazel run //:format.fix
```

### Running Tests During Development

```bash
# Run with verbose output
bazel test //test/... \
    --test_output=all \
    --test_arg="-s" \
    --nocache_test_results
```

## Creating Custom Plugins

Create a custom plugin by implementing the pytest hooks:

```python
# my_plugin.py
import pytest
from score.itf.plugins.core import Target, determine_target_scope

MY_CAPABILITIES = ["custom_feature"]

class MyTarget(Target):
    def __init__(self):
        super().__init__(capabilities=MY_CAPABILITIES)
    
    def custom_operation(self):
        # Custom functionality
        pass

@pytest.fixture(scope=determine_target_scope)
def target_init():
    yield MyTarget()
```

Register the plugin in `plugins.bzl`:

```starlark
load("//bazel:py_itf_plugin.bzl", "py_itf_plugin")

my_plugin = py_itf_plugin(
    py_library = "//path/to:my_plugin",
    enabled_plugins = ["my_plugin"],
    args = [],
    data = [],
    data_as_exec = [],
    tags = [],
)
```

Use in tests:

```starlark
py_itf_test(
    name = "test_custom",
    srcs = ["test.py"],
    plugins = [my_plugin],
)
```

## Project Structure

```
score/
├── itf/                      # Integration Test Framework
│   ├── core/                 # Core ITF functionality
│   │   ├── com/              # Communication modules (SSH, SFTP)
│   │   ├── docker/           # Shared Docker abstraction (DockerContainer)
│   │   ├── process/          # Process management
│   │   ├── target/           # Target base class
│   │   └── utils/            # Utility functions
│   ├── plugins/              # Plugin implementations
│   │   ├── core.py           # Core plugin with Target and decorators
│   │   ├── docker.py         # Docker plugin (uses core/docker)
│   │   ├── dlt/              # DLT plugin
│   │   └── qemu/             # QEMU plugin
│   └── ...
└── sctf/                     # Software Component Test Framework
    ├── bazel_gen/            # OCI pipeline build rules
    │   ├── collect_solibs.bzl
    │   ├── collect_tarballs.bzl
    │   ├── oci_pipeline.bzl
    │   └── remap_tar.bzl
    ├── environment/          # Execution environment backends
    │   ├── base.py           # Environment ABC + ProcessHandle
    │   └── docker_env.py     # Docker backend (uses core/docker)
    ├── exception/            # SCTF-specific exceptions
    └── plugins/              # Pytest plugin (docker_sandbox fixture)
```

## SCTF — Software Component Test Framework

SCTF is a Docker-based component testing layer within ITF. While `py_itf_test` runs tests against *pre-built* container images, SCTF **packages your build artifacts** (binaries, shared libraries) into an OCI image at build time and provides a structured environment to execute and observe them.

### SCTF vs ITF Docker — When to Use Which

| | `py_itf_test` + docker plugin | `py_sctf_test` |
|---|---|---|
| **Image source** | Pre-built (`--docker-image=ubuntu:24.04`) | Built from your Bazel deps at analysis time |
| **Plugin model** | Composable `py_itf_plugin` structs | Hardcoded `score.sctf.plugins` |
| **Test fixture** | `target` — a `DockerTarget` with exec/ssh capabilities | `docker_sandbox` — an `Environment` with process lifecycle tracking |
| **Use case** | *"I have a container; run tests against it"* (integration testing) | *"Package my software into a container and test it"* (component testing) |

See [score/sctf/README.md](score/sctf/README.md) for a detailed architectural rationale.

### SCTF Quick Start

```python
# test_my_component.py
def test_my_binary(docker_sandbox):
    env = docker_sandbox.environment
    handle = env.execute("/opt/bin/my_app", ["--mode", "test"])
    env.stop_process(handle)
    assert handle.exit_code == 0
```

```starlark
# BUILD
load("@score_itf//bazel:py_sctf_test.bzl", "py_sctf_test")

py_sctf_test(
    name = "test_my_component",
    srcs = ["test_my_component.py"],
    data = [":my_binary_package"],
)
```

The `py_sctf_test` macro automatically:
1. Collects shared libraries from your `data` dependencies
2. Packages them into a `pkg_tar` archive
3. Builds an OCI image via `oci_image` + `oci_tarball`
4. Generates a self-extracting bootstrap script that runs `docker load`
5. Creates a `py_test` with the correct flags to boot the container and run pytest

### SCTF Environment API

The `docker_sandbox` fixture provides a `DockerEnvironment` implementing the `Environment` ABC:

```python
def test_process_lifecycle(docker_sandbox):
    env = docker_sandbox.environment

    # Execute a binary — returns a ProcessHandle
    handle = env.execute("/opt/bin/sender", ["--mode", "send"], cwd="/opt/app")

    # Check if still running
    assert env.is_process_running(handle)

    # Stop with timeout (returns exit code)
    exit_code = env.stop_process(handle, timeout=10.0)

    # Copy files in/out of the container
    env.copy_to("/local/config.json", "/opt/app/config.json")
    env.copy_from("/opt/app/output.log", "/local/output.log")
```

Stdout and stderr from executed processes are automatically captured and streamed to the test log via Python's `logging` module, using the binary name as the logger (e.g., `[INFO] [sender] message`).

## Shared Docker Core

Both ITF's Docker plugin and SCTF's Docker environment delegate container operations to a single shared abstraction: `score.itf.core.docker.DockerContainer`.

```python
from score.itf.core.docker import DockerContainer, get_docker_client

client = get_docker_client()
container = DockerContainer.run(client, image="ubuntu:24.04", command="sleep infinity")

# Synchronous exec
result = container.exec(["echo", "hello"])  # returns (exit_code, output)

# Streaming exec (for log capture)
exec_id, stream = container.exec(["my_app"], stream=True)  # returns (exec_id, generator)

# File transfer
container.copy_to("/local/file", "/container/file")
container.copy_from("/container/file", "/local/file")

# Network inspection
ip = container.get_ip()
gateway = container.get_gateway()

container.stop()
```

This avoids code duplication and ensures both ITF and SCTF benefit from fixes and improvements in one place.

## Contributing

Contributions are welcome! Please ensure:
- All tests pass: `bazel test //test/...`
- Code is formatted: `bazel run //:format.fix`
- New features include tests and documentation

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.
