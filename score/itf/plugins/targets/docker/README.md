# Docker Target Plugin

Manages Docker containers as test targets. Provides execution, file transfer,
restart, SSH endpoint, and IP address contracts.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.targets.docker.plugin",
]
```

## CLI Options

| Option | Required | Description |
|---|---|---|
| `--docker-image` | Yes | Docker image to run tests against |
| `--docker-image-bootstrap` | No | Command to run before starting the container |
| `--keep-target` | No | Keep container alive across the whole session |
| `--extract-coverage` | No | Extract coverage files (.gcda) from container |
| `--coverage-output-dir` | No | Directory for coverage output |

## Contracts Provided

| Contract | Description |
|---|---|
| `ctf/target` | DockerRuntime instance (the container) |
| `itf/cap/exec` | Execute commands via `docker exec` |
| `itf/cap/file_transfer` | Copy files via `put_archive`/`get_archive` |
| `itf/cap/restart` | Restart the container |
| `itf/net/ssh_endpoint` | SSH connection params `{host, port, username, password, pkey_path}` |
| `itf/net/ip_address` | Container bridge IP address |

## Runtime Objects Exposed By Contracts

For Docker targets, contracts resolve to the following types:

| Contract | Type | Notes |
|---|---|---|
| `ctf/target` | `DockerRuntime` | Full access to container |
| `itf/cap/exec` | `DockerExecInterface` | Narrow: execute/execute_async/wrap_exec only |
| `itf/cap/file_transfer` | `DockerRuntime` | upload/download methods |
| `itf/cap/restart` | `DockerRuntime` | restart method |

`DockerExecInterface` is a narrow adapter that exposes only execution methods,
preventing accidental coupling to file transfer or restart capabilities through
the exec contract.

## DockerRuntime Methods

When you resolve `ctf/target`, you get a `DockerRuntime` instance exposing all
methods:

| Method | Purpose | Return |
|---|---|---|
| `execute(command: str)` | Run command synchronously in container shell | `(exit_code, output_bytes)` |
| `execute_async(binary_path, args=None, cwd="/")` | Start non-blocking process | `DockerAsyncProcess` |
| `wrap_exec(binary_path, ..., wait_on_exit=...)` | Context-managed async execution | `WrappedProcess` |
| `upload(local_path, remote_path)` | Copy file into container | `None` |
| `download(remote_path, local_path)` | Copy file from container | `None` |
| `restart()` | Restart container | `None` |
| `get_ip(network=None)` | Get container IP | `str` |
| `get_gateway(network=None)` | Get network gateway | `str` |

## DockerExecInterface Methods

When you resolve `itf/cap/exec`, you get a `DockerExecInterface`:

| Method | Purpose | Return |
|---|---|---|
| `execute(command: str)` | Run command synchronously | `(exit_code, output_bytes)` |
| `execute_async(binary_path, args=None, cwd="/")` | Start non-blocking process | `DockerAsyncProcess` |
| `wrap_exec(binary_path, ..., wait_on_exit=...)` | Context-managed async execution | `WrappedProcess` |

### Async Handle Methods

`execute_async(...)` returns a `DockerAsyncProcess` implementing:

- `pid()`
- `is_running()`
- `wait(timeout_s=...)`
- `stop()`
- `get_exit_code()`
- `get_output()`

### Wrapped Process Methods

`wrap_exec(...)` returns a `WrappedProcess` context manager exposing:

- `pid()`
- `is_running()`
- `wait(timeout_s=...)`
- `stop()`
- `get_exit_code()`
- `get_output()`
- `ret_code` (set when context exits)

## Usage Patterns

### 1) Synchronous execution

```python
def test_exec(exec_interface):
    exit_code, out = exec_interface.execute("echo hello")
    assert exit_code == 0
    assert b"hello" in out
```

### 2) Asynchronous execution

```python
def test_async(exec_interface):
    proc = exec_interface.execute_async("sleep", args=["1"])
    assert proc.pid() > 0
    assert proc.wait(timeout_s=30) == 0
```

### 3) Context-managed execution with wrap_exec

```python
def test_wrap(exec_interface):
    with exec_interface.wrap_exec("sleep", args=["1"], wait_on_exit=True) as wp:
        assert wp.is_running() or True  # process may finish quickly
    assert wp.ret_code == 0
```

### 4) File transfer and restart through the same runtime object

```python
def test_transfer_and_restart(dut):
    ft = dut.require("itf/cap/file_transfer")
    rs = dut.require("itf/cap/restart")

    ft.upload("local.txt", "/tmp/remote.txt")
    rs.restart()
```

## Contracts Required (Descriptors)

| Contract | Source |
|---|---|
| `itf/target/docker/image` | From `--docker-image` CLI option |
| `itf/target/docker/config` | Docker configuration dict |

## Verify Hook

The plugin runs a basic health check during the verify phase:

```
echo ok   # via itf/cap/exec
```

If this fails, behavior depends on run mode (LOOSE = warn, STRICT = abort).

## Example

```bash
pytest --docker-image=ubuntu:24.04 tests/
```
