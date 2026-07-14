# Mock Target Plugin

In-memory mock target for testing ITF plugins and framework behavior without
real hardware or containers. Records all commands and file operations.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.targets.mock.plugin",
]
```

## CLI Options

None. The mock target is zero-configuration.

## Contracts Provided

| Contract | Description |
|---|---|
| `ctf/target` | MockRuntime instance |
| `itf/cap/exec` | Records commands, returns configurable exit codes |
| `itf/cap/file_transfer` | In-memory file storage |
| `itf/net/ip_address` | Always `"127.0.0.1"` |

## Contracts Required

None.

## Use Cases

- **Plugin development** — test lifecycle hooks without waiting for boot
- **Framework tests** — validate composition and lifecycle behavior
- **CI smoke tests** — verify test collection without hardware

## Example

```python
def test_mock(dut):
    shell = dut.require("itf/cap/exec")
    code, output = shell.execute("echo hello")
    assert code == 0
```

```bash
pytest tests/  # no extra flags needed
```
