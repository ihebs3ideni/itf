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
"""An SSH session over paramiko (`ssh.shell`); commands run in a login shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import paramiko

from . import client as ssh_client


class Endpoint(Protocol):
    host: str
    port: int


class Credentials(Protocol):
    user: str
    password: str | None
    key_path: str | None


@dataclass(frozen=True)
class ShellConfig:
    connect_timeout: float = 15.0
    n_retries: int = 5
    retry_interval: float = 1.0
    keep_alive_interval: int | None = None
    command_timeout: float = 30.0
    max_exec_time: float = 180.0


class SshSession:
    """`itf.capabilities.exec.shell` over paramiko; commands run in a login shell."""

    endpoint: Endpoint
    credentials: Credentials

    def __init__(self, endpoint: Endpoint, credentials: Credentials, config: dict):
        self.endpoint = endpoint
        self.credentials = credentials
        self.connect_timeout = config.get("connect_timeout", 15.0)
        self.n_retries = config.get("n_retries", 5)
        self.retry_interval = config.get("retry_interval", 1.0)
        self.keep_alive_interval = config.get("keep_alive_interval")
        self.command_timeout = config.get("command_timeout", 30.0)
        self.max_exec_time = config.get("max_exec_time", 180.0)
        self._client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        self.close()
        self._client = ssh_client.connect(
            self.endpoint.host,
            self.endpoint.port,
            self.credentials.user,
            password=self.credentials.password,
            key_path=self.credentials.key_path,
            timeout=self.connect_timeout,
            n_retries=self.n_retries,
            retry_interval=self.retry_interval,
            keep_alive_interval=self.keep_alive_interval,
        )

    def is_connected(self) -> bool:
        transport = self._client.get_transport() if self._client is not None else None
        return transport is not None and transport.is_active()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def client(self) -> paramiko.SSHClient:
        """The connected paramiko client, for what this API does not cover."""
        if not self.is_connected():
            raise RuntimeError(f"ssh session to {self.endpoint.host}:{self.endpoint.port} is not open")
        return self._client

    def exec_lines(
        self,
        command: str,
        timeout: float | None = None,
        max_exec_time: float | None = None,
        separate_stderr: bool = True,
        log: bool = True,
    ) -> tuple[int, list[str], list[str]]:
        """(exit code, stdout lines, stderr lines); stderr merged into stdout unless `separate_stderr`.
        `timeout` bounds the start, `max_exec_time` the run (exit code -1 when exceeded)."""
        return ssh_client.execute_command_output(
            self.client(),
            command,
            timeout=self.command_timeout if timeout is None else timeout,
            max_exec_time=self.max_exec_time if max_exec_time is None else max_exec_time,
            separate_stderr=separate_stderr,
            log=log,
        )

    def exec(self, command: str, timeout: float = 30.0) -> tuple[int, str]:
        """(exit code, stdout followed by stderr); never raises on a nonzero exit."""
        code, out, err = self.exec_lines(command, timeout=timeout, separate_stderr=True)
        return code, "".join(out) + "".join(err)

    def run(self, command: str, timeout: float = 30.0) -> str:
        """stdout; raises RuntimeError with stderr on a nonzero exit."""
        code, out, err = self.exec_lines(command, timeout=timeout, separate_stderr=True)
        if code != 0:
            raise RuntimeError(f"ssh command failed ({code}): {command}\n{''.join(err)}")
        return "".join(out)
