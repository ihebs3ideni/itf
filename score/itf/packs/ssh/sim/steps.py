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
"""Opening a simulated session: nothing listens, so the platform's state stands in for reachability."""

from typing import Protocol

from score.itf.core import delivers


class Platform(Protocol):
    running: bool


class Shell(Protocol):
    platform: Platform

    def connect(self) -> None: ...
    def is_connected(self) -> bool: ...


@delivers(
    "itf.states.shell.open",
    name="sim.open_session",
    requires=("itf.states.platform.up",),
    also_delivers=("itf.states.network.reachable",),
    uses={"shell": "itf.capabilities.exec.shell"},
)
def open_session(shell: Shell) -> None:
    shell.connect()


@open_session.probe
def is_session_open(shell: Shell) -> bool:
    return shell.is_connected()


@open_session.probe_for("itf.states.network.reachable")
def is_reachable(shell: Shell) -> bool:
    return shell.platform.running
