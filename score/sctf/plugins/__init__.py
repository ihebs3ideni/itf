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
"""Pytest plugin providing a Docker-based sandbox for SCTF tests.

This plugin exposes the ``docker_sandbox`` fixture which creates a
:class:`~score.sctf.environment.DockerEnvironment`, calls ``setup()``,
and yields a :class:`~score.itf.core.utils.bunch.Bunch` with the
environment and workspace paths.

**Important**: This plugin does NOT register ``--docker-image`` or
``--docker-image-bootstrap``.  Those options are registered by the ITF
Docker plugin (``score.itf.plugins.docker``), which **must** be loaded
alongside this plugin.  The ``sctf_docker()`` Bazel plugin factory
ensures both plugins are always enabled together.

Usage in a test::

    def test_my_binary(docker_sandbox):
        handle = docker_sandbox.environment.execute("/opt/bin/my_app", [])
        # ...
        docker_sandbox.environment.stop_process(handle)
"""

import binascii
import logging
import os
import pathlib

import pytest

from score.itf.core.utils.bunch import Bunch
from score.sctf.environment.docker_env import DockerEnvironment
from score.sctf.exception import SctfRuntimeError

logger = logging.getLogger(__name__)


# NOTE: No pytest_addoption here.  --docker-image and --docker-image-bootstrap
# are registered by score.itf.plugins.docker.  This plugin reads them via
# request.config.getoption().


@pytest.fixture(scope="session")
def _docker_root_dir():
    """Create a unique root directory for this test session."""
    root = pathlib.Path(f"/tmp/{binascii.hexlify(os.urandom(16)).decode('ascii')}")
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="session")
def _docker_workspace(_docker_root_dir):
    """Workspace directory mapped into the container."""
    return str(_docker_root_dir)


@pytest.fixture(scope="session")
def docker_sandbox(request, _docker_workspace):
    """Session-scoped fixture that creates a Docker-based SCTF environment.

    Yields a :class:`Bunch` with:
        - ``environment``: :class:`DockerEnvironment` instance (already set up)
        - ``tmp_workspace``: Host path mapped as ``/tmp`` in the container

    The container is stopped on teardown.
    """
    docker_image = request.config.getoption("--docker-image", default=None)
    docker_bootstrap = request.config.getoption("--docker-image-bootstrap", default=None)

    if not docker_image:
        raise SctfRuntimeError(
            "--docker-image is required. "
            "This is normally injected by the sctf_docker() plugin via "
            "py_itf_test."
        )

    environment = DockerEnvironment.from_image(
        image=docker_image,
        mounts={"/tmp": _docker_workspace},
        bootstrap_command=docker_bootstrap,
    )

    environment.setup()

    env = Bunch(
        environment=environment,
        tmp_workspace=_docker_workspace,
    )

    yield env

    environment.teardown()
