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
- **Docker Target**: Full-featured `target` fixture with exec, file I/O, log capture, tcpdump, and SSH
- **Flexible Testing**: Write tests once, run across multiple targets (Docker, QEMU, hardware)
- **Capability System**: Tests can query and adapt based on available target capabilities
- **Bazel Integration**: Seamless integration with Bazel build system via `py_itf_test` macro

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

### Docker Target

The Docker plugin provides a `target` fixture that yields a `DockerTarget` instance.
`DockerTarget` wraps a Docker container and provides a rich API for executing
commands, transferring files, capturing logs, running tcpdump, and establishing
SSH connections.

| Feature | Details |
|---|---|
| **Fixture** | `target` |
| **Scope** | function (or session with `--keep-target`) |
| **Yields** | `DockerTarget` |
| **Capabilities** | `exec`, `tcpdump` |

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
    exit_code, output = target.exec("ls -la", detach=False)
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
- **`docker`**: Docker container targets with `exec` and `tcpdump` capabilities
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

Docker tests use the `target` fixture, which provides a `DockerTarget` with
exec, file I/O, log capture, tcpdump, and SSH capabilities:

```python
def test_docker_exec(target):
    exit_code, output = target.exec("uname -a", detach=False)
    assert exit_code == 0
    assert b"Linux" in output
```

Detached execution with automatic log capture:

```python
def test_background_binary(target):
    # Starts binary in background; stdout/stderr are captured to the test log
    exec_id = target.exec(["/opt/bin/my_app"], detach=True)
    assert target.is_exec_running(exec_id)

    # Wait for completion or kill
    target.kill_exec(exec_id)
    target.wait_exec(exec_id, timeout=5)
```

BUILD file:
```starlark
py_itf_test(
    name = "test_docker",
    srcs = ["test_docker.py"],
    args = [
        "--docker-image-bootstrap=$(location //path:image_tarball)",
        "--docker-image=my_image:latest",
    ],
    data = ["//path:image_tarball"],
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
    target.exec("echo test", detach=False)

@requires_capabilities("ssh", "sftp")
def test_network_features(target):
    # Only runs on targets with both 'ssh' and 'sftp'
    with target.ssh() as ssh:
        pass

@requires_capabilities("tcpdump")
def test_tcpdump_capture(target):
    # Only runs on targets with 'tcpdump' capability
    from score.itf.core.com.tcpdump import TcpDumpCapture
    with TcpDumpCapture(target.tcpdump_handler(), filter_expr="icmp") as cap:
        target.exec(["ping", "-c1", "127.0.0.1"], detach=False)
```

## DockerTarget API

The `target` fixture yields a `DockerTarget` instance. Key methods:

| Method | Description |
|---|---|
| `exec(cmd, workdir="/", detach=True)` | Run a command inside the container. Returns exec-ID (detach), `(exit_code, output)` (sync), or `(exec_id, generator)` (stream). Detached execs get automatic log capture. |
| `copy_to(host_path, container_path)` | Copy files from host into the container. |
| `copy_from(container_path, host_path)` | Copy files out of the container. |
| `get_ip(network="bridge")` | Get the container's IP address. |
| `get_gateway(network="bridge")` | Get the network gateway address. |
| `is_exec_running(exec_id)` | Check if a detached exec is still running. |
| `wait_exec(exec_id, timeout)` | Block until exec finishes or times out. |
| `kill_exec(exec_id, signal=9)` | Kill a detached process (works inside Bazel sandbox). |
| `get_exec_output(exec_id)` | Get the captured output of a detached exec. |
| `ssh()` | Open an SSH connection to the container. |
| `tcpdump_handler()` | Return a `DockerTcpDumpHandler` for use with `TcpDumpCapture`. Raises `RuntimeError` if the target lacks the `tcpdump` capability. |
| `stop(timeout=2)` | Stop and remove the container. |

```python
def test_full_api(target):
    # Synchronous exec
    exit_code, output = target.exec(["echo", "hello"], detach=False)
    assert exit_code == 0

    # Detached exec with log capture + kill
    exec_id = target.exec(["/bin/sleep", "60"], detach=True)
    assert target.is_exec_running(exec_id)
    target.kill_exec(exec_id)

    # File transfer
    target.copy_to("/tmp/local_file.txt", "/opt/data/file.txt")
    target.copy_from("/opt/data/result.txt", "/tmp/result.txt")

    # Network info
    ip = target.get_ip()
    gateway = target.get_gateway()
```

### TcpDump Integration

`TcpDumpCapture` is a target-agnostic context manager in `core/com` that
captures network traffic using tcpdump.  Each target plugin provides a
`tcpdump_handler()` method that returns the appropriate
`TcpDumpHandler` implementation (e.g. `DockerTcpDumpHandler` for Docker targets).

#### Basic Usage

```python
from score.itf.core.com.tcpdump import TcpDumpCapture
from score.itf.plugins.core import requires_capabilities

@requires_capabilities("tcpdump")
def test_network_capture(target):
    with TcpDumpCapture(
        target.tcpdump_handler(),
        filter_expr="port 80",
        interface="eth0",
    ) as cap:
        # Run operations that generate network traffic
        target.exec(["curl", "http://example.com"], detach=False)
    # cap.host_path points to the pcap on the host
```

