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
"""Opening the session: one connection that establishes two states, each with its own evidence.
`itf.states.shell.open` holds while the session is connected; `itf.states.network.reachable` holds
while its endpoint accepts TCP connections. Works with any shell provider that can connect."""

import socket
from typing import Protocol

from score.itf.core import delivers


class Endpoint(Protocol):
    host: str
    port: int


class Shell(Protocol):
    endpoint: Endpoint

    def connect(self) -> None: ...
    def is_connected(self) -> bool: ...


def accepts_connections(endpoint: Endpoint, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=timeout):
            return True
    except OSError:
        return False


@delivers(
    "itf.states.shell.open",
    name="ssh.open_session",
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
    return accepts_connections(shell.endpoint)
