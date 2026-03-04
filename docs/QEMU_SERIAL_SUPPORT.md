# QEMU Serial Channel Support

## Overview

ITF's QEMU plugin supports an alternative command execution mode using serial channels instead of SSH. This enables direct command execution on QEMU guests without requiring network configuration or SSH daemon setup.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Host System                                │
│                                                                      │
│  ┌──────────────┐     ┌─────────────────────────────────────────┐   │
│  │  Test Code   │     │              QEMU Process                │   │
│  │              │     │                                          │   │
│  │  target.exec │────►│  -serial mon:stdio      (COM1 - console) │   │
│  │              │     │  -serial unix:sock1     (COM2 - ch0)     │   │
│  └──────┬───────┘     │  -serial unix:sock2     (COM3 - ch1)     │   │
│         │             │  -serial unix:sock3     (COM4 - ch2)     │   │
│         │             └─────────────────────────────────────────┘   │
│         │                         │         │         │             │
│         │                         ▼         ▼         ▼             │
│         │             ┌─────────────────────────────────────────┐   │
│         │             │           Unix Sockets (tmpdir)          │   │
│         │             │   /tmp/itf_serial_xxx/serial_0.sock     │   │
│         │             │   /tmp/itf_serial_xxx/serial_1.sock     │   │
│         │             │   /tmp/itf_serial_xxx/serial_2.sock     │   │
│         │             └─────────────────────────────────────────┘   │
│         │                         ▲         ▲         ▲             │
│         │                         │         │         │             │
│         ▼                         │         │         │             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    SerialChannelPool                          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐              │   │
│  │  │ Channel 0  │  │ Channel 1  │  │ Channel 2  │              │   │
│  │  │ /dev/ser2  │  │ /dev/ser3  │  │ /dev/ser4  │  (guest dev) │   │
│  │  └────────────┘  └────────────┘  └────────────┘              │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         QEMU Guest (QNX/Linux)                       │
│                                                                      │
│  /dev/ser1 (COM1) ── Main console (stdin/stdout)                    │
│  /dev/ser2 (COM2) ── Serial channel 0 output                        │
│  /dev/ser3 (COM3) ── Serial channel 1 output                        │
│  /dev/ser4 (COM4) ── Serial channel 2 output                        │
│                                                                      │
│  Command execution:                                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  /bin/sh -c 'command > /dev/ser2 2>&1 &                        │ │
│  │              CHILD_PID=$!;                                      │ │
│  │              trap "kill -s SIGINT $CHILD_PID" INT;             │ │
│  │              wait $CHILD_PID;                                   │ │
│  │              echo "___ITF_QEMU_EXIT_CODE___=$?" > /dev/ser2'   │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### SerialChannel
Represents a single QEMU serial port channel. Each channel consists of:
- **Host side**: Unix socket created by QEMU (`-serial unix:<path>,server=on,wait=off`)
- **Guest side**: Device path (e.g., `/dev/ser2` for QNX, `/dev/ttyS1` for Linux)

```python
class SerialChannel:
    socket_path: str      # Host Unix socket path
    guest_device: str     # Guest device path

    def connect(timeout: float) -> None
    def makefile() -> IO
    def close() -> None
```

### SerialChannelPool
Manages a fixed pool of serial channels for concurrent process execution. Channels are pre-allocated at QEMU startup.

```python
class SerialChannelPool:
    def acquire(timeout: float) -> Optional[SerialChannel]
    def release(channel: SerialChannel) -> None

    @contextmanager
    def get_channel(timeout: float) -> SerialChannel

    @property
    def available_count -> int
    @property
    def total_count -> int
```

### SerialProcess
Represents a command running on the guest with output redirected to a serial channel.

```python
class SerialProcess:
    EXIT_SENTINEL = "___ITF_QEMU_EXIT_CODE___"

    def wait_for_exit(timeout: int) -> int
    def kill() -> None

    @property
    def output -> List[str]
    @property
    def exit_code -> int
    @property
    def is_running -> bool
```

## How It Works

### 1. QEMU Startup
When `enable_serial_channels: true` is set in config:

1. `create_serial_channels()` creates a temporary directory with Unix sockets
2. QEMU is launched with additional `-serial` arguments for each channel
3. After QEMU starts, each `SerialChannel` connects to its Unix socket
4. A `SerialChannelPool` is created to manage channel allocation

### 2. Command Execution
When `target.exec("command")` is called:

1. Pool acquires an available channel
2. Command is wrapped with output redirection and exit sentinel:
   ```sh
   /bin/sh -c 'command > /dev/ser2 2>&1 & CHILD_PID=$!; wait $CHILD_PID; echo "___ITF_QEMU_EXIT_CODE___=$?" > /dev/ser2'
   ```
3. Wrapped command is sent to guest via main console
4. Background thread reads output from the channel's Unix socket
5. When sentinel is detected, exit code is parsed and process completes

### 3. Exit Code Detection
The sentinel pattern `___ITF_QEMU_EXIT_CODE___=N` is written to the serial device after command completion. The reader thread:
- Parses the exit code from the sentinel
- Sets the done event
- Stops reading

## Configuration

### qemu_config.json
```json
{
    "networks": [...],
    "ssh_port": 22,
    "qemu_num_cores": 2,
    "qemu_ram_size": "1G",
    "enable_serial_channels": true,
    "num_serial_channels": 3,
    "guest_device_prefix": "/dev/ser"
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable_serial_channels` | bool | `false` | Enable serial exec mode |
| `num_serial_channels` | int | `3` | Number of concurrent channels (1-10) |
| `guest_device_prefix` | string | `"/dev/ttyS"` | Device prefix in guest (`/dev/ser` for QNX) |

## Usage

### Test Code
```python
import score.itf.plugins.core

@score.itf.plugins.core.requires_capabilities("exec")
def test_exec_command(target):
    """Test requires 'exec' capability - skipped if serial not enabled."""
    with target.exec("echo hello") as proc:
        exit_code = proc.wait_for_exit(timeout=10)
        assert exit_code == 0
        assert "hello" in "\n".join(proc.output)
```

### Capabilities
When serial channels are enabled, `QemuTarget` gains the `exec` capability:
- Base capabilities: `["ssh", "sftp"]`
- With serial: `["ssh", "sftp", "exec"]`

Tests decorated with `@requires_capabilities("exec")` will:
- Run when serial channels are enabled
- Skip when serial channels are disabled

## Limitations

1. **Concurrent Process Limit**: Limited by `num_serial_channels` (default 3)
2. **No stdin**: Commands cannot receive stdin input
3. **Binary Output**: May have issues with binary output due to serial encoding
4. **QNX/Linux Only**: Device paths are OS-specific

## Comparison: Serial vs SSH

| Feature | Serial Exec | SSH |
|---------|-------------|-----|
| Network required | No | Yes |
| SSH daemon required | No | Yes |
| Setup complexity | Low | Medium |
| Concurrent commands | Limited (3) | Unlimited |
| stdin support | No | Yes |
| Binary output | Limited | Full |
| Exit code detection | Sentinel pattern | Native |

## Files

| File | Description |
|------|-------------|
| `serial_console.py` | SerialChannel, SerialChannelPool, SerialProcess |
| `qemu.py` | QEMU process with serial channel initialization |
| `qemu_process.py` | QemuProcess wrapper with channel_pool property |
| `qemu_target.py` | QemuTarget with exec() method |
| `config.py` | Pydantic config with serial options |
