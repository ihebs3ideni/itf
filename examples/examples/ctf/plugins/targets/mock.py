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
"""Mock TARGET: in-process fakes, no OS or external services.

This is the fastest test strategy -- everything runs in-process against a fake
filesystem and a tiny command interpreter. It deliberately publishes only a
*subset* of capabilities (exec, file_transfer, restart) and NOT ``ctf/cap/network``,
so a target-agnostic suite run against it auto-skips the network test. That is
the whole point: capability availability is a graph fact, and the same suite
adapts to whatever the composed target publishes.
"""

from __future__ import annotations

import shlex

from ctf.contracts import provides, requires
from ctf.target import TARGET_ANCHOR

from plugins.capabilities import exec as cap_exec
from plugins.capabilities import file_transfer as cap_file_transfer
from plugins.capabilities import restart as cap_restart


class _FakeMachine:
    """A minimal in-process stand-in for a target: fake fs + tiny shell."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.restarts = 0

    def execute(self, command: str) -> tuple[int, bytes]:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return 2, f"parse error: {exc}".encode()
        if not argv:
            return 0, b""
        prog, args = argv[0], argv[1:]
        if prog == "echo":
            newline = b"\n"
            if args and args[0] == "-n":
                newline = b""
                args = args[1:]
            return 0, " ".join(args).encode() + newline
        if prog == "cat":
            if not args:
                return 1, b"cat: missing operand\n"
            data = self.files.get(args[0])
            if data is None:
                return 1, f"cat: {args[0]}: No such file\n".encode()
            return 0, data
        return 127, f"{prog}: command not found\n".encode()


# --------------------------------------------------------------------------
# Capability adapters over the fake machine.
# --------------------------------------------------------------------------
class _Exec:
    def __init__(self, machine: _FakeMachine):
        self._machine = machine

    def execute(self, command: str) -> tuple[int, bytes]:
        return self._machine.execute(command)


class _FileTransfer:
    def __init__(self, machine: _FakeMachine):
        self._machine = machine

    def upload(self, local_path: str, remote_path: str) -> None:
        with open(local_path, "rb") as f:
            self._machine.files[remote_path] = f.read()

    def download(self, remote_path: str, local_path: str) -> None:
        data = self._machine.files.get(remote_path)
        if data is None:
            raise FileNotFoundError(remote_path)
        with open(local_path, "wb") as f:
            f.write(data)


class _Restart:
    def __init__(self, machine: _FakeMachine):
        self._machine = machine

    def restart(self) -> None:
        self._machine.restarts += 1


# --------------------------------------------------------------------------
# Providers: a session-scoped fake machine + a subset of capabilities.
# --------------------------------------------------------------------------
@provides(TARGET_ANCHOR)
def mock_machine() -> _FakeMachine:
    # The acquired target handle: the generic ``ctf/target`` anchor that roots
    # the mandatory bring-up spine. Capabilities attach above it.
    return _FakeMachine()


@provides(cap_exec.CONTRACT)
@requires(TARGET_ANCHOR)
def exec_capability(machine: _FakeMachine) -> cap_exec.Exec:
    return _Exec(machine)


@provides(cap_file_transfer.CONTRACT)
@requires(TARGET_ANCHOR)
def file_transfer_capability(machine: _FakeMachine) -> cap_file_transfer.FileTransfer:
    return _FileTransfer(machine)


@provides(cap_restart.CONTRACT)
@requires(TARGET_ANCHOR)
def restart_capability(machine: _FakeMachine) -> cap_restart.Restart:
    return _Restart(machine)


# Intentionally NO ctf/cap/network provider: a target may lack a capability.


def pytest_ctf_setup(registry, config):
    registry.register(mock_machine)
    registry.register(exec_capability)
    registry.register(file_transfer_capability)
    registry.register(restart_capability)
