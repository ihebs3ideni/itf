# QEMU Target Plugin

Manages QEMU virtual machines as test targets. Boots a VM, waits for network,
and publishes exec/file-transfer capabilities over SSH/SFTP.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.targets.qemu.plugin",
    "score.itf.plugins.capabilities.ssh.plugin",  # required for exec/file_transfer
]
```

## CLI Options

| Option | Required | Description |
|---|---|---|
| `--qemu-config` | Yes | Path to JSON file with target configuration |
| `--qemu-image` | No | Path to a QEMU image (overrides config) |

## Contracts Provided

| Contract | Description |
|---|---|
| `ctf/target` | QemuRuntime instance (the VM process) |
| `itf/cap/exec` | Delegates to `itf/cap/ssh` |
| `itf/cap/file_transfer` | Delegates to `itf/cap/sftp` |
| `itf/cap/restart` | Restart QEMU process |
| `itf/net/ssh_endpoint` | `{host, port, username="root", password="", pkey_path=""}` |
| `itf/net/ip_address` | Target IP from config |

## Contracts Required

| Contract | Source |
|---|---|
| `itf/target/qemu/runtime_config` | From `--qemu-config` |
| `itf/cap/ssh` | SSH capability plugin |
| `itf/cap/sftp` | SSH capability plugin (SFTP) |

## Verify Hook

The plugin runs two health checks during verify:

1. **Ping** — ICMP reachability to target IP
2. **SSH echo** — Execute `echo ok` over SSH

## QEMU Config Format

```json
{
  "target_ip": "10.0.2.15",
  "ssh_port": 2222,
  "qemu_binary": "qemu-system-aarch64",
  "machine": "virt",
  "cpu": "cortex-a57",
  "memory": "2G",
  "extra_args": ["-nographic"]
}
```

## Example

```bash
pytest --qemu-config=targets/aarch64.json tests/
```
