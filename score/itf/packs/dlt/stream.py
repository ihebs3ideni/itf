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
"""A DLT receiver over TCP, stdlib framing (`dlt.stream`). Constructing it opens no socket;
`dlt.subscribe_stream` (steps.py) does."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from .framing import DltMessage, decode_message


@dataclass(frozen=True)
class StreamConfig:
    ecu_id: str = ""
    buffer: int = 4096
    connect_timeout: float = 60.0


class EndpointLike(Protocol):
    host: str
    port: int


class DltReceiver:
    def __init__(self, endpoint: EndpointLike, *, ecu_id: str = "", buffer: int = 4096, connect_timeout: float = 60.0):
        self.endpoint = endpoint
        self.connect_timeout = connect_timeout
        self.ecu_id = ecu_id
        self.buffer = buffer
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._messages: list[DltMessage] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def subscribe(self) -> None:
        """Connect, retrying until `connect_timeout`: the daemon may still be starting with the target."""
        self._sock = self._connect(time.monotonic() + self.connect_timeout)
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _connect(self, deadline: float) -> socket.socket:
        while True:
            try:
                sock = socket.create_connection((self.endpoint.host, self.endpoint.port), timeout=5)
                sock.settimeout(0.5)
                return sock
            except OSError:
                if time.monotonic() >= deadline or self._stop.is_set():
                    raise
                time.sleep(0.5)

    def _read_loop(self) -> None:
        """Read until closed. A connection the peer ends (a daemon restarting, or a port forwarder
        accepting before the daemon listens) is re-established within `connect_timeout`."""
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                chunk = b""
            if not chunk:
                if self._stop.is_set():
                    break
                try:
                    self._sock.close()
                    self._sock = self._connect(time.monotonic() + self.connect_timeout)
                except OSError:
                    break
                buf = b""
                continue
            buf += chunk
            while True:
                message, buf = decode_message(buf)
                if message is None:
                    break
                with self._lock:
                    self._messages.append(message)
                    if len(self._messages) > self.buffer:
                        del self._messages[: len(self._messages) - self.buffer]

    def _live(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def lines(self) -> list[DltMessage]:
        if not self._live():
            raise RuntimeError("log stream is dead")
        with self._lock:
            return list(self._messages)

    def filter(self, apid: str | None = None, ctid: str | None = None) -> list[DltMessage]:
        return [m for m in self.lines() if (apid is None or m.apid == apid) and (ctid is None or m.ctid == ctid)]

    def close(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
