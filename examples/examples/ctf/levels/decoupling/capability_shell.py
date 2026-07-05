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
"""PLUGIN B -- a CAPABILITY. Lives in its OWN repo, decoupled from the target.

Pretend this file ships in a separate repository. The ONLY thing it may import
is core ``ctf`` (here: ``ctf.contracts`` and the ``ctf.target`` anchor). It does
NOT import Plugin A (``target_box``) or its ``Box`` class -- they are not on its
PYTHONPATH. Its single link to the target is the core-blessed ``ctf/target``
anchor contract.

This plugin implements ``ctf/cap/exec``. It ``@requires`` only the generic
``ctf/target`` anchor and adapts whatever handle the anchor yields (anything with
a ``.run(cmd)`` method) into the ``Exec`` protocol.

Because the coupling is by *contract*, not by import, this exact plugin works
against any target that publishes ``ctf/target`` -- mock box, docker, ssh, qemu.
Swap Plugin A's repo; Plugin B is untouched.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ctf.contracts import provides, requires
from ctf.target import TARGET_ANCHOR

#: The reserved framework contract this plugin implements.
CONTRACT = "ctf/cap/exec"


@runtime_checkable
class Exec(Protocol):
    def execute(self, command: str) -> tuple[int, bytes]: ...


class _ShellOverTarget:
    """Adapts the target's uniform ``run`` primitive into the Exec capability."""

    def __init__(self, target) -> None:
        # `target` is whatever ctf/target yields. We only rely on `.run(cmd)`.
        self._target = target

    def execute(self, command: str) -> tuple[int, bytes]:
        return self._target.run(command)


@provides(CONTRACT)
@requires(TARGET_ANCHOR)
def shell_capability(target) -> Exec:
    # The engine injects the resolved ctf/target handle. The build order
    # (target ACQUIRED -> capability) is a graph consequence, not orchestration.
    return _ShellOverTarget(target)


def pytest_ctf_setup(registry, config):
    registry.register(shell_capability)
