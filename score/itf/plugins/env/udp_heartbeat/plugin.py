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
"""ITF UDP Heartbeat — environment plugin that sends continuous UDP payloads.

Usage in conftest::

    pytest_plugins = [
        "score.itf.core.itf_plugin",
        "score.itf.plugins.env.udp_heartbeat.plugin",
    ]

CLI flags::

    --itf-heartbeat              Enable the UDP heartbeat (default: off)
    --itf-heartbeat-host         Target host (default: from itf/net/ip_address)
    --itf-heartbeat-port         Target UDP port (default: 5555)
    --itf-heartbeat-interval     Interval in seconds (default: 1.0)
    --itf-heartbeat-payload      Initial payload hex or ascii (default: "ALIVE")
    --itf-heartbeat-autostart    Start sending on provision (default: true)

This is an env plugin — it simulates/provides an environment condition (continuous
network traffic) that the DUT may depend on. The heartbeat controller is exposed
as a CTF contract so tests can start/stop/change it programmatically.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.dut import DUT
from score.itf.core.ctf.registry import Registry

logger = logging.getLogger(__name__)

# Contract key
HEARTBEAT_CONTRACT = "itf/env/heartbeat"
IP_ADDRESS_CONTRACT = "itf/net/ip_address"


# ---------------------------------------------------------------------------
# Heartbeat controller (the resource exposed via the contract)
# ---------------------------------------------------------------------------
@dataclass
class HeartbeatController:
    """Runtime interface for the UDP heartbeat background task.

    Exposed to tests and other plugins via ``dut.require("itf/env/heartbeat")``.
    """

    host: str
    port: int
    interval: float
    payload: bytes

    _running: bool = field(default=False, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _sock: socket.socket | None = field(default=None, init=False, repr=False)
    _packets_sent: int = field(default=0, init=False, repr=False)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def packets_sent(self) -> int:
        return self._packets_sent

    def start(self) -> None:
        """Start sending UDP heartbeat packets in the background."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._thread = threading.Thread(target=self._send_loop, daemon=True)
            self._thread.start()
            logger.info(
                "Heartbeat started: %s:%d every %.2fs",
                self.host,
                self.port,
                self.interval,
            )

    def stop(self) -> None:
        """Stop the heartbeat sender."""
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._thread:
            self._thread.join(timeout=self.interval * 3)
            self._thread = None
        if self._sock:
            self._sock.close()
            self._sock = None
        logger.info("Heartbeat stopped after %d packets", self._packets_sent)

    def set_payload(self, payload: bytes | str) -> None:
        """Change the payload for subsequent packets."""
        with self._lock:
            self.payload = payload.encode() if isinstance(payload, str) else payload

    def set_interval(self, interval: float) -> None:
        """Change the send interval (takes effect next cycle)."""
        with self._lock:
            self.interval = interval

    def set_target(self, host: str, port: int | None = None) -> None:
        """Redirect heartbeat to a different host/port."""
        with self._lock:
            self.host = host
            if port is not None:
                self.port = port

    def _send_loop(self) -> None:
        while self._running:
            try:
                with self._lock:
                    host, port, payload = self.host, self.port, self.payload
                    interval = self.interval
                    sock = self._sock
                if sock and self._running:
                    sock.sendto(payload, (host, port))
                    self._packets_sent += 1
            except OSError as exc:
                logger.debug("Heartbeat send error: %s", exc)
            time.sleep(interval)


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("itf-heartbeat", "ITF UDP Heartbeat")
    group.addoption(
        "--itf-heartbeat",
        action="store_true",
        default=False,
        help="Enable the UDP heartbeat environment plugin.",
    )
    group.addoption(
        "--itf-heartbeat-host",
        type=str,
        default=None,
        help="Target host for heartbeat (default: uses itf/net/ip_address).",
    )
    group.addoption(
        "--itf-heartbeat-port",
        type=int,
        default=5555,
        help="Target UDP port (default: 5555).",
    )
    group.addoption(
        "--itf-heartbeat-interval",
        type=float,
        default=1.0,
        help="Send interval in seconds (default: 1.0).",
    )
    group.addoption(
        "--itf-heartbeat-payload",
        type=str,
        default="ALIVE",
        help="Payload to send (default: 'ALIVE').",
    )
    group.addoption(
        "--itf-heartbeat-autostart",
        action="store_true",
        default=True,
        help="Auto-start on provision phase (default: true).",
    )


_controller: HeartbeatController | None = None


@pytest.hookimpl
def pytest_itf_declare(registry: Registry, config: pytest.Config) -> None:
    if not config.getoption("--itf-heartbeat", default=False):
        return

    explicit_host = config.getoption("--itf-heartbeat-host", default=None)
    port = config.getoption("--itf-heartbeat-port", default=5555)
    interval = config.getoption("--itf-heartbeat-interval", default=1.0)
    payload = config.getoption("--itf-heartbeat-payload", default="ALIVE")

    if explicit_host:
        # No dependency on ip_address when host is explicitly provided
        @provides(HEARTBEAT_CONTRACT)
        def heartbeat_provider():
            global _controller  # noqa: PLW0603
            _controller = HeartbeatController(
                host=explicit_host,
                port=port,
                interval=interval,
                payload=payload.encode(),
            )
            return _controller

        registry.register(heartbeat_provider)
    else:
        # Depend on the IP address contract for dynamic resolution
        @provides(HEARTBEAT_CONTRACT)
        @requires(IP_ADDRESS_CONTRACT)
        def heartbeat_provider_dynamic(ip_address):
            global _controller  # noqa: PLW0603
            _controller = HeartbeatController(
                host=ip_address,
                port=port,
                interval=interval,
                payload=payload.encode(),
            )
            return _controller

        registry.register(heartbeat_provider_dynamic)


@pytest.hookimpl
def pytest_itf_provision(dut: DUT, config: pytest.Config) -> None:
    if not config.getoption("--itf-heartbeat", default=False):
        return
    autostart = config.getoption("--itf-heartbeat-autostart", default=True)
    if autostart and dut.available(HEARTBEAT_CONTRACT):
        controller = dut.require(HEARTBEAT_CONTRACT)
        controller.start()


@pytest.hookimpl
def pytest_itf_teardown(dut: DUT, config: pytest.Config) -> None:
    global _controller  # noqa: PLW0603
    if _controller is not None:
        _controller.stop()
        _controller = None
