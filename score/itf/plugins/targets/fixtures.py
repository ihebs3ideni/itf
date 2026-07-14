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
"""Generic contract-backed fixtures for target-provided capabilities.

These fixtures resolve contracts from the DUT and skip if unavailable.
They are loaded automatically when any target plugin is active.

Each capability plugin (ssh, ping, dlt) provides its own fixtures in its
own plugin.py. This module only covers the base contracts that targets
directly provide (exec, file_transfer, restart).

The DUT itself is available as the ``dut`` fixture (provided by itf_plugin).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def exec_interface(dut):
    """Execute commands on the target (``itf/cap/exec``)."""
    if not dut.available("itf/cap/exec"):
        pytest.skip("DUT does not publish 'itf/cap/exec'")
    return dut.require("itf/cap/exec")


@pytest.fixture
def file_transfer_interface(dut):
    """Upload/download files (``itf/cap/file_transfer``)."""
    if not dut.available("itf/cap/file_transfer"):
        pytest.skip("DUT does not publish 'itf/cap/file_transfer'")
    return dut.require("itf/cap/file_transfer")


@pytest.fixture
def restart_interface(dut):
    """Restart the target (``itf/cap/restart``)."""
    if not dut.available("itf/cap/restart"):
        pytest.skip("DUT does not publish 'itf/cap/restart'")
    return dut.require("itf/cap/restart")
