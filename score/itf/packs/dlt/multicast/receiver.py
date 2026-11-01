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
"""A DLT receiver joining UDP multicast groups, stdlib framing (`dlt.multicast`)."""

from __future__ import annotations

import ipaddress
import math
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from ..framing import DltMessage, decode_message


@dataclass(frozen=True)
class MulticastConfig:
    sources: str
    port: int = 3490
    dlt_file: str | None = None
    buffer: int = 100000
    stop_timeout: float = 2.0


def parse_sources(text: str) -> list[tuple[str, list[str]]]:
    """`"if_addr=group,group;if_addr=group"` -> [(if_addr, [group, ...]), ...]."""
    sources = []
    for entry in filter(None, (part.strip() for part in text.split(";"))):
        interface, _, groups = entry.partition("=")
        interface = str(ipaddress.IPv4Address(interface.strip()))
        members = [str(ipaddress.IPv4Address(g.strip())) for g in groups.split(",") if g.strip()]
        if any(not ipaddress.IPv4Address(g).is_multicast for g in members):
            raise ValueError(f"non-multicast group in DLT source {entry!r}")
        sources.append((interface, members))
    if not sources:
        raise ValueError("at least one DLT source is required")
    return sources


def split_datagram(datagram: bytes) -> tuple[list[tuple[bytes, DltMessage]], int]:
    """Every complete message in a datagram, raw and decoded, plus the count of dropped bytes."""
    found = []
    while len(datagram) >= 4:
        length = struct.unpack("!H", datagram[2:4])[0]
        if length < 4 or length > len(datagram):
            break
        message, _ = decode_message(datagram[:length])
        found.append((datagram[:length], message))
        datagram = datagram[length:]
    return found, len(datagram)


def storage_header(ecu_id: str, at: float) -> bytes:
    seconds = int(at)
    return (
        b"DLT\x01"
        + struct.pack("<Ii", seconds, int((at - seconds) * 1e6))
        + ecu_id.encode("ascii", errors="replace")[:4].ljust(4, b"\x00")
    )


class MulticastDltReceiver:
    def __init__(
        self,
        sources: str,
        *,
        port: int = 3490,
        dlt_file: str | None = None,
        buffer: int = 100000,
        stop_timeout: float = 2.0,
    ):
        if buffer <= 0:
            raise ValueError("buffer must be positive")
        if not math.isfinite(stop_timeout) or stop_timeout <= 0:
            raise ValueError("stop_timeout must be finite and positive")
        self.sources = parse_sources(sources)
        self.port = port
        self.dlt_file = dlt_file
        self.stop_timeout = stop_timeout
        self._messages: deque[DltMessage] = deque(maxlen=buffer)
        self._received = 0
        self._dropped_bytes = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._error: Exception | None = None

    def subscribe(self) -> None:
        if self.active():
            return
        self.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.port))
            for interface, groups in self.sources:
                for group in groups:
                    membership = socket.inet_aton(group) + socket.inet_aton(interface)
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            sock.settimeout(0.2)
            output = None
            if self.dlt_file:
                Path(self.dlt_file).parent.mkdir(parents=True, exist_ok=True)
                output = open(self.dlt_file, "ab")
        except Exception:
            sock.close()
            raise
        self._sock = sock
        self._error = None
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(sock, output), daemon=True, name="dlt-multicast")
        self._thread.start()

    def bound_port(self) -> int:
        return self._sock.getsockname()[1] if self._sock is not None else self.port

    def _loop(self, sock: socket.socket, output) -> None:
        try:
            while not self._stop.is_set():
                try:
                    datagram = sock.recv(65535)
                except socket.timeout:
                    continue
                received_at = time.time()
                messages, dropped = split_datagram(datagram)
                with self._lock:
                    self._dropped_bytes += dropped
                    for raw, message in messages:
                        self._messages.append(message)
                        self._received += 1
                        if output is not None:
                            output.write(storage_header(message.ecu_id, received_at) + raw)
                if output is not None and messages:
                    output.flush()
        except Exception as exc:
            if not self._stop.is_set():
                self._error = exc
        finally:
            if output is not None:
                output.close()

    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._error is None

    def lines(self) -> list[DltMessage]:
        if not self.active():
            raise RuntimeError("DLT multicast receiver is not active")
        with self._lock:
            return list(self._messages)

    def filter(self, apid: str | None = None, ctid: str | None = None, ecu_id: str | None = None) -> list[DltMessage]:
        return [
            m
            for m in self.lines()
            if (apid is None or m.apid == apid)
            and (ctid is None or m.ctid == ctid)
            and (ecu_id is None or m.ecu_id == ecu_id)
        ]

    def count(self) -> int:
        return self._received

    def dropped_bytes(self) -> int:
        return self._dropped_bytes

    def path(self) -> Path | None:
        return Path(self.dlt_file) if self.dlt_file else None

    def close(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        sock, self._sock = self._sock, None
        if sock is not None:
            sock.close()
        if thread is not None:
            thread.join(timeout=self.stop_timeout)
            if thread.is_alive():
                raise RuntimeError("DLT multicast receiver did not stop within stop_timeout")
