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
"""SSH exec capability (mocked) -- exec provided by *derivation*, not the target.

This plugin provides ``ctf/cap/exec`` for targets that have no native shell but
expose an SSH endpoint. It requires exactly one thing:

* ``ctf/net/ssh_endpoint`` -- where to connect (a target fact/provider).

It knows nothing about tokens. Whether a key must be deployed first is the
*target's* business: a target may declare its endpoint with a
``@requires(ctf/sec/token)`` link, in which case the graph deploys the key
before the endpoint (and therefore before this exec) is integrated. The endpoint
value carries the connecting credential (or ``None`` for anonymous), so the same
plugin serves keyed and keyless targets alike.

Declared unconditionally: it always requires ``ctf/net/ssh_endpoint``. A target
that publishes no endpoint simply leaves ``ctf/cap/exec`` unresolved (loose mode
records it unavailable); no registration guard is needed.
"""

from __future__ import annotations

import shlex

from ctf.contracts import provides, requires

from ..capabilities import exec as cap_exec

#: The target's SSH endpoint: ``(host, port, credential)`` (mocked). ``credential``
#: is ``None`` for anonymous, else an object with ``.token_id`` / ``.valid``.
ENDPOINT = "ctf/net/ssh_endpoint"


class _SshExec:
    def __init__(self, endpoint: tuple) -> None:
        host, port, credential = endpoint
        self._credential = credential
        who = credential.token_id if credential is not None else "anonymous"
        print(f"[ssh] opened session to {host}:{port} as {who!r}")

    def execute(self, command: str) -> tuple[int, bytes]:
        if self._credential is not None and not self._credential.valid:
            return 255, b"Permission denied (credential invalid)"
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return 2, f"parse error: {exc}".encode()
        if not argv:
            return 0, b""
        prog, args = argv[0], argv[1:]
        if prog == "echo":
            newline = b"\n"
            if args[:1] == ["-n"]:
                newline = b""
                args = args[1:]
            return 0, " ".join(args).encode() + newline
        if prog == "whoami":
            who = self._credential.token_id if self._credential is not None else "anonymous"
            return 0, who.encode() + b"\n"
        return 127, f"{prog}: command not found\n".encode()


@provides(cap_exec.CONTRACT)
@requires(ENDPOINT)
def ssh_exec(endpoint: tuple) -> cap_exec.Exec:
    return _SshExec(endpoint)


def pytest_ctf_setup(registry, config):
    # Declared unconditionally. On a target with no SSH endpoint the provider is
    # simply unresolvable and the engine records ``ctf/cap/exec`` unavailable.
    registry.register(ssh_exec)
