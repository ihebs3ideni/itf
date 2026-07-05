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
"""PLUGIN A -- the TARGET. Lives in its OWN repo. Publishes only ``ctf/target``.

Pretend this file ships in a separate repository. The ONLY thing it may import
is core ``ctf`` (here: ``ctf.contracts`` and the ``ctf.target`` anchor). It does
not import Plugin B or Plugin C -- they are not on its PYTHONPATH.

This plugin's whole job is to *acquire the target*. It exposes the target as the
generic ``ctf/target`` anchor: a handle with one uniform low-level primitive,
``run(cmd) -> (code, bytes)``.

It knows NOTHING about ``ctf/cap/exec`` or any capability. A different target
(docker, ssh, qemu) would publish the same anchor with its own ``run`` -- and
every capability written against the anchor would keep working unchanged.
"""

from __future__ import annotations

import shlex

from ctf.contracts import provides
from ctf.target import TARGET_ANCHOR


class Box:
    """A mocked target box: booted, with a tiny uniform command primitive."""

    def __init__(self) -> None:
        self.booted = True

    def run(self, command: str) -> tuple[int, bytes]:
        """The one primitive the target offers. Capabilities adapt this."""
        argv = shlex.split(command)
        if not argv:
            return 0, b""
        if argv[0] == "echo":
            args = argv[1:]
            newline = b"\n"
            if args[:1] == ["-n"]:
                newline = b""
                args = args[1:]
            return 0, " ".join(args).encode() + newline
        return 127, f"{argv[0]}: command not found\n".encode()


@provides(TARGET_ANCHOR)
def box() -> Box:
    # The target is ACQUIRED here; capabilities attach above it. No capability
    # code lives in this plugin.
    return Box()


def pytest_ctf_setup(registry, config):
    registry.register(box)
