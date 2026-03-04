# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
"""
Serial console support for QEMU targets.

This module provides serial channel management for running commands inside
QEMU guests without requiring SSH/network configuration.

The implementation uses extra QEMU serial ports (COM2-COM4) mapped to Unix
sockets for dedicated per-process output channels. The main console (COM1/stdio)
is used for command execution and synchronization.
"""

import logging
import os
import shutil
import socket
import tempfile
import threading
import time
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class SerialChannel:
    """Represents a dedicated QEMU serial port channel.

    Each channel consists of a host-side Unix socket and a corresponding
    guest-side device path (e.g. /dev/ser2 on QNX, /dev/ttyS1 on Linux).
    
    QEMU acts as the server (-serial unix:<path>,server=on,wait=off),
    and the host connects as a client to read guest process output.
    """

    def __init__(self, socket_path: str, guest_device: str) -> None:
        """Initialize a serial channel.
        
        Args:
            socket_path: Path to the Unix socket on the host.
            guest_device: Device path inside the guest (e.g. /dev/ser2).
        """
        self.socket_path = socket_path
        self.guest_device = guest_device
        self._connection: Optional[socket.socket] = None

    def connect(self, timeout: float = 30) -> None:
        """Connect to the QEMU-created Unix socket.
        
        Retries until the socket is available (QEMU creates it after startup).
        
        Args:
            timeout: Maximum time to wait for connection.
            
        Raises:
            SerialConnectionError: If connection times out.
        """
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.socket_path)
                sock.setblocking(True)
                self._connection = sock
                logger.debug(f"Connected to serial channel: {self.socket_path}")
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
                last_error = e
                time.sleep(0.2)
        raise SerialConnectionError(
            f"Timed out connecting to QEMU serial socket: {self.socket_path}. "
            f"Last error: {last_error}"
        )

    def makefile(self):
        """Return a file-like object for line-oriented reading."""
        if self._connection is None:
            raise SerialConnectionError("Channel not connected")
        return self._connection.makefile("rb")

    def close(self) -> None:
        """Close the socket connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    @property
    def is_connected(self) -> bool:
        """Check if the channel is connected."""
        return self._connection is not None


class SerialChannelPool:
    """Manages a fixed pool of extra QEMU serial channels.

    Channels are pre-allocated at QEMU launch time. Callers acquire a
    channel before starting a guest process and release it when done.
    
    This limits concurrent background processes to the number of available
    serial channels (typically 3: COM2-COM4).
    """

    def __init__(self, channels: List[SerialChannel]) -> None:
        """Initialize the channel pool.
        
        Args:
            channels: List of SerialChannel instances to manage.
        """
        self._available = list(channels)
        self._in_use: List[SerialChannel] = []
        self._lock = threading.Lock()

    def acquire(self) -> Optional[SerialChannel]:
        """Acquire an available channel.
        
        Returns:
            A SerialChannel if available, None if all channels are in use.
        """
        with self._lock:
            if not self._available:
                return None
            channel = self._available.pop()
            self._in_use.append(channel)
            logger.debug(f"Acquired serial channel: {channel.guest_device}")
            return channel

    def release(self, channel: SerialChannel) -> None:
        """Release a channel back to the pool.
        
        Args:
            channel: The channel to release.
        """
        with self._lock:
            if channel in self._in_use:
                self._in_use.remove(channel)
                self._available.append(channel)
                logger.debug(f"Released serial channel: {channel.guest_device}")

    def close_all(self) -> None:
        """Close all channels and clear the pool."""
        with self._lock:
            for ch in self._available + self._in_use:
                ch.close()
            self._available.clear()
            self._in_use.clear()

    @property
    def available_count(self) -> int:
        """Number of available channels."""
        with self._lock:
            return len(self._available)

    @property
    def total_count(self) -> int:
        """Total number of channels in the pool."""
        with self._lock:
            return len(self._available) + len(self._in_use)


class SerialConnectionError(Exception):
    """Raised when serial connection fails."""
    pass


class SerialProcessError(Exception):
    """Raised when serial process execution fails."""
    pass


def create_serial_channels(
    num_channels: int = 3,
    tmpdir: Optional[str] = None,
    guest_device_prefix: str = "/dev/ser",
    guest_device_start: int = 2,
) -> Tuple[List[SerialChannel], List[str], str]:
    """Create serial channels and QEMU args for extra serial ports.

    Each extra port uses: -serial unix:<path>,server=on,wait=off

    QEMU x86_64 emulates ISA 8250 UARTs at the standard COM port I/O addresses.
    COM1 (stdio) is the main console; COM2-COM4 are available for dedicated
    process output channels.
    
    For QNX guests, these appear as /dev/ser2 - /dev/ser4.
    For Linux guests, these appear as /dev/ttyS1 - /dev/ttyS3.

    Args:
        num_channels: Number of extra serial channels to create (default 3).
        tmpdir: Directory for Unix sockets. If None, a temp dir is created.
        guest_device_prefix: Device path prefix in guest (default "/dev/ser" for QNX).
        guest_device_start: Starting device number (default 2, since COM1 is console).

    Returns:
        Tuple of (list of SerialChannel, list of QEMU args, tmpdir path).
    """
    if tmpdir is None:
        tmpdir = tempfile.mkdtemp(prefix="itf_qemu_serial_")
    
    channels: List[SerialChannel] = []
    qemu_args: List[str] = []
    
    for i in range(num_channels):
        sock_path = os.path.join(tmpdir, f"serial_{i}.sock")
        guest_dev = f"{guest_device_prefix}{guest_device_start + i}"
        
        ch = SerialChannel(sock_path, guest_dev)
        channels.append(ch)
        qemu_args.extend(["-serial", f"unix:{sock_path},server=on,wait=off"])
        
    logger.info(f"Created {num_channels} serial channels in {tmpdir}")
    return channels, qemu_args, tmpdir


def cleanup_serial_channels(tmpdir: str) -> None:
    """Clean up the temporary directory for serial sockets.
    
    Args:
        tmpdir: Path to the temporary directory to remove.
    """
    if tmpdir and os.path.isdir(tmpdir):
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
            logger.debug(f"Cleaned up serial channel tmpdir: {tmpdir}")
        except Exception as e:
            logger.warning(f"Failed to clean up {tmpdir}: {e}")


class SerialProcess:
    """Runs a command inside QEMU guest with output on a dedicated serial channel.

    Each process is assigned a dedicated QEMU serial port channel so its
    output never intermixes with other processes or the main console.
    
    The host reads from the channel's Unix socket in a background thread,
    providing real-time log output.

    Completion is signaled through the serial channel: after the command
    finishes, a unique sentinel line containing the exit code is written
    to the same serial device. The background reader thread detects the
    sentinel, stores the exit code, and sets an event.
    """

    EXIT_SENTINEL = "___ITF_QEMU_EXIT_CODE___"

    def __init__(
        self,
        console,
        channel_pool: SerialChannelPool,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        """Initialize a serial process.
        
        Args:
            console: The main QEMU console for launching commands.
            channel_pool: Pool to acquire output channels from.
            command: Command to execute in the guest.
            cwd: Working directory (optional).
            timeout: Default timeout for wait_for_exit.
        """
        self._console = console
        self._channel_pool = channel_pool
        self._command = command
        self._timeout = timeout
        self._cwd = cwd
        self._channel: Optional[SerialChannel] = None
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._pid = -1
        self._exit_code = -1
        self._stream_thread: Optional[threading.Thread] = None
        self._output_lines: List[str] = []
        self._logger = logging.getLogger(f"SerialProcess[{command[:30]}]")

    def __enter__(self):
        """Start the process and output streaming."""
        self._channel = self._channel_pool.acquire()
        if self._channel is None:
            raise SerialProcessError(
                "No serial channels available. Cannot run more concurrent "
                f"processes than available channels ({self._channel_pool.total_count})."
            )

        cwd_prefix = f"cd {self._cwd}; " if self._cwd else ""
        guest_dev = self._channel.guest_device

        # Build a shell command that:
        #  1. Redirects stdout+stderr to the dedicated serial device
        #  2. Traps SIGINT to forward it to the child process
        #  3. After the command exits, echoes a sentinel line with exit code
        shell_cmd = (
            f"/bin/sh -c '"
            f"{cwd_prefix}"
            f"{self._command} > {guest_dev} 2>&1 &"
            "CHILD_PID=$!; "
            "trap \"kill -s SIGINT $CHILD_PID\" INT; "
            "wait $CHILD_PID; "
            f"echo \"{self.EXIT_SENTINEL}=$?\" > {guest_dev}"
            "'"
        )

        self._pid = self._console.run_sh_cmd_async(shell_cmd)
        self._logger.info(
            f"Launched command '{self._command}' with PID {self._pid}, "
            f"output on {guest_dev}"
        )

        # Start reading from the channel's Unix socket in a background thread
        self._stream_thread = threading.Thread(
            target=self._stream_output,
            name=f"serial-stream-{self._pid}",
            daemon=True,
        )
        self._stream_thread.start()

        return self

    def _stream_output(self):
        """Read lines from the serial channel socket and log them live."""
        try:
            sock_file = self._channel.makefile()
            while not self._stop_event.is_set():
                line = sock_file.readline()
                if not line:
                    break
                    
                decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not decoded:
                    continue

                # Strip serial flow-control characters (XON, XOFF)
                stripped = decoded.lstrip("\x00\x11\x13")

                # Check for the exit sentinel
                if stripped.startswith(self.EXIT_SENTINEL + "="):
                    try:
                        self._exit_code = int(stripped.split("=", 1)[1].strip())
                    except (ValueError, IndexError):
                        self._exit_code = -1
                    self._done_event.set()
                    break

                self._output_lines.append(decoded)
                self._logger.info(decoded)
        except Exception as e:
            if not self._stop_event.is_set():
                self._logger.warning(f"Stream read error: {e}")

    def wait_for_exit(self, timeout: Optional[int] = None) -> int:
        """Wait for the process to exit and return its exit code.
        
        Args:
            timeout: Maximum time to wait (uses default if None).
            
        Returns:
            Exit code, or -1 on timeout.
        """
        effective_timeout = timeout if timeout is not None else self._timeout

        if self._done_event.wait(timeout=effective_timeout):
            return self._exit_code

        self._logger.error(f"Timed out waiting for PID {self._pid} to finish")
        return -1

    def kill(self):
        """Kill the process using SIGINT."""
        if self._pid > 0:
            self._console.run_sh_cmd_output(f"kill -s SIGINT {self._pid}")
            self._logger.info(f"Sent SIGINT to PID {self._pid}")
            self.wait_for_exit(timeout=5)

    @property
    def output(self) -> List[str]:
        """Return captured output lines."""
        return list(self._output_lines)

    @property
    def exit_code(self) -> int:
        """Return exit code (-1 if not finished)."""
        return self._exit_code

    @property
    def is_running(self) -> bool:
        """Check if the process is still running."""
        return not self._done_event.is_set()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up: wait for process and release channel."""
        # If the process hasn't finished, kill it
        if not self._done_event.is_set():
            self.kill()

        self._stop_event.set()
        if self._stream_thread:
            self._stream_thread.join(timeout=5)

        # Release the channel back to the pool
        if self._channel:
            self._channel_pool.release(self._channel)
            self._channel = None
