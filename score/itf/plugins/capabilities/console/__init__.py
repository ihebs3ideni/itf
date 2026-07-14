# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""Serial console capability package.

Library exports: SerialConsole, ConsoleComponent, ConsoleEndpoint.
Plugin wiring lives in ``plugin.py`` (loaded via pytest_plugins).
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Generator

import serial

logger = logging.getLogger(__name__)

# Contracts
CAP_CONSOLE_CONTRACT = "itf/cap/console"
CONSOLE_ENDPOINT_CONTRACT = "itf/net/serial_endpoint"


@dataclass(frozen=True)
class ConsoleEndpoint:
    """Structured serial port connection parameters."""

    port: str
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    timeout: float = 1.0
    xonxoff: bool = False
    rtscts: bool = False

    @classmethod
    def from_mapping(cls, data: dict) -> "ConsoleEndpoint":
        return cls(
            port=str(data["port"]),
            baudrate=int(data.get("baudrate", 115200)),
            bytesize=int(data.get("bytesize", 8)),
            parity=str(data.get("parity", "N")),
            stopbits=float(data.get("stopbits", 1)),
            timeout=float(data.get("timeout", 1.0)),
            xonxoff=bool(data.get("xonxoff", False)),
            rtscts=bool(data.get("rtscts", False)),
        )


class SerialConsole:
    """An active serial console session (context manager).

    Use this to send commands and read responses over a serial port.

    Example::

        with console.open() as session:
            session.write_line("ls /")
            output = session.read_until("# ", timeout=5)
    """

    def __init__(self, connection: serial.Serial):
        self._conn = connection
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._conn.is_open

    def write(self, data: bytes) -> int:
        """Write raw bytes to the serial port."""
        with self._lock:
            return self._conn.write(data)

    def write_line(self, text: str, encoding: str = "utf-8", newline: str = "\n") -> int:
        """Write a line of text followed by a newline."""
        return self.write((text + newline).encode(encoding))

    def read(self, size: int = 1) -> bytes:
        """Read up to ``size`` bytes from the serial port."""
        with self._lock:
            return self._conn.read(size)

    def read_all(self) -> bytes:
        """Read all available bytes in the input buffer."""
        with self._lock:
            return self._conn.read(self._conn.in_waiting or 1)

    def read_until(self, expected: str, timeout: float = 5.0, encoding: str = "utf-8") -> str:
        """Read until ``expected`` string is found or timeout expires.

        Returns the accumulated output (including the expected string if found).
        Raises TimeoutError if the expected string is not found within timeout.
        """
        buf = b""
        expected_bytes = expected.encode(encoding)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                waiting = self._conn.in_waiting
                if waiting:
                    buf += self._conn.read(waiting)
                else:
                    buf += self._conn.read(1)
            if expected_bytes in buf:
                return buf.decode(encoding, errors="replace")
        raise TimeoutError(
            f"Timed out after {timeout}s waiting for {expected!r}. "
            f"Buffer so far: {buf.decode(encoding, errors='replace')!r}"
        )

    def execute(self, command: str, prompt: str = "# ", timeout: float = 10.0) -> tuple[int, str]:
        """Execute a shell command and return (exit_code, output).

        Sends the command, reads until the prompt reappears, then sends
        ``echo $?`` to retrieve the exit code.
        """
        # Flush input buffer
        with self._lock:
            self._conn.reset_input_buffer()

        self.write_line(command)
        output = self.read_until(prompt, timeout=timeout)

        # Strip the command echo and trailing prompt
        lines = output.splitlines()
        # Remove first line (command echo) and last line (prompt)
        body = "\n".join(lines[1:-1]) if len(lines) > 2 else ""

        # Get exit code
        with self._lock:
            self._conn.reset_input_buffer()
        self.write_line("echo $?")
        rc_output = self.read_until(prompt, timeout=5.0)
        rc_lines = rc_output.splitlines()
        try:
            exit_code = int(rc_lines[1].strip()) if len(rc_lines) > 1 else -1
        except (ValueError, IndexError):
            exit_code = -1

        return exit_code, body

    def flush(self) -> None:
        """Flush both input and output buffers."""
        with self._lock:
            self._conn.reset_input_buffer()
            self._conn.reset_output_buffer()

    def close(self) -> None:
        """Close the serial connection."""
        if self._conn.is_open:
            self._conn.close()


class ConsoleComponent:
    """Factory for serial console connections from an endpoint.

    The component holds connection parameters and creates console sessions
    via the ``open()`` context manager.

    Usage as a capability backend::

        console = dut.require("itf/cap/console")
        with console.open() as session:
            code, output = session.execute("uname -a")
            assert code == 0

    Usage as an exec backend::

        # The console plugin can also satisfy itf/cap/exec when the target
        # only has a serial connection (no SSH, no docker exec).
    """

    def __init__(self, endpoint: ConsoleEndpoint):
        self._endpoint = endpoint
        self._active_session: SerialConsole | None = None

    @property
    def endpoint(self) -> ConsoleEndpoint:
        return self._endpoint

    @contextlib.contextmanager
    def open(self, **overrides) -> Generator[SerialConsole, None, None]:
        """Open a serial console session.

        Yields a ``SerialConsole`` context that auto-closes on exit.

        Args:
            **overrides: Override any endpoint parameter (port, baudrate, etc.)
        """
        params = {
            "port": overrides.get("port", self._endpoint.port),
            "baudrate": overrides.get("baudrate", self._endpoint.baudrate),
            "bytesize": overrides.get("bytesize", self._endpoint.bytesize),
            "parity": overrides.get("parity", self._endpoint.parity),
            "stopbits": overrides.get("stopbits", self._endpoint.stopbits),
            "timeout": overrides.get("timeout", self._endpoint.timeout),
            "xonxoff": overrides.get("xonxoff", self._endpoint.xonxoff),
            "rtscts": overrides.get("rtscts", self._endpoint.rtscts),
        }
        logger.debug("Opening serial console on %s @ %d baud", params["port"], params["baudrate"])
        conn = serial.Serial(**params)
        session = SerialConsole(conn)
        try:
            yield session
        finally:
            session.close()
            logger.debug("Closed serial console on %s", params["port"])

    def execute(self, command: str, prompt: str = "# ", timeout: float = 10.0) -> tuple[int, str]:
        """Convenience: open a session, execute one command, close.

        This implements the same interface as ``itf/cap/exec`` backends,
        making the console usable as a drop-in exec backend.
        """
        with self.open() as session:
            return session.execute(command, prompt=prompt, timeout=timeout)


__all__ = [
    "SerialConsole",
    "ConsoleComponent",
    "ConsoleEndpoint",
    "CAP_CONSOLE_CONTRACT",
    "CONSOLE_ENDPOINT_CONTRACT",
]
