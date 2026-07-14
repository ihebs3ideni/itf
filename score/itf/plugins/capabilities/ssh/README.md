# SSH Capability Plugin

Provides SSH and SFTP connection factories for communicating with targets over
the network. Target-agnostic — works with any target that publishes an SSH
endpoint.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.capabilities.ssh.plugin",
]
```

## CLI Options

None. Connection parameters come from the `itf/net/ssh_endpoint` contract.

## Contracts Provided

| Contract | Description |
|---|---|
| `itf/cap/ssh` | `SshComponent` — execute commands over SSH |
| `itf/cap/sftp` | `SftpComponent` — transfer files over SFTP |

## Contracts Required

| Contract | Published By |
|---|---|
| `itf/net/ssh_endpoint` | Target plugins (docker, qemu, HW) |

The endpoint is a dict: `{host, port, username, password, pkey_path}`.

## Verify Hook

The plugin runs two health checks during verify:

1. **SSH** — `echo ok` over SSH connection
2. **SFTP** — list `/` directory

## Fixtures

| Fixture | Scope | Description |
|---|---|---|
| `ssh_interface` | session | `SshComponent` instance (skips if unavailable) |
| `sftp_interface` | session | `SftpComponent` instance (skips if unavailable) |

## Usage in Tests

```python
def test_remote_file(dut):
    ssh = dut.require("itf/cap/ssh")
    code, output = ssh.execute("cat /etc/hostname")
    assert code == 0
```

Or via fixture:

```python
def test_upload(sftp_interface):
    sftp_interface.put("local.txt", "/tmp/remote.txt")
```

## Design

The SSH plugin never imports a target plugin. It only requires
`itf/net/ssh_endpoint` — the target decides whether SSH is available by
publishing (or not) the endpoint contract.

## Multi-Device Registration

For boards with multiple SoCs, use the device registration helpers to register
the SSH plugin into a device scope:

```python
from score.itf.plugins.capabilities.ssh.plugin import register_ssh, register_sftp

@pytest.hookimpl
def pytest_itf_declare(registry, config):
    with registry.device("safety") as dev:
        dev.add_descriptor(Descriptor(
            "itf/net/ssh_endpoint",
            {"host": "10.0.1.2", "port": 22, "username": "root"},
        ))

    # Register SSH into the safety device's assembly
    register_ssh(registry, device="safety")
    register_sftp(registry, device="safety")
```

Tests access device-scoped SSH via `DeviceProxy`:

```python
def test_safety_soc(dut):
    ssh = dut["safety"].require("itf/cap/ssh")
    with ssh.connect() as conn:
        conn.execute_command("cat /proc/version")
```
