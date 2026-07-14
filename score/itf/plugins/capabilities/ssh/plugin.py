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
"""SSH/SFTP capability pytest plugin.

Loaded via: pytest_plugins = ["score.itf.plugins.capabilities.ssh.plugin"]

Declares (phase: declare):
- itf/cap/ssh — SshComponent (factory for SSH connections)
- itf/cap/sftp — SftpComponent (factory for SFTP connections)

Requires:
- itf/net/ssh_endpoint (published by a target plugin)

Verifies (phase: verify):
- SSH echo test confirms connectivity
- SFTP list confirms file operations work
"""

from __future__ import annotations

import logging

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.plugins.capabilities.ssh import (
    CAP_SFTP_CONTRACT,
    CAP_SSH_CONTRACT,
    SSH_ENDPOINT_CONTRACT,
    SftpComponent,
    SshComponent,
    SshEndpoint,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
@provides(CAP_SSH_CONTRACT)
@requires(SSH_ENDPOINT_CONTRACT)
def ssh_capability(endpoint_data):
    endpoint = SshEndpoint.from_mapping(endpoint_data)
    return SshComponent(endpoint)


@provides(CAP_SFTP_CONTRACT)
@requires(SSH_ENDPOINT_CONTRACT)
def sftp_capability(endpoint_data):
    endpoint = SshEndpoint.from_mapping(endpoint_data)
    return SftpComponent(endpoint)


# ---------------------------------------------------------------------------
# Device registration helpers
# ---------------------------------------------------------------------------
def register_ssh(registry, *, device: str) -> None:
    """Register an SSH provider for a specific device scope.

    Registers ``itf/cap/ssh`` into the device's own registry. The device
    scope must also have an ``itf/net/ssh_endpoint`` descriptor (or inherit
    one from root).
    """
    with registry.device(device) as dev:
        dev.register(ssh_capability)


def register_sftp(registry, *, device: str) -> None:
    """Register an SFTP provider for a specific device scope.

    Registers ``itf/cap/sftp`` into the device's own registry.
    """
    with registry.device(device) as dev:
        dev.register(sftp_capability)


# ---------------------------------------------------------------------------
# Phase: DECLARE — register SSH/SFTP providers
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_declare(registry, config):
    registry.register(ssh_capability)
    registry.register(sftp_capability)


# ---------------------------------------------------------------------------
# Phase: VERIFY — startup checks (SSH echo, SFTP list)
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_verify(dut, config):
    if dut.available(CAP_SSH_CONTRACT):
        ssh_component = dut.require(CAP_SSH_CONTRACT)
        with ssh_component.connect(timeout=15, n_retries=5, retry_interval=2) as ssh:
            result = ssh.execute_command("echo health_check")
        assert result == 0, "SSH health check failed: could not execute command on target"
        logger.info("SSH startup check: OK")

    if dut.available(CAP_SFTP_CONTRACT):
        sftp_component = dut.require(CAP_SFTP_CONTRACT)
        with sftp_component.connect() as sftp:
            result = sftp.list_dirs_and_files("/")
        assert result, "SFTP health check failed: could not list files on target"
        logger.info("SFTP startup check: OK")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def ssh_interface(dut):
    """SSH connection factory resolved from the DUT."""
    if not dut.available(CAP_SSH_CONTRACT):
        pytest.skip(f"DUT does not publish {CAP_SSH_CONTRACT!r}")
    return dut.require(CAP_SSH_CONTRACT)


@pytest.fixture
def sftp_interface(dut):
    """SFTP connection factory resolved from the DUT."""
    if not dut.available(CAP_SFTP_CONTRACT):
        pytest.skip(f"DUT does not publish {CAP_SFTP_CONTRACT!r}")
    return dut.require(CAP_SFTP_CONTRACT)
