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
"""``ctf/scenario/echo`` -- an echo endpoint, *derived* from a capability.

A scenario is a higher-level behaviour composed from capability contracts rather
than a target primitive. This one derives an echo endpoint from ``ctf/cap/exec``:
``send(payload)`` runs ``echo`` on whatever target backs the exec capability and
returns the bytes. No target implements "echo"; the same scenario runs on every
target that publishes a shell (mock, subprocess, docker).

This is the ``cap-requires-cap`` shape: the scenario provider ``@requires`` a
capability contract, so the engine builds the capability first and the scenario
on top of it -- ordering is a graph consequence, not orchestration.
"""

from __future__ import annotations

import shlex
from typing import Protocol, runtime_checkable

from ctf.contracts import provides, requires

from ..capabilities import exec as cap_exec

#: The reserved framework contract for this scenario.
CONTRACT = "ctf/scenario/echo"


@runtime_checkable
class Echo(Protocol):
    """Send bytes to the target's echo endpoint and receive them back."""

    def send(self, payload: bytes) -> bytes:
        """Send ``payload`` to the echo endpoint; return the echoed bytes."""
        ...


class _ExecEcho:
    """Echo derived from a shell: run ``echo`` on the target and read it back."""

    def __init__(self, shell: cap_exec.Exec) -> None:
        self._shell = shell

    def send(self, payload: bytes) -> bytes:
        code, out = self._shell.execute("echo -n " + shlex.quote(payload.decode()))
        if code != 0:
            raise RuntimeError(f"echo failed with exit code {code}: {out!r}")
        return out


@provides(CONTRACT)
@requires(cap_exec.CONTRACT)
def echo_via_exec(shell: cap_exec.Exec) -> Echo:
    return _ExecEcho(shell)


def pytest_ctf_setup(registry, config):
    # Declared unconditionally: it requires ``ctf/cap/exec``. A target with no
    # shell leaves the scenario unresolvable and the engine records it
    # unavailable (loose mode); its tests then skip. No self-gating.
    registry.register(echo_via_exec)
