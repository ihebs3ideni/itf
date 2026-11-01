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
"""One-shot commands through an SSH session node (`ssh.exec`)."""

from __future__ import annotations

import logging

from typing import Protocol
import paramiko

logger = logging.getLogger(__name__)


class Shell(Protocol):
    __contract__ = "exec.shell"

    def exec(self, command: str, timeout: float = 30.0) -> tuple[int, str]: ...
    def client(self) -> paramiko.SSHClient: ...


def _short(text: str, limit: int = 200) -> str:
    """One log line: the first `limit` characters, newlines shown as ⏎."""
    text = text.replace("\r", "").replace("\n", "⏎")
    return text if len(text) <= limit else text[:limit] + f"… ({len(text)} chars)"


class SshExec:
    """`command` through an SSH session node; the session owns the connection."""

    def __init__(self, shell: Shell):
        self.shell = shell

    def exec(self, command: str, timeout: float = 30.0) -> tuple[int, str]:
        logger.debug("ssh exec: sending %s", command)
        code, output = self.shell.exec(command, timeout)
        logger.debug("ssh exec: output %s", _short(output))
        logger.info("ssh exec: %s -> exit %s", command, code)
        return code, output
