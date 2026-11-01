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
from typing import Protocol

from score.itf.core import state


class Logs(Protocol):
    __contract__ = "observe.logs"

    def subscribe(self) -> None: ...
    def _live(self) -> bool: ...


@state("logs.active", after=("platform.up",), label="subscribe")
def subscribe_stream(logs: Logs) -> None:
    logs.subscribe()


@subscribe_stream.probe
def is_stream_active(logs: Logs) -> bool:
    return logs._live()
