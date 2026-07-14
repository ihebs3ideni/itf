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
"""Docker target pytest plugin.

Loaded via: pytest_plugins = ["score.itf.plugins.targets.docker.plugin"]

Declares (phase: declare):
- ctf/target (TARGET_ANCHOR) — DockerRuntime instance
- itf/cap/exec — self-contained via Docker API
- itf/cap/file_transfer — self-contained via put_archive/get_archive
- itf/cap/restart — container restart
- itf/net/ssh_endpoint — SSH params for capability plugins
- itf/net/ip_address — container IP for capability plugins

Provisions (phase: provision):
- Starts the Docker container (happens lazily on first DUT access)

Verifies (phase: verify):
- Docker exec health check (container responds to echo)
"""

from __future__ import annotations

import logging
import os

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.target import TARGET_ANCHOR
from score.itf.plugins.targets.docker.runtime import DockerExecInterface, docker_target_runtime

logger = logging.getLogger(__name__)

# Contracts
CAP_EXEC_CONTRACT = "itf/cap/exec"
CAP_FILE_TRANSFER_CONTRACT = "itf/cap/file_transfer"
CAP_RESTART_CONTRACT = "itf/cap/restart"
CAP_SSH_ENDPOINT_CONTRACT = "itf/net/ssh_endpoint"
CAP_IP_ADDRESS_CONTRACT = "itf/net/ip_address"
DOCKER_SPINE_ANCHOR = "ctf/target/docker"
DOCKER_IMAGE_CONTRACT = "itf/target/docker/image"
DOCKER_CONFIG_CONTRACT = "itf/target/docker/config"


# ---------------------------------------------------------------------------
# Providers (module-level, pure transformations)
# ---------------------------------------------------------------------------
@provides(TARGET_ANCHOR)
@requires(DOCKER_IMAGE_CONTRACT, DOCKER_CONFIG_CONTRACT)
def docker_anchor(docker_image, docker_config):
    yield from docker_target_runtime(docker_image, docker_config)


@provides(CAP_EXEC_CONTRACT)
@requires(TARGET_ANCHOR)
def docker_exec(target):
    return DockerExecInterface(target)


@provides(CAP_FILE_TRANSFER_CONTRACT)
@requires(TARGET_ANCHOR)
def docker_file_transfer(target):
    return target


@provides(CAP_RESTART_CONTRACT)
@requires(TARGET_ANCHOR)
def docker_restart(target):
    return target


@provides(CAP_SSH_ENDPOINT_CONTRACT)
@requires(TARGET_ANCHOR)
def docker_ssh_endpoint(target):
    return {
        "host": target.get_ip(),
        "port": 2222,
        "username": "score",
        "password": "score",
        "pkey_path": "",
    }


@provides(CAP_IP_ADDRESS_CONTRACT)
@requires(TARGET_ANCHOR)
def docker_ip_address(target):
    return target.get_ip()


@provides(DOCKER_SPINE_ANCHOR)
@requires(CAP_EXEC_CONTRACT)
def docker_spine_anchor(exec_capability):
    """Explicit docker anchor that makes exec part of the mandatory spine."""
    return exec_capability


# ---------------------------------------------------------------------------
# CLI Options
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(
        "--docker-image",
        action="store",
        required=True,
        help="Docker image to run tests against.",
    )
    parser.addoption(
        "--docker-image-bootstrap",
        action="store",
        required=False,
        help="Docker image bootstrap command, executed before starting the container.",
    )
    parser.addoption(
        "--keep-target",
        action="store_true",
        default=False,
        help="Keep the target alive across the whole session (session-scoped).",
    )
    parser.addoption(
        "--extract-coverage",
        action="store_true",
        default=False,
        help="Extract coverage files (.gcda) from the container before teardown.",
    )
    parser.addoption(
        "--coverage-output-dir",
        default=os.path.join(
            os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", "/tmp"),
            "sysroot",
        ),
        help="Directory to write extracted coverage files.",
    )


# ---------------------------------------------------------------------------
# Phase: DECLARE — register descriptors and providers
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_declare(registry, config):
    configuration = {
        "environment": {},
        "command": "sleep infinity",
        "init": True,
        "shm_size": "2G",
        "volumes": {},
        "bootstrap_command": config.getoption("docker_image_bootstrap"),
        "extract_coverage": config.getoption("extract_coverage"),
        "coverage_output_dir": config.getoption("coverage_output_dir"),
    }

    registry.add_descriptor(Descriptor(DOCKER_IMAGE_CONTRACT, value=config.getoption("docker_image")))
    registry.add_descriptor(Descriptor(DOCKER_CONFIG_CONTRACT, value=configuration))

    registry.register(docker_anchor)
    registry.register(docker_exec)
    registry.register(docker_file_transfer)
    registry.register(docker_restart)
    registry.register(docker_ssh_endpoint)
    registry.register(docker_ip_address)
    registry.register(docker_spine_anchor)


# ---------------------------------------------------------------------------
# Phase: VERIFY — startup checks (container responds to exec)
# ---------------------------------------------------------------------------
@pytest.hookimpl
def pytest_itf_verify(dut, config):
    if not dut.available(TARGET_ANCHOR):
        return
    target = dut.require(TARGET_ANCHOR)
    exit_code, output = target.execute("echo health_check")
    if exit_code != 0:
        raise AssertionError(f"Docker exec health check failed (exit_code={exit_code})")
    logger.info("Docker startup check: container exec OK")
