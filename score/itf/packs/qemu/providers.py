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
"""QEMU providers. Constructing the platform starts nothing: `qemu.start_platform` (steps.py) does;
teardown stops QEMU and deletes the copy-on-write overlays it booted from."""

from collections.abc import Iterator
from score.itf.core import provides

from .platform import PlatformConfig, QemuPlatform
from .descriptors import ConfiguredPlatform, QemuCredentials, QemuEndpoint
from .console import ConsolePlatform, QemuConsole


@provides("itf.capabilities.platform.instance", name="qemu.instance", config_schema=PlatformConfig)
def make_platform(config: dict) -> Iterator[QemuPlatform]:
    platform = QemuPlatform(config)
    yield platform
    platform.stop()


@provides(
    "itf.capabilities.descriptor.endpoint",
    name="qemu.endpoint",
    gives=("host", "port"),
    needs={"platform": "itf.capabilities.platform.instance"},
)
def make_endpoint(platform: ConfiguredPlatform) -> QemuEndpoint:
    return QemuEndpoint(platform)


@provides(
    "itf.capabilities.descriptor.credentials",
    name="qemu.credentials",
    gives=("user", "password", "key_path"),
    needs={"platform": "itf.capabilities.platform.instance"},
)
def make_credentials(platform: ConfiguredPlatform) -> QemuCredentials:
    return QemuCredentials(platform)


@provides(
    "itf.capabilities.exec.console",
    name="qemu.console",
    needs={"platform": "itf.capabilities.platform.instance"},
)
def make_console(platform: ConsolePlatform) -> Iterator[QemuConsole]:
    console = QemuConsole(platform)
    yield console
    console.close()
