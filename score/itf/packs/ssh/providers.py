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
"""SSH providers. A session is constructed unconnected; `ssh.open_session` (steps.py) connects it."""

from collections.abc import Iterator
from score.itf.core import provides

from .session import Credentials, Endpoint, ShellConfig, SshSession
from .command import Shell, SshExec
from .process import SshProcess
from .files import SftpFiles


@provides(
    "itf.capabilities.exec.shell",
    name="ssh.shell",
    config_schema=ShellConfig,
    needs={
        "endpoint": "itf.capabilities.descriptor.endpoint",
        "credentials": "itf.capabilities.descriptor.credentials",
    },
)
def make_session(endpoint: Endpoint, credentials: Credentials, config: dict) -> Iterator[SshSession]:
    session = SshSession(endpoint, credentials, config)
    yield session
    session.close()


@provides(
    "itf.capabilities.exec.command",
    name="ssh.exec",
    needs={"shell": "itf.capabilities.exec.shell"},
)
def make_exec(shell: Shell) -> SshExec:
    return SshExec(shell)


@provides(
    "itf.capabilities.exec.process",
    name="ssh.process",
    needs={"shell": "itf.capabilities.exec.shell"},
)
def make_process(shell: Shell) -> SshProcess:
    return SshProcess(shell)


@provides(
    "itf.capabilities.files.transfer",
    name="sftp.files",
    needs={"shell": "itf.capabilities.exec.shell"},
)
def make_files(shell: Shell) -> SftpFiles:
    return SftpFiles(shell)
