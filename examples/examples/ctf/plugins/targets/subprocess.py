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
"""Subprocess TARGET: run against the local host via subprocess/shutil.

A middle ground between the in-process mock and a real container: commands run
for real on the host shell and files are copied on the host filesystem, but
there is no isolation or network identity. Publishes exec, file_transfer and
restart -- and NOT ``ctf/cap/network`` -- so, like the mock, it demonstrates a
target-agnostic suite adapting to the capabilities actually present.
"""

from __future__ import annotations

import shutil
import subprocess

from ctf.contracts import provides, requires
from ctf.target import TARGET_ANCHOR

from plugins.capabilities import exec as cap_exec
from plugins.capabilities import file_transfer as cap_file_transfer
from plugins.capabilities import restart as cap_restart


class _Host:
    """The local host, used as a target."""


class _Exec:
    def __init__(self, host: _Host):
        self._host = host

    def execute(self, command: str) -> tuple[int, bytes]:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
        )
        return proc.returncode, proc.stdout + proc.stderr


class _FileTransfer:
    def __init__(self, host: _Host):
        self._host = host

    def upload(self, local_path: str, remote_path: str) -> None:
        shutil.copyfile(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        shutil.copyfile(remote_path, local_path)


class _Restart:
    def __init__(self, host: _Host):
        self._host = host

    def restart(self) -> None:
        # Nothing to restart on the host; the target stays usable.
        pass


@provides(TARGET_ANCHOR)
def subprocess_host() -> _Host:
    # The acquired target handle: the generic ``ctf/target`` anchor rooting the
    # mandatory bring-up spine.
    return _Host()


@provides(cap_exec.CONTRACT)
@requires(TARGET_ANCHOR)
def exec_capability(host: _Host) -> cap_exec.Exec:
    return _Exec(host)


@provides(cap_file_transfer.CONTRACT)
@requires(TARGET_ANCHOR)
def file_transfer_capability(host: _Host) -> cap_file_transfer.FileTransfer:
    return _FileTransfer(host)


@provides(cap_restart.CONTRACT)
@requires(TARGET_ANCHOR)
def restart_capability(host: _Host) -> cap_restart.Restart:
    return _Restart(host)


def pytest_ctf_setup(registry, config):
    registry.register(subprocess_host)
    registry.register(exec_capability)
    registry.register(file_transfer_capability)
    registry.register(restart_capability)
