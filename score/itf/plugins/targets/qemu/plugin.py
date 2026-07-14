# *******************************************************************************
# Copyright (c) 2025-2026 Contributors to the Eclipse Foundation
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
"""QEMU target pytest plugin.

Loaded via: pytest_plugins = ["score.itf.plugins.targets.qemu.plugin"]

Declares (phase: declare):
- ctf/target (TARGET_ANCHOR) — QemuRuntime instance
- itf/cap/exec — delegates to itf/cap/ssh
- itf/cap/file_transfer — delegates to itf/cap/sftp
- itf/cap/restart — QEMU process restart
- itf/net/ssh_endpoint — SSH params from QEMU config
- itf/net/ip_address — target IP from QEMU config

Verifies (phase: verify):
- QEMU VM is reachable via ping (shared ping plugin)
- SSH/SFTP connectivity (delegated to SSH capability plugin)
"""

from __future__ import annotations

import logging
import socket

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.target import TARGET_ANCHOR
from score.itf.core.utils.bunch import Bunch
from score.itf.plugins.targets.qemu.config import load_configuration
from score.itf.plugins.targets.qemu.runtime import qemu_target
from score.itf.plugins.capabilities.ping.ping import ping as ping_host

logger = logging.getLogger(__name__)

# Contracts
CAP_EXEC_CONTRACT = "itf/cap/exec"
CAP_FILE_TRANSFER_CONTRACT = "itf/cap/file_transfer"
CAP_RESTART_CONTRACT = "itf/cap/restart"
CAP_SSH_CONTRACT = "itf/cap/ssh"
CAP_SFTP_CONTRACT = "itf/cap/sftp"
CAP_SSH_ENDPOINT_CONTRACT = "itf/net/ssh_endpoint"
CAP_IP_ADDRESS_CONTRACT = "itf/net/ip_address"
QEMU_RUNTIME_CONFIG_CONTRACT = "itf/target/qemu/runtime_config"


# ---------------------------------------------------------------------------
# Providers (module-level, pure transformations)
# ---------------------------------------------------------------------------
@provides(TARGET_ANCHOR)
@requires(QEMU_RUNTIME_CONFIG_CONTRACT)
def qemu_anchor(runtime_config):
    logger.info(f"Starting tests on host: {socket.gethostname()}")
    with qemu_target(runtime_config) as qemu:
        yield qemu


@provides(CAP_SSH_ENDPOINT_CONTRACT)
@requires(QEMU_RUNTIME_CONFIG_CONTRACT)
def qemu_ssh_endpoint(runtime_config):
    return {
        "host": runtime_config.qemu_config.networks[0].ip_address,
        "port": runtime_config.qemu_config.ssh_port,
        "username": "root",
        "password": "",
        "pkey_path": "",
    }


@provides(CAP_IP_ADDRESS_CONTRACT)
@requires(QEMU_RUNTIME_CONFIG_CONTRACT)
def qemu_ip_address(runtime_config):
    return runtime_config.qemu_config.networks[0].ip_address


@provides(CAP_EXEC_CONTRACT)
@requires(CAP_SSH_CONTRACT)
def qemu_exec(ssh):
    return ssh


@provides(CAP_FILE_TRANSFER_CONTRACT)
@requires(CAP_SFTP_CONTRACT)
def qemu_file_transfer(sftp):
    return sftp


@provides(CAP_RESTART_CONTRACT)
@requires(TARGET_ANCHOR)
def qemu_restart(target):
    return target


# ---------------------------------------------------------------------------
# CLI Options
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(
        "--qemu-config",
        action="store",
        required=True,
        help="Path to json file with target configurations.",
    )
    parser.addoption("--qemu-image", action="store", help="Path to a QEMU image")


# ---------------------------------------------------------------------------
# Phase: DECLARE — register descriptors and providers
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_declare(registry, config):
    runtime_cfg = Bunch(
        qemu_config=load_configuration(config.getoption("qemu_config")),
        qemu_image=config.getoption("qemu_image"),
    )
    registry.add_descriptor(Descriptor(QEMU_RUNTIME_CONFIG_CONTRACT, value=runtime_cfg))

    registry.register(qemu_anchor)
    registry.register(qemu_ssh_endpoint)
    registry.register(qemu_ip_address)
    registry.register(qemu_exec)
    registry.register(qemu_file_transfer)
    registry.register(qemu_restart)


# ---------------------------------------------------------------------------
# Phase: VERIFY — startup checks (VM reachable, interfaces resolved)
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_verify(dut, config):
    if not dut.available(CAP_IP_ADDRESS_CONTRACT):
        return

    # Verify QEMU VM is reachable (uses shared ping utility)
    ip = dut.require(CAP_IP_ADDRESS_CONTRACT)
    result = ping_host(ip, timeout=30)
    assert result, f"QEMU target at {ip} is not reachable within 30s"
    logger.info(f"QEMU startup check: ping {ip} OK")

    # Verify exec interface resolves (SSH must be working)
    if dut.available(CAP_EXEC_CONTRACT):
        exec_iface = dut.require(CAP_EXEC_CONTRACT)
        # Attempt a simple command to confirm the interface is live
        try:
            exit_code, _ = exec_iface.execute("echo itf_ready")
            assert exit_code == 0, "QEMU exec interface not responsive"
            logger.info("QEMU startup check: exec interface OK")
        except Exception as exc:
            raise AssertionError(f"QEMU startup check failed: exec interface error: {exc}") from exc
