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
"""Mock target pytest plugin.

Loaded via: pytest_plugins = ["score.itf.plugins.targets.mock.plugin"]

Provides:
- ctf/target (TARGET_ANCHOR)
- itf/cap/exec (records commands)
- itf/cap/file_transfer (in-memory)
- itf/net/ip_address (127.0.0.1)
"""

from __future__ import annotations

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.target import TARGET_ANCHOR
from score.itf.plugins.targets.mock import MockRuntime

CAP_EXEC_CONTRACT = "itf/cap/exec"
CAP_FILE_TRANSFER_CONTRACT = "itf/cap/file_transfer"
CAP_IP_ADDRESS_CONTRACT = "itf/net/ip_address"


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
@provides(TARGET_ANCHOR)
def mock_anchor():
    return MockRuntime()


@provides(CAP_EXEC_CONTRACT)
@requires(TARGET_ANCHOR)
def mock_exec(target):
    return target


@provides(CAP_FILE_TRANSFER_CONTRACT)
@requires(TARGET_ANCHOR)
def mock_file_transfer(target):
    return target


@provides(CAP_IP_ADDRESS_CONTRACT)
@requires(TARGET_ANCHOR)
def mock_ip_address(_target):
    return "127.0.0.1"


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_declare(registry, config):
    registry.register(mock_anchor)
    registry.register(mock_exec)
    registry.register(mock_file_transfer)
    registry.register(mock_ip_address)
