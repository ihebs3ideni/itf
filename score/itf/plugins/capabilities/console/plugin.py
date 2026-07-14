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
"""Serial console capability pytest plugin.

Loaded via: pytest_plugins = ["score.itf.plugins.capabilities.console.plugin"]

Declares (phase: declare):
- itf/cap/console — ConsoleComponent (factory for serial console connections)

Requires:
- itf/net/serial_endpoint (published by a target plugin or descriptor)

Verifies (phase: verify):
- Opens the serial port and sends a newline, expecting a prompt response.

CLI Options:
- --serial-port: Serial device path (e.g. /dev/ttyUSB0, COM3)
- --serial-baudrate: Baud rate (default: 115200)
- --serial-prompt: Expected shell prompt (default: "# ")
"""

from __future__ import annotations

import logging

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.plugins.capabilities.console import (
    CAP_CONSOLE_CONTRACT,
    CONSOLE_ENDPOINT_CONTRACT,
    ConsoleComponent,
    ConsoleEndpoint,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
@provides(CAP_CONSOLE_CONTRACT)
@requires(CONSOLE_ENDPOINT_CONTRACT)
def console_capability(endpoint_data):
    endpoint = ConsoleEndpoint.from_mapping(endpoint_data)
    return ConsoleComponent(endpoint)


# ---------------------------------------------------------------------------
# Phase: DECLARE — register console provider and optional descriptor
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_declare(registry, config):
    # If CLI options are provided, register the endpoint as a descriptor
    port = config.getoption("--serial-port", default=None)
    if port:
        baudrate = config.getoption("--serial-baudrate", default=115200)
        endpoint_data = {
            "port": port,
            "baudrate": baudrate,
        }
        registry.add_descriptor(Descriptor(CONSOLE_ENDPOINT_CONTRACT, endpoint_data))

    registry.register(console_capability)


# ---------------------------------------------------------------------------
# Phase: VERIFY — startup check (open port, expect prompt)
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_verify(dut, config):
    if not dut.available(CAP_CONSOLE_CONTRACT):
        return

    console = dut.require(CAP_CONSOLE_CONTRACT)
    prompt = config.getoption("--serial-prompt", default="# ")

    with console.open() as session:
        # Send a newline and wait for the prompt
        session.write_line("")
        try:
            session.read_until(prompt, timeout=10.0)
        except TimeoutError as exc:
            raise AssertionError(
                f"Console health check failed: no prompt ({prompt!r}) received on {console.endpoint.port}"
            ) from exc

    logger.info("Console startup check: OK (%s @ %d)", console.endpoint.port, console.endpoint.baudrate)


# ---------------------------------------------------------------------------
# CLI Options
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    group = parser.getgroup("itf-console", "Serial console options")
    group.addoption(
        "--serial-port",
        default=None,
        help="Serial device path (e.g. /dev/ttyUSB0, COM3). "
        "If provided, registers itf/net/serial_endpoint automatically.",
    )
    group.addoption(
        "--serial-baudrate",
        type=int,
        default=115200,
        help="Baud rate for serial connection (default: 115200).",
    )
    group.addoption(
        "--serial-prompt",
        default="# ",
        help="Expected shell prompt for health checks and execute() (default: '# ').",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def console_interface(dut):
    """Console component resolved from the DUT."""
    if not dut.available(CAP_CONSOLE_CONTRACT):
        pytest.skip(f"DUT does not publish {CAP_CONSOLE_CONTRACT!r}")
    return dut.require(CAP_CONSOLE_CONTRACT)


@pytest.fixture
def console_session(console_interface):
    """An open serial console session (context-managed)."""
    with console_interface.open() as session:
        yield session
