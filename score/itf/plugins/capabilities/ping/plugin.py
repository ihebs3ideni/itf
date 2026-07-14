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
"""Ping capability pytest plugin — shared by all targets with IP addresses.

Loaded via: pytest_plugins = ["score.itf.plugins.capabilities.ping.plugin"]

Declares (phase: declare):
- itf/cap/ping — PingComponent (requires itf/net/ip_address from target)

Verifies (phase: verify):
- Pings localhost to confirm the ping component works as infrastructure.

This plugin is target-agnostic: it consumes the itf/net/ip_address descriptor
published by any target (Docker, QEMU, etc.) and provides a ping interface
through both a fixture and the DUT.
"""

from __future__ import annotations

import logging

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.plugins.capabilities.ping.ping import ping as ping_host, PingComponent

logger = logging.getLogger(__name__)

# Contracts
CAP_PING_CONTRACT = "itf/cap/ping"
IP_ADDRESS_CONTRACT = "itf/net/ip_address"


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
@provides(CAP_PING_CONTRACT)
@requires(IP_ADDRESS_CONTRACT)
def ping_capability(ip_address):
    return PingComponent(str(ip_address))


# ---------------------------------------------------------------------------
# Device registration helper
# ---------------------------------------------------------------------------
def register_ping(registry, *, device: str) -> None:
    """Register a ping provider for a specific device scope.

    Registers ``itf/cap/ping`` into the device's own registry. The device
    scope must have an ``itf/net/ip_address`` descriptor (or inherit one).
    """
    with registry.device(device) as dev:
        dev.register(ping_capability)


# ---------------------------------------------------------------------------
# Phase: DECLARE — register the ping provider
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_declare(registry, config):
    registry.register(ping_capability)


# ---------------------------------------------------------------------------
# Phase: VERIFY — confirm ping infrastructure works (ping localhost)
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_verify(dut, config):
    if not dut.available(CAP_PING_CONTRACT):
        return
    result = ping_host("127.0.0.1", timeout=5)
    if result:
        logger.info("Ping startup check: localhost OK")
    else:
        logger.warning("Ping startup check: localhost unreachable (ping utility may be missing)")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def ping_interface(dut):
    """Ping component resolved from the DUT.

    Available to any target that publishes itf/net/ip_address.
    Shared between Docker, QEMU, and any future targets.
    """
    if not dut.available(CAP_PING_CONTRACT):
        pytest.skip(f"DUT does not publish {CAP_PING_CONTRACT!r}")
    return dut.require(CAP_PING_CONTRACT)
