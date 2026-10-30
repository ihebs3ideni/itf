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
"""Docker providers. Constructing the platform starts nothing: `docker.start_platform` (steps.py) does;
teardown stops and removes the container and the network created for it."""

from collections.abc import Iterator

from score.itf.core import provides

from .command import DockerExec, Platform
from .endpoint import DockerEndpoint, EndpointConfig, EndpointPlatform
from .files import DockerFiles
from .platform import DockerPlatform, PlatformConfig
from .process import DockerProcess

NEEDS_PLATFORM = {"platform": "itf.capabilities.platform.instance"}


@provides("itf.capabilities.platform.instance", name="docker.instance", config_schema=PlatformConfig)
def make_platform(config: dict) -> Iterator[DockerPlatform]:
    platform = DockerPlatform(config)
    yield platform
    platform.stop()


@provides("itf.capabilities.exec.command", name="docker.exec", needs=NEEDS_PLATFORM)
def make_exec(platform: Platform) -> DockerExec:
    return DockerExec(platform)


@provides("itf.capabilities.exec.process", name="docker.process", needs=NEEDS_PLATFORM)
def make_process(platform: Platform) -> DockerProcess:
    return DockerProcess(platform)


@provides("itf.capabilities.files.transfer", name="docker.files", needs=NEEDS_PLATFORM)
def make_files(platform: Platform) -> DockerFiles:
    return DockerFiles(platform)


@provides(
    "itf.capabilities.descriptor.endpoint",
    name="docker.endpoint",
    config_schema=EndpointConfig,
    gives=("host", "port"),
    needs={"platform": "itf.capabilities.platform.instance"},
)
def make_endpoint(platform: EndpointPlatform, config: dict) -> DockerEndpoint:
    return DockerEndpoint(platform, config)
