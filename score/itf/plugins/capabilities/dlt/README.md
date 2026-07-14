# DLT Capability Plugin

Integrates DLT (Diagnostic Logging and Trace) for capturing logs from targets
running a DLT daemon. Supports both host-side and on-target capture.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.capabilities.dlt.plugin",
]
```

## CLI Options

| Option | Required | Description |
|---|---|---|
| `--dlt-receive-path` | Yes | Path to `dlt-receive` binary on the host |
| `--dlt-config` | No | Path to JSON DLT configuration file |
| `--dlt-receive-on-target-path` | No | Path to `dlt-receive` cross-compiled for target |

## Contracts Provided

| Contract | Description |
|---|---|
| `itf/cap/dlt_on_target` | `DltOnTargetComponent` — manage on-target DLT capture |

## Contracts Required

| Contract | Published By |
|---|---|
| `itf/cap/exec` | Target or exec capability plugin |
| `itf/cap/file_transfer` | Target or file transfer capability plugin |
| `itf/dlt/binary_path` | Self-registered descriptor from CLI option |

## Fixtures

| Fixture | Scope | Description |
|---|---|---|
| `dlt_config` | session | DLT configuration dict |
| `dlt` | session | Active `DltReceive` context manager (host-side) |
| `dlt_on_target` | session | `DltOnTargetComponent` (skips if unavailable) |

## DLT Config Format

```json
{
  "host_ip": "192.168.1.100",
  "target_ip": "192.168.1.50",
  "multicast_ips": ["239.0.0.1"]
}
```

## Usage in Tests

```python
def test_dlt_capture(dlt):
    """Host-side DLT capture."""
    with dlt.capture() as logs:
        # trigger something on target
        pass
    assert any("APP1" in msg for msg in logs)

def test_on_target_dlt(dlt_on_target):
    """On-target DLT capture."""
    dlt_on_target.start()
    # ... exercise target ...
    traces = dlt_on_target.stop_and_collect()
    assert len(traces) > 0
```

## Example

```bash
pytest --dlt-receive-path=/usr/bin/dlt-receive \
       --dlt-config=dlt_setup.json \
       tests/
```
