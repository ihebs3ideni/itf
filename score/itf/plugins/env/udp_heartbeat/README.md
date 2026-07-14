# UDP Heartbeat Plugin

Simulates a continuous environment condition by sending periodic UDP packets to
the target. Useful for testing watchdog behavior, keep-alive protocols, or
network presence detection.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.env.udp_heartbeat.plugin",
]
```

## CLI Options

| Option | Default | Description |
|---|---|---|
| `--itf-heartbeat` | off | Enable the UDP heartbeat |
| `--itf-heartbeat-host` | from `itf/net/ip_address` | Target host for heartbeat |
| `--itf-heartbeat-port` | `5555` | Target UDP port |
| `--itf-heartbeat-interval` | `1.0` | Send interval in seconds |
| `--itf-heartbeat-payload` | `"ALIVE"` | Payload string |
| `--itf-heartbeat-autostart` | `true` | Auto-start on provision phase |

## Contracts Provided

| Contract | Description |
|---|---|
| `itf/env/heartbeat` | `HeartbeatController` — runtime control of the heartbeat |

## Contracts Required

| Contract | When |
|---|---|
| `itf/net/ip_address` | Only if `--itf-heartbeat-host` is not set |

## Lifecycle Hooks

- **DECLARE** — registers provider (if `--itf-heartbeat` enabled)
- **PROVISION** — auto-starts heartbeat (if autostart enabled)
- **TEARDOWN** — stops heartbeat

## Runtime API

```python
def test_watchdog(dut):
    hb = dut.require("itf/env/heartbeat")

    hb.start()                        # manual start
    hb.stop()                         # stop sending
    hb.set_payload("CUSTOM")          # change payload
    hb.set_interval(0.5)              # change frequency
    hb.set_target("10.0.0.2", 6000)   # redirect
    print(hb.packets_sent)            # counter
    print(hb.is_running)              # status
```

## Use Cases

- Watchdog keep-alive testing
- Network presence simulation
- Protocol heartbeat compliance
- Fault injection (stop heartbeat → verify target reacts)

## Example

```bash
pytest --itf-heartbeat --itf-heartbeat-port=9000 --itf-heartbeat-interval=0.5 tests/
```
