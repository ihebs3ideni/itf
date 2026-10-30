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
"""The original target API over contracts, and `requires_capabilities`.

`LegacyTarget` finds the root scope's nodes by contract token and presents them in the original
shape: `execute`, `execute_async`, `wrap_exec`, `upload`, `download`, `restart`, `ssh`, `sftp`,
`ping`, `ping_lost`. It works with any recipe providing those contracts.
"""

import functools

import pytest

from score.itf.core.process import WrappedProcess

from .adapters import LegacySftp, LegacySsh
from .target import Target

COMMAND = "itf.capabilities.exec.command"
PROCESS = "itf.capabilities.exec.process"
FILES = "itf.capabilities.files.transfer"
PLATFORM = "itf.capabilities.platform.instance"
SHELL = "itf.capabilities.exec.shell"
PING = "itf.capabilities.net.ping"


def node_of(view, token: str, name: str | None = None):
    """Node `name` if given and present, else the first node of `token` in the scope (by name)."""
    names = sorted(n["name"] for n in view.plan()["target"]["nodes"] if n["contract"] == token)
    if name in names:
        return view.get(name)
    return view.get(names[0]) if names else None


class LegacyTarget(Target):
    def __init__(self, view, capabilities=None):
        super().__init__(capabilities=capabilities)
        self.view = view

    def _node(self, token: str, name: str | None = None):
        node = node_of(self.view, token, name)
        if node is None:
            raise NotImplementedError(f"the recipe declares no {token} node")
        return node

    def execute(self, command: str):
        code, output = self._node(COMMAND, "command").exec(command)
        return code, output.encode()

    def execute_async(self, binary_path, args=None, cwd="/", **kwargs):
        return self._node(PROCESS, "process").spawn(binary_path, args=args, cwd=cwd)

    def spawn(self, binary_path, args=None, cwd="/", **kwargs):
        return self.execute_async(binary_path, args=args, cwd=cwd)

    def wrap_exec(self, *args, **kwargs) -> WrappedProcess:
        return WrappedProcess(self._node(PROCESS, "process"), *args, **kwargs)

    def upload(self, local_path: str, remote_path: str) -> None:
        self._node(FILES, "files").upload(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        self._node(FILES, "files").download(remote_path, local_path)

    def restart(self) -> None:
        self._node(PLATFORM).restart()

    def ssh(self, username=None, password=None, pkey_path=None, port=None, **_ignored):
        """The recipe's SSH session. One login per node: a different login needs its own node."""
        shell = self._node(SHELL)
        credentials = shell.credentials
        for asked, have in (
            (username, credentials.user),
            (password, credentials.password),
            (pkey_path, credentials.key_path),
            (port, shell.endpoint.port),
        ):
            if asked is not None and asked != have:
                raise NotImplementedError(
                    "target.ssh() with another login or port: declare a shell node for it in the recipe"
                )
        return LegacySsh(shell)

    def sftp(self, ssh_connection=None, **_ignored):
        return LegacySftp(self._node(FILES, "sftp"))

    def ping(self, timeout, wait_ms_precision=None):
        return self._node(PING).wait_up(timeout)

    def ping_lost(self, timeout, interval=1, wait_ms_precision=None):
        return self._node(PING).wait_down(timeout)


def requires_capabilities(*capabilities):
    """Skip a test unless the target has every capability: "exec", "file_transfer", "restart", "ssh", "sftp".
    The new API gates with `@itf.requires(token)` instead, before the run."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            target = kwargs.get("target") or next((a for a in args if hasattr(a, "has_all_capabilities")), None)
            if target and not target.has_all_capabilities(set(capabilities)):
                pytest.skip(f"Target missing required capabilities: {capabilities}")
            return func(*args, **kwargs)

        return wrapper

    return decorator
