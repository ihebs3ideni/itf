# Ping Capability Plugin

Provides ICMP ping capability for verifying target network reachability.
Target-agnostic — works with any target that publishes an IP address.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.capabilities.ping.plugin",
]
```

## CLI Options

None.

## Contracts Provided

| Contract | Description |
|---|---|
| `itf/cap/ping` | `PingComponent` — ICMP ping wrapper |

## Contracts Required

| Contract | Published By |
|---|---|
| `itf/net/ip_address` | Target plugins |

## Verify Hook

The plugin pings the target IP during the verify phase as a health check.

## Fixtures

| Fixture | Scope | Description |
|---|---|---|
| `ping_interface` | session | `PingComponent` instance (skips if unavailable) |

## Usage in Tests

```python
def test_target_reachable(dut):
    ping = dut.require("itf/cap/ping")
    assert ping.ping(timeout=5)
```

Or via fixture:

```python
def test_network(ping_interface):
    assert ping_interface.ping(count=3, timeout=10)
```

## API

```python
class PingComponent:
    def ping(self, count=1, timeout=5) -> bool: ...
```

## Multi-Device Registration

For multi-SoC boards, use the device registration helper:

```python
from score.itf.plugins.capabilities.ping.plugin import register_ping

@pytest.hookimpl
def pytest_itf_declare(registry, config):
    with registry.device("safety") as dev:
        dev.add_descriptor(Descriptor("itf/net/ip_address", "10.0.1.2"))

    register_ping(registry, device="safety")
```

```python
def test_safety_reachable(dut):
    ping = dut["safety"].require("itf/cap/ping")
    assert ping.ping()
```
