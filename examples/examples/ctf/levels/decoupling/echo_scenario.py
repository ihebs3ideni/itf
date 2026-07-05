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
"""PLUGIN C -- a SCENARIO derived from a capability. Lives in its OWN repo.

``ctf/scenario/echo`` is built purely from ``ctf/cap/exec``. Pretend this file
ships in a separate repository: the ONLY thing it may import is core ``ctf``.
It does NOT import Plugin B (``capability_shell``) or Plugin A -- it cannot, they
are not on its PYTHONPATH. The single link to the capability is the published
contract *string* ``"ctf/cap/exec"``, declared locally below.

The engine builds target -> exec capability -> echo scenario in order, each in
its own repo, coupled only by contract strings.
"""

from __future__ import annotations

import shlex
from typing import Protocol, runtime_checkable

from ctf.contracts import provides, requires

#: The published contract this scenario builds on. This bare string -- NOT an
#: import of Plugin B -- is the entire coupling. Repo C only needs to know the
#: name Repo B promised to provide.
EXEC = "ctf/cap/exec"

#: The reserved framework contract this plugin implements.
CONTRACT = "ctf/scenario/echo"


@runtime_checkable
class Echo(Protocol):
    def send(self, payload: bytes) -> bytes: ...


class _EchoOverExec:
    def __init__(self, shell) -> None:
        self._shell = shell  # anything satisfying ctf/cap/exec

    def send(self, payload: bytes) -> bytes:
        code, out = self._shell.execute("echo -n " + shlex.quote(payload.decode()))
        if code != 0:
            raise RuntimeError(f"echo failed ({code}): {out!r}")
        return out


@provides(CONTRACT)
@requires(EXEC)
def echo_scenario(shell) -> Echo:
    return _EchoOverExec(shell)


def pytest_ctf_setup(registry, config):
    registry.register(echo_scenario)
