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
import subprocess
import io
import os
import tarfile
import docker as pypi_docker
import pytest

from score.itf.plugins.core import determine_target_scope
from score.itf.plugins.core import Target

from score.itf.core.com.ssh import Ssh


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


class DockerTarget(Target):
    def __init__(self, container):
        super().__init__()
        self.container = container

    def __getattr__(self, name):
        return getattr(self.container, name)

    def execute(self, command: str):
        return self.container.exec_run(command)

    def upload(self, local_path: str, remote_path: str) -> None:
        if not os.path.isfile(local_path):
            raise FileNotFoundError(local_path)

        remote_dir = os.path.dirname(remote_path) or "/"
        remote_name = os.path.basename(remote_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(local_path, arcname=remote_name)
        tar_stream.seek(0)

        ok = self.container.put_archive(remote_dir, tar_stream.getvalue())
        if not ok:
            raise RuntimeError(f"Failed to upload '{local_path}' to '{remote_path}'")

    def download(self, remote_path: str, local_path: str) -> None:
        stream, _ = self.container.get_archive(remote_path)
        tar_bytes = b"".join(stream)

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
            members = tar.getmembers()
            if not members:
                raise FileNotFoundError(remote_path)

            member = members[0]
            extracted = tar.extractfile(member)
            if extracted is None:
                raise FileNotFoundError(remote_path)
            with open(local_path, "wb") as f:
                f.write(extracted.read())

    def restart(self) -> None:
        self.container.restart()

    def get_ip(self):
        self.container.reload()
        return self.container.attrs["NetworkSettings"]["Networks"]["bridge"]["IPAddress"]

    def get_gateway(self):
        self.container.reload()
        return self.container.attrs["NetworkSettings"]["Networks"]["bridge"]["Gateway"]

    def ssh(self, username="score", password="score", port=2222):
        return Ssh(target_ip=self.get_ip(), port=port, username=username, password=password)


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
    if docker_image_bootstrap:
        logger.info(f"Executing custom image bootstrap command: {docker_image_bootstrap}")
        subprocess.run([docker_image_bootstrap], check=True)

    docker_image = request.config.getoption("docker_image")
    client = pypi_docker.from_env()
    container = client.containers.run(
        docker_image,
        _docker_configuration["command"],
        detach=True,
        auto_remove=False,
        init=_docker_configuration["init"],
        environment=_docker_configuration["environment"],
    )
    try:
        yield DockerTarget(container)
    finally:
        try:
            container.stop(timeout=1)
        finally:
            # Ensure restart() doesn't accidentally delete the container mid-test.
            container.remove(force=True)
