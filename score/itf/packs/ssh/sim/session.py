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
"""An in-memory shell session over a simulated platform."""

from __future__ import annotations

from typing import Protocol


class Endpoint(Protocol):
    host: str
    port: int


class Credentials(Protocol):
    user: str


class Platform(Protocol):
    gen: int

    def exec(self, cmd: str) -> str: ...


class SimSession:
    """Dies when the simulated platform's generation changes, like a session across a reimage."""

    endpoint: Endpoint
    platform: Platform

    def __init__(self, endpoint: Endpoint, credentials: Credentials, platform: Platform):
        self.endpoint = endpoint
        self.credentials = credentials
        self.platform = platform
        self._gen: int | None = None

    def connect(self) -> None:
        self._gen = self.platform.gen

    def is_connected(self) -> bool:
        return self._gen is not None and self._gen == self.platform.gen

    def close(self) -> None:
        self._gen = None

    def exec(self, command: str, timeout: float = 30.0) -> tuple[int, str]:
        if not self.is_connected():
            raise RuntimeError("shell session is dead (the platform changed under it)")
        return 0, self.platform.exec(command)

    def run(self, command: str, timeout: float = 30.0) -> str:
        return self.exec(command, timeout)[1]
