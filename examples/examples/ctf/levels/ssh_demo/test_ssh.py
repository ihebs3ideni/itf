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
"""Tests that exec over SSH -- oblivious to token deployment.

These use the ordinary ``shell`` fixture (``ctf/cap/exec``). On sealed_a that
exec is SSH-over-a-deployed-token; on sealed_b it is SSH-over-anonymous. The
tests do not know or care -- they just execute commands.
"""

from __future__ import annotations

from plugins.security import token as sec_token


def test_exec_over_ssh(shell):
    code, out = shell.execute("echo -n hello over ssh")
    assert code == 0
    assert out == b"hello over ssh"


def test_specific_token_deployed(request, shell):
    # Only the exact requested id is deployed -- not "all tokens".
    if request.config.getoption("--ssh-target") == "sealed_a":
        assert sec_token.DEPLOYED == ["token-42"]
        code, who = shell.execute("whoami")
        assert who == b"token-42\n"
    else:
        assert sec_token.DEPLOYED == []
        code, who = shell.execute("whoami")
        assert who == b"anonymous\n"
    assert code == 0