#### TcpDumpCapture Parameters

| Parameter | Default | Description |
|---|---|---|
| `handler` | *(required)* | A `TcpDumpHandler` returned by `target.tcpdump_handler()`. |
| `host_output_path` | `None` | Where to save the pcap on the host. If `None`, a temp file is created. |
| `interface` | `"any"` | Network interface to capture on. |
| `filter_expr` | `""` | BPF filter expression (e.g. `"port 80"`). |
| `target_pcap_path` | `"/tmp/capture.pcap"` | Path on the target where tcpdump writes the capture file. |
| `tcpdump_binary` | `"/usr/sbin/tcpdump"` | Path to the tcpdump binary on the target. |
| `snapshot_length` | `0` | Max bytes per packet (`-s` flag). `0` means unlimited. |
| `rotate_seconds` | `None` | If set, rotate capture files every N seconds (`-G`). |
| `max_packets` | `None` | If set, stop capture after N packets (`-c`). |
| `extra_args` | `None` | Additional CLI flags passed verbatim to tcpdump (e.g. `["--dont-verify-checksums"]`). |

After the context manager exits, two read-only properties are available:

| Property | Description |
|---|---|
| `cap.host_path` | Absolute path to the pcap file on the host. |
| `cap.target_path` | Path to the pcap file on the target (mirrors `target_pcap_path`). |

#### Advanced Example

```python
from score.itf.core.com.tcpdump import TcpDumpCapture
from score.itf.plugins.core import requires_capabilities

@requires_capabilities("tcpdump")
def test_udp_traffic_captured(target):
    with TcpDumpCapture(
        target.tcpdump_handler(),
        interface="lo",
        target_pcap_path="/tmp/example_app_capture.pcap",
        snapshot_length=256,
        extra_args=["--dont-verify-checksums"],
    ) as cap:
        assert cap.target_path == "/tmp/example_app_capture.pcap"
        target.exec(
            ["sh", "-c", "echo hello | nc -u -w1 127.0.0.1 5000"],
            detach=False,
        )
    assert os.path.exists(cap.host_path)
```

#### Custom Handlers

Custom handlers can be implemented for any target type by subclassing
`TcpDumpHandler` from `score.itf.core.com.tcpdump`.  The handler must
implement three methods: `start(cmd)`, `stop(handle)`, and
`retrieve(target_pcap_path, host_path)`.

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

Control the target lifecycle with the `--keep-target` flag:

```bash
# Default: Create a fresh target for each test (clean state)
bazel test //test:my_test

# Keep target running between tests (faster, shared state)
bazel test //test:my_test -- --test_arg="--keep-target"
```

### Custom Docker Configuration

Override Docker settings for integration tests via `docker_configuration`:

```python
import pytest

@pytest.fixture
def docker_configuration():
    return {
        "environment": {"MY_VAR": "value"},
        "command": "my-custom-command",
    }

def test_with_custom_docker(target):
    # Uses custom configuration
    pass
```

The `docker_configuration` fixture supports the following keys:

| Key | Description |
|---|---|
| `environment` | Dict of environment variables |
| `command` | Container entrypoint command |
| `volumes` | Dict of volume mounts (`{host_path: {"bind": path, "mode": "rw"}}`) |
| `privileged` | Run container in privileged mode |
| `network_mode` | Docker network mode (e.g., `"host"`) |
| `shm_size` | Shared memory size (e.g., `"256m"`) |
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
# Run docker tests
bazel test //test:test_docker --test_output=all

# Run example tests
bazel test //examples/itf:test_example_app --test_output=all
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
score/itf/
├── core/                 # Core ITF functionality
│   ├── com/              # Communication modules (SSH, SFTP, ping, tcpdump)
│   │   ├── ssh.py        # SSH connection context manager
│   │   ├── tcpdump.py    # TcpDumpCapture + TcpDumpHandler (abstract)
│   │   ├── sftp.py       # SFTP file transfer
│   │   └── ping.py       # Ping utilities
│   ├── process/          # Process management
│   ├── target/           # Target base class with capability system
│   └── utils/            # Utility functions
├── plugins/              # Plugin implementations
│   ├── core.py           # Core plugin (Target fixture, requires_capabilities)
│   ├── docker/           # Docker plugin
│   │   ├── __init__.py       # Plugin entry point (CLI options, fixtures)
│   │   ├── docker_target.py  # DockerTarget class
│   │   ├── output_reader.py  # OutputReader (detached exec log drain)
│   │   └── tcpdump_handler.py # DockerTcpDumpHandler
│   ├── dlt/              # DLT plugin
│   └── qemu/             # QEMU plugin
└── ...
```

## Contributing

Contributions are welcome! Please ensure:
- All tests pass: `bazel test //test/...`
- Code is formatted: `bazel run //:format.fix`
- New features include tests and documentation

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.
