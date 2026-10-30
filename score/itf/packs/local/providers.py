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
"""Host providers. Constructing the platform creates nothing: `local.start_platform` does."""

from collections.abc import Iterator

from score.itf.core import provides

from .command import LocalExec, Platform
from .files import LocalFiles
from .files import Platform as FilesPlatform
from .platform import LocalPlatform, PlatformConfig
from .process import LocalProcess


@provides("itf.capabilities.platform.instance", name="local.instance", config_schema=PlatformConfig)
def make_platform(config: dict) -> Iterator[LocalPlatform]:
    platform = LocalPlatform(config)
    yield platform
    platform.stop()


@provides("itf.capabilities.exec.command", name="local.exec", needs={"platform": "itf.capabilities.platform.instance"})
def make_exec(platform: Platform) -> LocalExec:
    return LocalExec(platform)


@provides(
    "itf.capabilities.exec.process", name="local.process", needs={"platform": "itf.capabilities.platform.instance"}
)
def make_process(platform: Platform) -> LocalProcess:
    return LocalProcess(platform)


@provides(
    "itf.capabilities.files.transfer", name="local.files", needs={"platform": "itf.capabilities.platform.instance"}
)
def make_files(platform: FilesPlatform) -> LocalFiles:
    return LocalFiles(platform)
