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
import logging
import pytest

from score.itf.plugins.core import determine_target_scope
from score.itf.plugins.core import Target

from score.itf.core.com.ssh import Ssh
from score.itf.core.docker import DockerContainer, get_docker_client


logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--docker-image",
        action="store",
        required=False,
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
    """ITF target backed by a Docker container.

    Wraps a :class:`~score.itf.core.docker.DockerContainer` and adds the
    ``Target`` capability model, SSH convenience, and ``__getattr__`` proxy
    to the raw ``docker-py`` container for backward compatibility.
    """

    def __init__(self, docker_container, capabilities=DOCKER_CAPABILITIES):
        super().__init__(capabilities=capabilities)
        self._docker = docker_container
        # Keep direct reference for __getattr__ backward compat
        self.container = docker_container.raw

    def __getattr__(self, name):
        return getattr(self.container, name)

    def get_ip(self, network="bridge"):
        return self._docker.get_ip(network)

    def get_gateway(self, network="bridge"):
        return self._docker.get_gateway(network)

    def ssh(self, username="score", password="score", port=2222):
        return Ssh(target_ip=self.get_ip(), port=port, username=username, password=password)

    @property
    def docker_container(self):
        """The underlying :class:`DockerContainer` instance."""
        return self._docker


@pytest.fixture(scope=determine_target_scope)
def docker_configuration():
    """
    Fixture that provides a customization point for Docker configuration in tests.

    This fixture allows tests to override and customize Docker settings by providing
    a dictionary of configuration parameters. Tests can use this fixture to inject
    custom Docker configuration values as needed for their specific test scenarios.

    Returns:
        dict: An empty dictionary that can be populated with custom Docker configuration
            parameters by tests or through pytest fixtures/parametrization.

    Scope:
        The fixture scope is determined dynamically based on the target scope.
    """
    return {}


@pytest.fixture(scope=determine_target_scope)
def _docker_configuration(docker_configuration):
    configuration = {
        "environment": {},
        "command": "sleep infinity",
        "init": True,
    }
    merged_configuration = {**configuration, **docker_configuration}

    return merged_configuration


@pytest.fixture(scope=determine_target_scope)
def target_init(request, _docker_configuration):
    print(_docker_configuration)

    docker_image_bootstrap = request.config.getoption("docker_image_bootstrap")
    docker_image = request.config.getoption("docker_image")

    if not docker_image:
        raise ValueError(
            "--docker-image is required when using the Docker plugin. "
            "Pass it via Bazel args or the sctf_docker() plugin."
        )

    client = get_docker_client()
    docker_container = DockerContainer.run(
        client,
        image=docker_image,
        command=_docker_configuration["command"],
        environment=_docker_configuration.get("environment"),
        init=_docker_configuration.get("init", True),
        bootstrap_command=docker_image_bootstrap,
    )

    yield DockerTarget(docker_container)
    docker_container.stop(timeout=1)
