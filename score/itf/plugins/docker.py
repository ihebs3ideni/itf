# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
"""ITF Docker plugin — runs integration tests inside Docker containers.

This plugin now delegates to :class:`~score.itf.core.environment.DockerEnvironment`
so that ITF and SCTF share the same container runtime infrastructure.
"""

import logging
import pytest

from score.itf.plugins.core import determine_target_scope
from score.itf.plugins.core import Target
from score.itf.core.environment import DockerEnvironment


logger = logging.getLogger(__name__)


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


DOCKER_CAPABILITIES = ["exec"]


class DockerTarget(Target):
    """Target backed by a :class:`DockerEnvironment`.

    Provides the same interface as before — the underlying Docker container
    is accessible via ``self.container`` for tests that use the Docker SDK
    directly (``target.exec_run(...)``), while new code can use
    ``self.environment`` for the unified API.
    """

    def __init__(self, environment: DockerEnvironment, container, capabilities=DOCKER_CAPABILITIES):
        super().__init__(capabilities=set(capabilities))
        self.environment = environment
        self.container = container

    def __getattr__(self, name):
        # Delegate unknown attributes to the underlying Docker container
        # so that existing tests using target.exec_run(...) keep working.
        return getattr(self.container, name)


@pytest.fixture(scope=determine_target_scope)
def target_init(request):
    docker_image = request.config.getoption("docker_image")
    docker_image_bootstrap = request.config.getoption("docker_image_bootstrap")

    env = DockerEnvironment.from_image(
        docker_image,
        bootstrap_command=docker_image_bootstrap,
    )
    env.setup()

    # Expose the raw container for backward compatibility
    container = env._container

    yield DockerTarget(env, container)

    env.teardown()

