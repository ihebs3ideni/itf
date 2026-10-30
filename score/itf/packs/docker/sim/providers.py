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
"""In-memory platform providers, for offline runs."""

from score.itf.core import provides

from .platform import Platform, PlatformConfig, SimExec, SimPlatform


@provides("itf.capabilities.platform.instance", name="sim.platform", config_schema=PlatformConfig)
def make_platform(config: dict) -> SimPlatform:
    return SimPlatform(config["name"], config.get("ip", "127.0.0.1"))


@provides(
    "itf.capabilities.exec.command",
    name="sim.exec",
    needs={"platform": "itf.capabilities.platform.instance"},
)
def make_exec(platform: Platform) -> SimExec:
    return SimExec(platform)
