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
"""Capability gating shared by every test level.

A test expresses a capability requirement in one of two target-agnostic ways:

* inject a capability fixture (``shell``, ``files``, ``power``, ``network``) --
  if the composed target does not publish that capability, the test skips;
* mark it ``@pytest.mark.requires_capability("ctf/cap/...")`` for a capability it
  needs but does not directly inject.

Availability is answered by the composition graph (``dut.available``) -- whether
the capability can actually be resolved against the composed target -- never by a
target object. Registered by each level via ``pytest_plugins``.
"""

from __future__ import annotations

import pytest

from ctf import get_dut

from plugins.capabilities import exec as cap_exec
from plugins.capabilities import file_transfer as cap_file_transfer
from plugins.capabilities import network as cap_network
from plugins.capabilities import ping as cap_ping
from plugins.capabilities import restart as cap_restart


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_capability(*contracts): skip unless the composed target "
        "publishes every named contract",
    )


def pytest_runtest_setup(item):
    dut = get_dut(item.config)
    for marker in item.iter_markers(name="requires_capability"):
        for contract in marker.args:
            if dut is None or not dut.available(contract):
                pytest.skip(f"composed target does not publish capability {contract!r}")


def _capability(dut, contract: str):
    if not dut.available(contract):
        pytest.skip(f"composed target does not publish capability {contract!r}")
    return dut.require(contract)


@pytest.fixture
def shell(dut):
    """``ctf/cap/exec``."""
    return _capability(dut, cap_exec.CONTRACT)


@pytest.fixture
def files(dut):
    """``ctf/cap/file_transfer``."""
    return _capability(dut, cap_file_transfer.CONTRACT)


@pytest.fixture
def power(dut):
    """``ctf/cap/restart``."""
    return _capability(dut, cap_restart.CONTRACT)


@pytest.fixture
def network(dut):
    """``ctf/cap/network`` (absent on some targets)."""
    return _capability(dut, cap_network.CONTRACT)


@pytest.fixture
def ping(dut):
    """``ctf/cap/ping`` -- derived; present only when the target has a network."""
    return _capability(dut, cap_ping.CONTRACT)
