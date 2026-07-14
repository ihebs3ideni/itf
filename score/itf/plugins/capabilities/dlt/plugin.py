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
"""DLT capability pytest plugin.

Loaded via: pytest_plugins = ["score.itf.plugins.capabilities.dlt.plugin"]

Provides:
- itf/cap/dlt_on_target — DltOnTargetComponent

Requires:
- itf/cap/exec and itf/cap/file_transfer (published by a target plugin)
"""

from __future__ import annotations

import json
import logging

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.utils.bunch import Bunch
from score.itf.plugins.capabilities.dlt import CAP_DLT_ON_TARGET_CONTRACT, DltOnTargetComponent, DltReceive, Protocol

logger = logging.getLogger(__name__)

CAP_EXEC_CONTRACT = "itf/cap/exec"
CAP_FILE_TRANSFER_CONTRACT = "itf/cap/file_transfer"
DLT_BINARY_PATH_CONTRACT = "itf/dlt/binary_path"


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
@provides(CAP_DLT_ON_TARGET_CONTRACT)
@requires(CAP_EXEC_CONTRACT, CAP_FILE_TRANSFER_CONTRACT, DLT_BINARY_PATH_CONTRACT)
def dlt_on_target_component(exec_interface, file_transfer_interface, binary_path):
    return DltOnTargetComponent(exec_interface, file_transfer_interface, binary_path)


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(
        "--dlt-config",
        action="store",
        required=False,
        help="Path to json file with dlt configurations.",
    )
    parser.addoption(
        "--dlt-receive-path",
        action="store",
        required=True,
        help="Path to dlt-receive binary.",
    )
    parser.addoption(
        "--dlt-receive-on-target-path",
        action="store",
        required=False,
        help="Path to dlt-receive binary cross-compiled for the target platform.",
    )


@pytest.fixture(scope="session")
def dlt_config(request):
    b = Bunch(
        host_ip="127.0.0.1",
        target_ip="127.0.0.1",
        multicast_ips=[],
    )

    dlt_config_path = request.config.getoption("dlt_config")
    if dlt_config_path:
        with open(dlt_config_path) as f:
            json_config = json.load(f)
            if "host_ip" in json_config:
                b.host_ip = json_config["host_ip"]
            if "target_ip" in json_config:
                b.target_ip = json_config["target_ip"]
            if "multicast_ips" in json_config:
                b.multicast_ips = json_config["multicast_ips"]

    b.dlt_receive_path = request.config.getoption("dlt_receive_path")

    return b


@pytest.fixture(scope="session")
def dlt(dlt_config):
    with DltReceive(
        protocol=Protocol.UDP,
        host_ip=dlt_config.host_ip,
        multicast_ips=dlt_config.multicast_ips,
        binary_path=dlt_config.dlt_receive_path,
    ):
        yield


@pytest.fixture()
def dlt_on_target(dut):
    if not dut.available(CAP_DLT_ON_TARGET_CONTRACT):
        pytest.skip(f"composed DUT does not publish {CAP_DLT_ON_TARGET_CONTRACT!r}")
    component = dut.require(CAP_DLT_ON_TARGET_CONTRACT)
    yield component
    component.stop_all()


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    on_target_path = config.getoption("dlt_receive_on_target_path", default=None)
    local_binary = on_target_path or config.getoption("dlt_receive_path")

    from score.itf.core.ctf.descriptor import Descriptor

    registry.add_descriptor(Descriptor(DLT_BINARY_PATH_CONTRACT, value=local_binary))
    registry.register(dlt_on_target_component)
