# Console Capability Plugin

Provides serial console connections over COM/UART ports. Works as both a
standalone capability (interactive sessions) and as an exec backend for
targets that only have serial access.

## Loading

```python
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.capabilities.console.plugin",
]
```

## CLI Options

| Option | Default | Description |
|---|---|---|
| `--serial-port` | none | Serial device path (e.g. `/dev/ttyUSB0`, `COM3`). Auto-registers endpoint. |
| `--serial-baudrate` | `115200` | Baud rate for the connection |
| `--serial-prompt` | `"# "` | Expected shell prompt for health checks and `execute()` |

## Contracts Provided

| Contract | Description |
|---|---|
| `itf/cap/console` | `ConsoleComponent` — factory for serial console sessions |

## Contracts Required

| Contract | Published By |
|---|---|
| `itf/net/serial_endpoint` | Target plugin or auto-registered from `--serial-port` |

The endpoint is a dict: `{port, baudrate, bytesize, parity, stopbits, timeout, xonxoff, rtscts}`.

## Verify Hook

Opens the serial port, sends a newline, and waits for the configured prompt.
If no prompt appears within 10 seconds, the check fails.

## Fixtures

| Fixture | Scope | Description |
|---|---|---|
| `console_interface` | function | `ConsoleComponent` instance (skips if unavailable) |
| `console_session` | function | An open `SerialConsole` session (auto-closes) |

## Usage

### Interactive session (context manager)

```python
def test_serial_output(dut):
    console = dut.require("itf/cap/console")

    with console.open() as session:
        session.write_line("ls /")
        output = session.read_until("# ", timeout=5)
        assert "bin" in output
```

### Execute commands (exec backend)

```python
def test_serial_exec(dut):
    console = dut.require("itf/cap/console")

    # One-shot: opens port, runs command, closes
    code, output = console.execute("uname -a")
    assert code == 0
    assert "Linux" in output
```

### Via fixture

```python
def test_bootlog(console_session):
    console_session.write_line("dmesg | tail -5")
    output = console_session.read_until("# ", timeout=10)
    assert "kernel" in output.lower()
```

### As an exec backend for targets

A target plugin can provide the serial endpoint and rely on the console
plugin to satisfy `itf/cap/exec`:

```python
# In your conftest.py, bind exec to console for serial-only targets
@pytest.hookimpl
def pytest_itf_bindings(registry, config):
    # If your target only has serial, make the console the exec backend
    registry.bind("itf/cap/exec", "itf/cap/exec", "itf/cap/console")
```

## SerialConsole API

```python
class SerialConsole:
    def write(self, data: bytes) -> int: ...
    def write_line(self, text: str) -> int: ...
    def read(self, size: int = 1) -> bytes: ...
    def read_all(self) -> bytes: ...
    def read_until(self, expected: str, timeout: float = 5.0) -> str: ...
    def execute(self, command: str, prompt: str = "# ", timeout: float = 10.0) -> tuple[int, str]: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
    @property
    def is_open(self) -> bool: ...
```

## Example

```bash
pytest --serial-port=/dev/ttyUSB0 --serial-baudrate=115200 tests/
```
