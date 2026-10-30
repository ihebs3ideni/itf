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
"""`itf.states.logs.active` for dlt-receive. Over TCP, add a relation in the recipe so it waits for
the target: `logs.active requires network.reachable`."""

from typing import Protocol

from score.itf.core import delivers


class Logs(Protocol):
    def subscribe(self) -> None: ...
    def active(self) -> bool: ...


@delivers("itf.states.logs.active", name="dlt.start_receive", uses={"logs": "itf.capabilities.observe.logs"})
def start_receive(logs: Logs) -> None:
    logs.subscribe()


@start_receive.probe
def is_receiving(logs: Logs) -> bool:
    return logs.active()
