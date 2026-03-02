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
"""Docker pytest plugin for ITF integration tests.

Provides a single ``target`` fixture backed by :class:`DockerTarget` — a rich
wrapper around a Docker container that offers command execution (synchronous,
detached, streaming), process management, network inspection, file transfer,
and background log capture.

The ``target`` fixture is activated automatically when a test requests it.
Its scope is determined dynamically by ``determine_target_scope``.
"""

import logging
import subprocess

import pytest

from score.itf.plugins.core import determine_target_scope, register_capability_hint
from score.itf.plugins.docker.docker_target import DockerTarget, get_docker_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capability hints
# ---------------------------------------------------------------------------

register_capability_hint(
    "tcpdump_external",
    "Requires --spawn_strategy=local and CAP_NET_RAW on the hermetic tcpdump binary. "
    "Either run as root (sudo bazel test --spawn_strategy=local) or set capabilities "
    "with: sudo setcap cap_net_admin,cap_net_raw=eip bazel-bin/third_party/tcpdump/tcpdump"
)


# ---------------------------------------------------------------------------
# CLI options
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
        help="Docker image bootstrap command, that will be executed before referencing the container.",
    )
    parser.addoption(
        "--tcpdump-path",
        action="store",
        default="",
        help="Path to hermetically built tcpdump binary for external capture.",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope=determine_target_scope)
def docker_configuration():
    """Customisation point for the Docker container.

    Override in ``conftest.py`` to set environment, volumes, shm_size, etc.

    :returns: Configuration overrides merged into the defaults.
    :rtype: dict
    """
    return {}


@pytest.fixture(scope=determine_target_scope)
def _docker_configuration(docker_configuration):
    defaults = {
        "command": "sleep infinity",
        "init": True,
        "environment": {},
    }
    return {**defaults, **docker_configuration}


@pytest.fixture(scope=determine_target_scope)
def target_init(request, _docker_configuration):
    logger.debug(_docker_configuration)

    docker_image_bootstrap = request.config.getoption("docker_image_bootstrap")
    docker_image = request.config.getoption("docker_image")

    if docker_image_bootstrap:
        logger.info("Executing bootstrap command: %s", docker_image_bootstrap)
        subprocess.run([docker_image_bootstrap], check=True)

    client = get_docker_client()

    kwargs = dict(
        command=_docker_configuration["command"],
        detach=True,
        auto_remove=True,
        init=_docker_configuration.get("init", True),
    )
    if _docker_configuration.get("environment"):
        kwargs["environment"] = _docker_configuration["environment"]
    if _docker_configuration.get("volumes"):
        kwargs["volumes"] = _docker_configuration["volumes"]
    if _docker_configuration.get("privileged"):
        kwargs["privileged"] = True
    if _docker_configuration.get("network_mode"):
        kwargs["network_mode"] = _docker_configuration["network_mode"]
    if _docker_configuration.get("shm_size"):
        kwargs["shm_size"] = _docker_configuration["shm_size"]

    logger.info("Starting container from image %s", docker_image)
    container = client.containers.run(docker_image, **kwargs)
    logger.info("Container started: %s", container.short_id)

    tcpdump_bin = request.config.getoption("tcpdump_path", default="")
    yield DockerTarget(client, container, tcpdump_bin=tcpdump_bin)

    # Teardown
    cid = container.short_id
    logger.info("Stopping container %s", cid)
    try:
        container.stop(timeout=1)
    except Exception:
        logger.debug("Container stop failed (may already be removed)", exc_info=True)
