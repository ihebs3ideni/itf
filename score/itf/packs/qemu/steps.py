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
from typing import Protocol

from score.itf.core import delivers


class Platform(Protocol):
    def start(self) -> None: ...
    def running(self) -> bool: ...


class Console(Protocol):
    def open(self) -> None: ...
    def is_open(self) -> bool: ...


@delivers("itf.states.platform.up", name="qemu.start_platform", uses={"platform": "itf.capabilities.platform.instance"})
def start_platform(platform: Platform) -> None:
    platform.start()


@start_platform.probe
def platform_is_up(platform: Platform) -> bool:
    return platform.running()


@delivers("itf.states.console.open", name="qemu.open_console", uses={"console": "itf.capabilities.exec.console"})
def open_console(console: Console) -> None:
    console.open()


@open_console.probe
def console_is_open(console: Console) -> bool:
    return console.is_open()
